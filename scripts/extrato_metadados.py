#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extrato de metadados do banco do AnonClin, SOMENTE LEITURA, SEM PHI.

Motivação
---------
A regra 1 do projeto é inviolável: `db.sqlite3` contém texto clínico real de
pacientes (a tabela `tb_anonclin_anotador_sentenca` guarda os tokens das
sentenças) e não pode sair do perímetro institucional. Mas as tabelas de
controle de experimento, ids, contagens, hiperparâmetros, métricas, não são
dado de paciente, e precisam ser consultáveis sem carregar PHI junto.

Este script resolve isso: lê apenas colunas explicitamente autorizadas, nunca
faz `SELECT *`, e valida a saída antes de gravar. O JSON gerado pode circular
livremente; o banco não sai do lugar.

Garantias de construção
-----------------------
1. Banco aberto em modo read-only real (URI `mode=ro`). O script não consegue
   escrever nem que houvesse um bug.
2. Allowlist explícita de tabela → colunas. Uma tabela não listada não é lida,
   nem que seja criada depois. `tb_anonclin_anotador_sentenca` NUNCA é lida.
3. As tabelas do anotador entram só como COUNT agregado. Nenhum conteúdo.
4. O campo `obs` é excluído de todas as tabelas: é texto livre, e texto livre
   pode ter recebido trecho clínico colado. Para ler `obs`, use a interface.
5. Sanitização dos JSONField: chaves e números passam; strings longas são
   redigidas.
6. Guarda final: a saída inteira é varrida antes de gravar. Qualquer string
   acima do limite aborta a execução, falha fechada, não aberta.

Uso
---
    python scripts/extrato_metadados.py
    python scripts/extrato_metadados.py --saida extrato.json
    ANONCLIN_DB=/outro/caminho/db.sqlite3 python scripts/extrato_metadados.py

O caminho do banco é resolvido a partir da raiz do repositório (dois níveis
acima deste arquivo), não hardcoded, roda em qualquer máquina.
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------
# Limites da sanitização
# --------------------------------------------------------------------------

# Strings acima disso dentro de um JSONField são redigidas. Rótulos legítimos
# ("BERTimbau-leNER-large", "B-INSTITUICAO") ficam bem abaixo.
MAX_STR_JSON = 60

# Limite duro da varredura final. Nenhuma string da saída pode passar disso.
# Caminhos de arquivo são a maior string legítima esperada.
MAX_STR_SAIDA = 500

# --------------------------------------------------------------------------
# Allowlist, tabela → colunas lidas na íntegra
#
# O que NÃO está aqui não é lido. `obs` fica de fora em todas.
# --------------------------------------------------------------------------

TABELAS_METADADO = {
    'tb_anonclin_experimento': [
        'id', 'nome', 'descricao', 'criado_em', 'atualizado_em',
    ],
    'tb_anonclin_execucao_analise': [
        'id', 'experimento_id', 'criado_em',
        'total_registros', 'total_prescricoes', 'total_pareceres',
        'pacientes_unicos', 'periodo_inicio', 'periodo_fim', 'total_hospitais',
        'tokens_presc_min', 'tokens_presc_media', 'tokens_presc_mediana',
        'tokens_presc_max', 'tokens_presc_p25', 'tokens_presc_p75',
        'tokens_par_min', 'tokens_par_media', 'tokens_par_mediana',
        'tokens_par_max', 'tokens_par_p25', 'tokens_par_p75',
        'presc_texto_livre', 'presc_template',
        'presc_pct_texto_livre', 'presc_pct_template',
        'par_texto_livre', 'par_template',
        'par_pct_texto_livre', 'par_pct_template',
        'especialidades_json',
    ],
    'tb_anonclin_execucao_extracao_mv': [
        'id', 'experimento_id', 'criado_em', 'finalizado_em',
        'status', 'pid', 'hospitais_incluidos',
        'teto_prescricoes', 'batch_size',
        'caminho_sqlite', 'caminho_log',
    ],
    'tb_anonclin_execucao_preprocessamento': [
        'id', 'experimento_id', 'criado_em',
        'amostra_por_tipo', 'total_documentos', 'total_sentencas',
        'total_prescricoes', 'total_pareceres',
        'presc_texto_livre', 'presc_template',
        'presc_pct_texto_livre', 'presc_pct_template',
        'par_texto_livre', 'par_template',
        'par_pct_texto_livre', 'par_pct_template',
        'caminho_conll', 'caminho_jsonl', 'caminho_anotacao',
        'selecao_phi',
    ],
    'tb_anonclin_execucao_anotacao': [
        'id', 'experimento_id', 'criado_em',
        'total_sentencas_amostra',
        'kappa', 'kappa_meta_atingida', 'concordancia_obs', 'concordancia_esp',
        'total_tokens_kappa',
        'total_sentencas_anotadas', 'distribuicao_entidades_json',
        'caminho_conll_anotado',
    ],
    'tb_anonclin_execucao_divisao': [
        'id', 'experimento_id', 'criado_em',
        'total_treino', 'total_dev', 'total_teste',
        'verificacao_ok', 'ausentes_dev_json', 'ausentes_teste_json',
        'distribuicao_json',
        'caminho_train', 'caminho_dev', 'caminho_teste',
    ],
    'tb_anonclin_execucao_treinamento': [
        'id', 'experimento_id', 'criado_em', 'nome_modelo',
        'hiperparametros_json', 'epochs', 'tempo_treinamento_seg',
        'classes_json', 'caminho_modelo',
    ],
    'tb_anonclin_execucao_avaliacao': [
        'id', 'treinamento_id', 'criado_em',
        'f1_entity_micro', 'f1_por_entidade_json',
        'f1_token_macro', 'f1_token_weighted',
        'relatorio_json',
    ],
    'tb_anonclin_execucao_anonimizacao': [
        'id', 'experimento_id', 'criado_em', 'nome_modelo',
        'total_documentos_anonimizados', 'total_spans_substituidos',
        'distribuicao_marcadores_json',
        'coverage', 'precision_anon', 'levenshtein_ratio',
        'f1_downstream_original', 'f1_downstream_anonimizado',
        'delta_f1', 'delta_f1_por_entidade_json',
        'caminho_corpus_anonimizado',
    ],
    'tb_anonclin_anotador_sessao': [
        'id', 'experimento_id', 'criado_em', 'nome', 'encerrada',
    ],
}

# Colunas que guardam JSON serializado e passam pela sanitização.
COLUNAS_JSON = {
    'especialidades_json', 'selecao_phi', 'distribuicao_entidades_json',
    'ausentes_dev_json', 'ausentes_teste_json', 'distribuicao_json',
    'hiperparametros_json', 'classes_json', 'f1_por_entidade_json',
    'relatorio_json', 'distribuicao_marcadores_json',
    'delta_f1_por_entidade_json',
}

# Tabelas que contêm ou podem conter texto clínico: só entram como contagem.
# `tb_anonclin_anotador_sentenca` guarda os tokens das sentenças reais, é a
# razão de a regra 1 tratar o banco inteiro como PHI.
TABELAS_SO_CONTAGEM = [
    'tb_anonclin_anotador_sentenca',
    'tb_anonclin_anotador_token',
    'tb_anonclin_anotador_adjudicacao',
]


class PHISuspeitoError(RuntimeError):
    """Levantada quando a varredura final encontra string acima do limite."""


def resolver_caminho_banco(cli_path=None):
    """Resolve o banco: --db > env ANONCLIN_DB > raiz do repositório."""
    if cli_path:
        return Path(cli_path).expanduser().resolve()
    if os.environ.get('ANONCLIN_DB'):
        return Path(os.environ['ANONCLIN_DB']).expanduser().resolve()
    raiz_repo = Path(__file__).resolve().parent.parent
    return raiz_repo / 'db.sqlite3'


def conectar_somente_leitura(caminho):
    """Abre em modo read-only real, o SQLite recusa qualquer escrita."""
    if not caminho.exists():
        sys.exit(f'ERRO: banco não encontrado em {caminho}')
    uri = f'file:{caminho.as_posix()}?mode=ro'
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def tabelas_existentes(con):
    cur = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    return {linha['name'] for linha in cur.fetchall()}


def colunas_existentes(con, tabela):
    cur = con.execute(f'PRAGMA table_info("{tabela}")')
    return {linha['name'] for linha in cur.fetchall()}


def sanitizar(valor, profundidade=0):
    """
    Reduz uma estrutura vinda de JSONField ao que é seguro publicar.

    Números, booleanos e nulos passam. Strings curtas passam (são rótulos de
    entidade, nomes de modelo, chaves de dicionário). Strings longas viram um
    marcador com o tamanho original, o dado não vaza, mas fica visível que
    havia algo ali.
    """
    if profundidade > 12:
        return '<PROFUNDIDADE_EXCEDIDA>'
    if valor is None or isinstance(valor, (int, float, bool)):
        return valor
    if isinstance(valor, str):
        if len(valor) > MAX_STR_JSON:
            return f'<STRING_REDIGIDA:{len(valor)}_chars>'
        return valor
    if isinstance(valor, dict):
        return {
            sanitizar(k, profundidade + 1): sanitizar(v, profundidade + 1)
            for k, v in valor.items()
        }
    if isinstance(valor, (list, tuple)):
        return [sanitizar(v, profundidade + 1) for v in valor]
    return f'<TIPO_NAO_SUPORTADO:{type(valor).__name__}>'


def ler_tabela(con, tabela, colunas_pedidas):
    """Lê só as colunas autorizadas que de fato existem no banco."""
    presentes = colunas_existentes(con, tabela)
    colunas = [c for c in colunas_pedidas if c in presentes]
    ausentes = [c for c in colunas_pedidas if c not in presentes]

    lista_sql = ', '.join(f'"{c}"' for c in colunas)
    ordem = 'id' if 'id' in presentes else colunas[0]
    cur = con.execute(f'SELECT {lista_sql} FROM "{tabela}" ORDER BY "{ordem}"')

    linhas = []
    for linha in cur.fetchall():
        registro = {}
        for coluna in colunas:
            valor = linha[coluna]
            if coluna in COLUNAS_JSON and isinstance(valor, str):
                try:
                    valor = sanitizar(json.loads(valor))
                except (json.JSONDecodeError, TypeError):
                    valor = f'<JSON_ILEGIVEL:{len(valor)}_chars>'
            elif isinstance(valor, str) and len(valor) > MAX_STR_SAIDA:
                valor = f'<STRING_REDIGIDA:{len(valor)}_chars>'
            registro[coluna] = valor
        linhas.append(registro)

    return {
        'total': len(linhas),
        'colunas_ausentes_no_banco': ausentes,
        'registros': linhas,
    }


def varrer_saida(no, caminho='raiz'):
    """
    Guarda final: percorre a saída inteira procurando string acima do limite.

    Falha fechada, se algo escapou da sanitização, o script aborta em vez de
    gravar um arquivo possivelmente contaminado.
    """
    if isinstance(no, str):
        if len(no) > MAX_STR_SAIDA:
            raise PHISuspeitoError(
                f'String de {len(no)} chars em {caminho}, acima do limite de '
                f'{MAX_STR_SAIDA}. Extração abortada por precaução.'
            )
    elif isinstance(no, dict):
        for chave, valor in no.items():
            varrer_saida(chave, f'{caminho}.{chave}')
            varrer_saida(valor, f'{caminho}.{chave}')
    elif isinstance(no, list):
        for i, item in enumerate(no):
            varrer_saida(item, f'{caminho}[{i}]')


def montar_extrato(con):
    existentes = tabelas_existentes(con)
    extrato = {
        'gerado_em': datetime.now(timezone.utc).isoformat(),
        'aviso': (
            'Extrato de metadados do AnonClin. Não contém texto clínico: '
            'as tabelas com conteúdo de sentença entram apenas como contagem, '
            'o campo `obs` é excluído de todas as tabelas, e a saída passa por '
            'varredura antes da gravação.'
        ),
        'tabelas': {},
        'contagens_sem_conteudo': {},
        'tabelas_ignoradas': [],
    }

    for tabela, colunas in TABELAS_METADADO.items():
        if tabela in existentes:
            extrato['tabelas'][tabela] = ler_tabela(con, tabela, colunas)
        else:
            extrato['tabelas'][tabela] = {
                'total': 0,
                'ausente_no_banco': True,
                'registros': [],
            }

    for tabela in TABELAS_SO_CONTAGEM:
        if tabela in existentes:
            cur = con.execute(f'SELECT COUNT(*) AS n FROM "{tabela}"')
            extrato['contagens_sem_conteudo'][tabela] = cur.fetchone()['n']
        else:
            extrato['contagens_sem_conteudo'][tabela] = None

    conhecidas = set(TABELAS_METADADO) | set(TABELAS_SO_CONTAGEM)
    extrato['tabelas_ignoradas'] = sorted(
        t for t in existentes
        if t not in conhecidas and not t.startswith('sqlite_')
    )

    return extrato


def resumir(extrato):
    """Resumo curto no terminal, para conferência rápida."""
    experimentos = extrato['tabelas']['tb_anonclin_experimento']
    linhas = [f"Experimentos: {experimentos['total']}"]
    for registro in experimentos['registros']:
        criado = (registro.get('criado_em') or '')[:16]
        linhas.append(f"  [{registro['id']}] {registro.get('nome')}, {criado}")

    linhas.append('')
    linhas.append('Execuções por etapa:')
    for tabela, dados in extrato['tabelas'].items():
        if tabela == 'tb_anonclin_experimento':
            continue
        etapa = tabela.replace('tb_anonclin_', '')
        linhas.append(f'  {etapa:38s} {dados["total"]:>5d}')

    linhas.append('')
    linhas.append('Tabelas lidas apenas como contagem (contêm ou podem conter PHI):')
    for tabela, n in extrato['contagens_sem_conteudo'].items():
        rotulo = 'ausente' if n is None else f'{n} registros'
        linhas.append(f'  {tabela.replace("tb_anonclin_", ""):38s} {rotulo}')

    if extrato['tabelas_ignoradas']:
        linhas.append('')
        linhas.append(
            'Tabelas presentes no banco e não lidas por este script: '
            + ', '.join(extrato['tabelas_ignoradas'])
        )

    return '\n'.join(linhas)


def main():
    parser = argparse.ArgumentParser(
        description='Extrato de metadados do AnonClin (somente leitura, sem PHI).'
    )
    parser.add_argument('--db', help='Caminho do db.sqlite3 (default: raiz do repo).')
    parser.add_argument('--saida', help='Arquivo JSON de saída (default: só resumo no terminal).')
    parser.add_argument('--json', action='store_true', help='Imprime o JSON completo no terminal.')
    args = parser.parse_args()

    caminho = resolver_caminho_banco(args.db)
    con = conectar_somente_leitura(caminho)
    try:
        extrato = montar_extrato(con)
    finally:
        con.close()

    try:
        varrer_saida(extrato)
    except PHISuspeitoError as erro:
        sys.exit(f'ABORTADO: {erro}')

    if args.saida:
        destino = Path(args.saida).expanduser().resolve()
        destino.write_text(
            json.dumps(extrato, ensure_ascii=False, indent=2, default=str),
            encoding='utf-8',
        )
        print(f'Extrato gravado em {destino}\n')

    if args.json:
        print(json.dumps(extrato, ensure_ascii=False, indent=2, default=str))
    else:
        print(f'Banco: {caminho}\n')
        print(resumir(extrato))


if __name__ == '__main__':
    main()
