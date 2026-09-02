#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auditoria dos blocos de mineração dirigida do Exp 003 — SOMENTE LEITURA, SEM PHI.

Pergunta que este script responde
---------------------------------
O `Experimento_003_corpus_mv.sqlite3` foi gerado antes ou depois da correção do
`\\b` em `extrair_mv_sqlite.py` (05/08/2026)?

Motivo da dúvida: a única execução de extração com status `concluido` no banco
do AnonClin é a id=8, de 04/08/2026 — anterior à correção. As execuções de
05/08 (id=9 e id=10) ficaram penduradas em `em_execucao`. Se o banco atual for
pré-correção, os registros do bloco `mineracao_documento` são majoritariamente
falso positivo ("RG" casando dentro de ALERGIAS, CIRURGIA, URGÊNCIA), e a
decisão sobre ampliar a extração muda completamente.

O que ele faz
-------------
Reaplica as regex VIGENTES (as corrigidas, com `\\b`) sobre os registros que já
estão gravados em cada bloco de mineração, e conta quantos sobrevivem. Taxa de
sobrevivência alta = banco pós-correção. Taxa baixa = banco pré-correção, e o
bloco precisa ser reprocessado.

Garantias
---------
1. Banco aberto em modo read-only real (URI `mode=ro`). Nunca escreve.
2. A saída contém apenas CONTAGENS. Nenhum trecho de texto clínico é impresso
   ou gravado, em nenhuma circunstância.
3. As regex vêm, por padrão, do próprio `extrair_mv_sqlite.py`, então a
   auditoria usa exatamente as regras vigentes. Se a importação falhar (por
   exemplo, `oracledb` ausente no ambiente), o script cai para cópias locais e
   avisa claramente qual caminho usou.

Uso
---
    python scripts/auditar_mineracao.py
    python scripts/auditar_mineracao.py --saida auditoria_mineracao.json
    python scripts/auditar_mineracao.py --amostra-sistematica 20000

O caminho do banco é resolvido a partir da raiz do repositório; use --db ou a
variável de ambiente EXP003_DB para apontar para outro lugar.
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parent.parent
CAMINHO_PADRAO = RAIZ_REPO / 'outputs' / 'preprocessamento' / 'Experimento_003_corpus_mv.sqlite3'


# ---------------------------------------------------------------------------
# Regex: importa do script de extração; cai para cópia local se não der
# ---------------------------------------------------------------------------

def carregar_regex():
    """
    Tenta importar as regex vigentes de scripts/extrair_mv_sqlite.py.

    Retorna (dict_de_regras, origem) onde origem é 'extrair_mv_sqlite.py' ou
    'copia_local'. A cópia local reproduz a versão corrigida de 05/08/2026 —
    se o original tiver mudado desde então, a importação é a fonte correta e
    a cópia pode divergir. Por isso a origem é sempre reportada na saída.
    """
    caminho = RAIZ_REPO / 'scripts' / 'extrair_mv_sqlite.py'
    if caminho.exists():
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location('_extrair_mv', caminho)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return {
                'documento':  mod.RE_DOCUMENTO,
                'prontuario': mod.RE_PRONTUARIO,
                'matricula':  mod.RE_MATRICULA,
                'endereco':   mod.endereco_real,
            }, 'extrair_mv_sqlite.py'
        except Exception as erro:
            print(f'[aviso] não consegui importar extrair_mv_sqlite.py ({type(erro).__name__}: {erro}).')
            print('[aviso] usando cópia local das regex — confira se batem com o original.\n')

    # Cópia local — espelha a versão corrigida de 05/08/2026
    re_documento  = re.compile(r'\b(?:RG|CNS|CRM|CNH)\b', re.IGNORECASE)
    re_prontuario = re.compile(r'(?i)\bpront(?:u[áa]rio)?\.?\s*[:\-]\s*n?[ºo°]?\s*\d{4,10}\b')
    re_matricula  = re.compile(r'(?i)\bmatr[íi]cula\s*[:\-]\s*\d{3,10}\b')
    re_end_kw     = re.compile(r'\b(RUA|AVENIDA|TRAVESSA|RODOVIA|ALAMEDA|BAIRRO)\b', re.IGNORECASE)
    re_de_rua     = re.compile(r'\bDE\s*$', re.IGNORECASE)

    def endereco_real(texto):
        for m in re_end_kw.finditer(texto):
            if m.group(1).upper() != 'RUA':
                return True
            if not re_de_rua.search(texto[max(0, m.start() - 4):m.start()]):
                return True
        return False

    return {
        'documento':  re_documento,
        'prontuario': re_prontuario,
        'matricula':  re_matricula,
        'endereco':   endereco_real,
    }, 'copia_local'


# Qual regra valida cada bloco de mineração
REGRA_POR_BLOCO = {
    'mineracao_documento':  'documento',
    'mineracao_prontuario': 'prontuario',
    'mineracao_matricula':  'matricula',
    'mineracao_endereco':   'endereco',
}

# Termos contados individualmente no bloco de documento, para mostrar qual
# sigla sustenta o bloco. Só contagem — nunca o texto ao redor.
TERMOS_DOCUMENTO = ['RG', 'CNS', 'CRM', 'CNH']


def conectar_ro(caminho):
    if not caminho.exists():
        sys.exit(f'ERRO: banco não encontrado em {caminho}')
    con = sqlite3.connect(f'file:{caminho.as_posix()}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    return con


def casa(regra, texto):
    """Aplica a regra (regex compilada ou função) a um texto."""
    if texto is None:
        return False
    if callable(regra) and not hasattr(regra, 'search'):
        return bool(regra(texto))
    return bool(regra.search(texto))


def auditar_bloco(con, bloco, regra, contar_termos=False, regex_termos=None):
    cur = con.execute(
        'SELECT ds_evolucao FROM prescricoes WHERE bloco_origem = ?', (bloco,)
    )
    total = sobreviventes = vazios = 0
    por_termo = {t: 0 for t in TERMOS_DOCUMENTO} if contar_termos else None

    for (texto,) in cur:
        total += 1
        if not texto:
            vazios += 1
            continue
        if casa(regra, texto):
            sobreviventes += 1
            if contar_termos:
                for termo, rx in regex_termos.items():
                    if rx.search(texto):
                        por_termo[termo] += 1

    descartados = total - sobreviventes
    return {
        'total_gravado':       total,
        'sobrevivem_regex':    sobreviventes,
        'descartados':         descartados,
        'texto_vazio':         vazios,
        'pct_sobrevivencia':   round(sobreviventes / total * 100, 2) if total else None,
        'pct_falso_positivo':  round(descartados / total * 100, 2) if total else None,
        'ocorrencias_por_termo': por_termo,
    }


def auditar(con, regras, origem_regras, amostra_sistematica=0):
    resultado = {
        'gerado_em': datetime.now(timezone.utc).isoformat(),
        'origem_das_regex': origem_regras,
        'aviso': 'Somente contagens. Nenhum trecho de texto clínico é incluído nesta saída.',
        'blocos': {},
        'metadados_extracao': {},
        'progresso_extracao': {},
    }

    # Estado da extração — diz o que o script gravou e até onde chegou
    try:
        for linha in con.execute('SELECT chave, valor FROM _metadados'):
            resultado['metadados_extracao'][linha['chave']] = linha['valor']
    except sqlite3.Error:
        resultado['metadados_extracao'] = {'_erro': 'tabela _metadados ausente'}

    try:
        for linha in con.execute('SELECT bloco, offset_atual, concluido FROM _progresso'):
            resultado['progresso_extracao'][linha['bloco']] = {
                'offset_atual': linha['offset_atual'],
                'concluido':    bool(linha['concluido']),
            }
    except sqlite3.Error:
        resultado['progresso_extracao'] = {'_erro': 'tabela _progresso ausente'}

    # Distribuição real de bloco_origem
    resultado['distribuicao_bloco_origem'] = {
        (linha['bloco_origem'] or '<nulo>'): linha['n']
        for linha in con.execute(
            'SELECT bloco_origem, COUNT(*) AS n FROM prescricoes '
            'GROUP BY bloco_origem ORDER BY n DESC'
        )
    }
    resultado['total_pareceres'] = con.execute(
        'SELECT COUNT(*) AS n FROM pareceres'
    ).fetchone()['n']

    regex_termos = {t: re.compile(rf'\b{t}\b', re.IGNORECASE) for t in TERMOS_DOCUMENTO}

    for bloco, chave_regra in REGRA_POR_BLOCO.items():
        if bloco not in resultado['distribuicao_bloco_origem']:
            resultado['blocos'][bloco] = {'ausente_no_banco': True}
            continue
        resultado['blocos'][bloco] = auditar_bloco(
            con, bloco, regras[chave_regra],
            contar_termos=(bloco == 'mineracao_documento'),
            regex_termos=regex_termos,
        )

    # Taxa base no bloco sistemático, para comparação
    if amostra_sistematica > 0:
        cur = con.execute(
            'SELECT ds_evolucao FROM prescricoes WHERE bloco_origem = ? LIMIT ?',
            ('sistematica', amostra_sistematica),
        )
        n = casam_doc = 0
        for (texto,) in cur:
            n += 1
            if texto and casa(regras['documento'], texto):
                casam_doc += 1
        resultado['taxa_base_sistematica'] = {
            'amostra':              n,
            'casam_regex_documento': casam_doc,
            'pct':                  round(casam_doc / n * 100, 2) if n else None,
            'nota': 'Fração da amostra sistemática que casaria a regex de DOCUMENTO. '
                    'Serve de linha de base: a mineração só agrega valor se sua taxa '
                    'de sobrevivência for muito maior que esta.',
        }

    return resultado


def resumir(r):
    linhas = [f"Regex carregadas de: {r['origem_das_regex']}", '']

    linhas.append('Distribuição por bloco_origem (prescrições):')
    for bloco, n in r['distribuicao_bloco_origem'].items():
        linhas.append(f'  {bloco:24s} {n:>9,d}')
    linhas.append(f"  {'(pareceres)':24s} {r['total_pareceres']:>9,d}")

    linhas.append('')
    linhas.append('Auditoria dos blocos minerados — reaplicando as regex com \\b:')
    linhas.append(f"  {'bloco':24s} {'gravado':>9s} {'sobrevive':>10s} {'FP':>8s}")
    for bloco, d in r['blocos'].items():
        if d.get('ausente_no_banco'):
            linhas.append(f'  {bloco:24s} {"—":>9s} {"ausente":>10s}')
            continue
        linhas.append(
            f"  {bloco:24s} {d['total_gravado']:>9,d} "
            f"{d['sobrevivem_regex']:>10,d} {d['pct_falso_positivo']:>7.2f}%"
        )

    doc = r['blocos'].get('mineracao_documento', {})
    if doc.get('ocorrencias_por_termo'):
        linhas.append('')
        linhas.append('  Termos que sustentam mineracao_documento:')
        for termo, n in doc['ocorrencias_por_termo'].items():
            linhas.append(f'    {termo:6s} {n:>8,d}')

    if 'taxa_base_sistematica' in r:
        b = r['taxa_base_sistematica']
        linhas.append('')
        linhas.append(
            f"Linha de base (amostra sistemática, n={b['amostra']:,}): "
            f"{b['casam_regex_documento']:,} casam a regex de DOCUMENTO ({b['pct']}%)"
        )

    if r['progresso_extracao'] and '_erro' not in r['progresso_extracao']:
        linhas.append('')
        linhas.append('Progresso registrado pela extração:')
        for bloco, d in r['progresso_extracao'].items():
            estado = 'concluído' if d['concluido'] else 'INCOMPLETO'
            linhas.append(f"  {bloco:24s} offset={d['offset_atual']:>9,d}  {estado}")

    if r['metadados_extracao'] and '_erro' not in r['metadados_extracao']:
        linhas.append('')
        linhas.append('Metadados da extração:')
        for chave, valor in r['metadados_extracao'].items():
            linhas.append(f'  {chave} = {valor}')

    linhas.append('')
    linhas.append('Como ler: sobrevivência alta (>90%) sugere banco pós-correção do \\b.')
    linhas.append('Sobrevivência baixa indica bloco gravado pela versão antiga — reprocessar.')
    return '\n'.join(linhas)


def main():
    parser = argparse.ArgumentParser(
        description='Audita os blocos de mineração do Exp 003 (somente leitura, sem PHI).'
    )
    parser.add_argument('--db', help='Caminho do Experimento_003_corpus_mv.sqlite3.')
    parser.add_argument('--saida', help='Grava o resultado em JSON.')
    parser.add_argument(
        '--amostra-sistematica', type=int, default=0,
        help='Nº de registros do bloco sistemático a testar como linha de base (0 = pular).',
    )
    args = parser.parse_args()

    caminho = Path(args.db).expanduser().resolve() if args.db else (
        Path(os.environ['EXP003_DB']).expanduser().resolve()
        if os.environ.get('EXP003_DB') else CAMINHO_PADRAO
    )

    regras, origem = carregar_regex()
    con = conectar_ro(caminho)
    try:
        resultado = auditar(con, regras, origem, args.amostra_sistematica)
    finally:
        con.close()

    if args.saida:
        destino = Path(args.saida).expanduser().resolve()
        destino.write_text(
            json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8'
        )
        print(f'Resultado gravado em {destino}\n')

    print(f'Banco: {caminho}\n')
    print(resumir(resultado))


if __name__ == '__main__':
    main()
