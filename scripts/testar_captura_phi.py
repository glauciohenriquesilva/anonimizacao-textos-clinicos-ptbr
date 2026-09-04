#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste da captura de PHI estrutural (Fase 1 da extensão de corpus com surrogates).

Roda somente sobre casos SINTÉTICOS escritos à mão. Nenhum dado real é lido, nenhum
banco é acessado. Pode ser executado a qualquer momento, em qualquer máquina.

    python scripts/testar_captura_phi.py

O que ele verifica:

  1. NÃO-REGRESSÃO: `normalizar_texto(t)` sem coletor continua produzindo placeholders
     simples ('__DATA__'). Se isto quebrar, todo o corpus do Exp 002 muda.
  2. ROUND-TRIP: desnumerar a saída com coletor devolve exatamente a saída sem coletor.
     É esta igualdade que garante que o corpus exportado não muda quando a captura liga.
  3. COBERTURA: com coletor, nenhum placeholder fica órfão (sem número). Um órfão
     significa PHI mascarado cujo valor original se perdeu.
  4. RECONSTRUÇÃO: os valores capturados, aplicados de volta às posições registradas,
     reconstituem o texto normalizado original.
  5. FALSOS POSITIVOS: o que a pipeline deliberadamente NÃO mascara (RG e CEP que
     parecem telefone) continua não sendo mascarado nem registrado.

Saída: relatório no terminal e código de saída 0 (tudo ok) ou 1 (alguma falha).
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from preprocessamento.services.preprocessamento import (  # noqa: E402
    normalizar_texto,
    desnumerar_placeholders,
    extrair_phi_da_sentenca,
    limpar_tokens_numerados,
    tokenizar_word_level,
)

# ---------------------------------------------------------------------------
# Casos sintéticos. Nenhum dado real: números e nomes são inventados.
# ---------------------------------------------------------------------------

CASOS = [
    "Paciente atendido em 12/05/2025 as 14h30 pelo Dr. Souza.",
    "Retorno agendado para 03/08/2024 07:09:30 na sala 2.",
    "Contato da filha: (27) 99706.2830 e tambem 27 99612 - 0360.",
    "TEL 27 33767-7523 / celular 998387639 / fixo 33366997",
    "CPF 12345678901 e outro 123.456.789-00 no mesmo texto.",
    "Reside na RUA das Flores, CEP 29160-021, bairro Centro.",
    "END 29160021 confirmado pelo acompanhante.",
    "Enviar para exemplo.paciente@provedor.com.br ate 2025-01-05.",
    "Consulta 07:09, retorno 15:30HS, alta as 9 horas.",
    "Evolucao em 2026-08-04 07:09 e novo registro 2026-08-05 08:10:15.",
    "Datas soltas: 01/02, 2024, 15/03/2023 e 2023-12-25.",
    "PA: 120x80 FC. 88bpm TAX 36.5C - sem PHI nesta sentenca.",
    "Sem nenhum identificador nesta sentenca clinica.",
    "",
]

# Casos em que a pipeline NÃO deve mascarar. São proteções deliberadas contra
# falso positivo, documentadas em mascarar_telefone() (Task #25, 24/07/2026).
CASOS_NAO_MASCARAR = [
    ("RG : 978466517 nao e telefone.", "978466517"),
    ("CEP : 2916 - 0021 tambem nao e telefone.", "2916 - 0021"),
]

RE_ORFAO = re.compile(r'__[A-Z]+__')
RE_NUMERADO = re.compile(r'__[A-Z]+_\d{4}__')


def _falhar(relatorio, teste, detalhe):
    relatorio.append((teste, detalhe))


def main():
    falhas = []

    # --- 1. Não-regressão -------------------------------------------------
    for texto in CASOS:
        saida = normalizar_texto(texto)
        if RE_NUMERADO.search(saida):
            _falhar(falhas, 'nao-regressao',
                    f'placeholder numerado sem coletor em {texto!r} -> {saida!r}')

    # --- 2. Round-trip ----------------------------------------------------
    for texto in CASOS:
        coletor = []
        com_captura = normalizar_texto(texto, coletor)
        if desnumerar_placeholders(com_captura) != normalizar_texto(texto):
            _falhar(falhas, 'round-trip',
                    f'{texto!r}: {desnumerar_placeholders(com_captura)!r} != '
                    f'{normalizar_texto(texto)!r}')

    # --- 3. Cobertura -----------------------------------------------------
    for texto in CASOS:
        coletor = []
        com_captura = normalizar_texto(texto, coletor)
        orfaos = RE_ORFAO.findall(RE_NUMERADO.sub('', com_captura))
        if orfaos:
            _falhar(falhas, 'cobertura',
                    f'PHI mascarado sem valor preservado em {texto!r}: {orfaos}')

    # --- 4. Reconstrução --------------------------------------------------
    total_phi = 0
    for texto in CASOS:
        if not texto:
            continue
        coletor = []
        com_captura = normalizar_texto(texto, coletor)
        tokens_numerados = tokenizar_word_level(com_captura)
        phi = extrair_phi_da_sentenca(tokens_numerados, coletor)
        tokens = limpar_tokens_numerados(tokens_numerados)
        total_phi += len(phi)

        for item in phi:
            if not tokens[item['posicao']].startswith('__'):
                _falhar(falhas, 'reconstrucao',
                        f'posicao {item["posicao"]} nao aponta para placeholder '
                        f'em {texto!r}')
                continue
            tokens[item['posicao']] = item['valor']

        # O texto reconstruído deve conter cada valor original de volta
        reconstruido = ' '.join(tokens)
        for item in phi:
            if item['valor'] not in reconstruido:
                _falhar(falhas, 'reconstrucao',
                        f'valor {item["valor"]!r} nao voltou ao texto de {texto!r}')

    # --- 5. Falsos positivos protegidos -----------------------------------
    for texto, trecho in CASOS_NAO_MASCARAR:
        coletor = []
        saida = normalizar_texto(texto, coletor)
        if trecho not in saida:
            _falhar(falhas, 'falso-positivo',
                    f'{trecho!r} foi mascarado indevidamente em {texto!r} -> {saida!r}')
        if any(d['valor'] == trecho for d in coletor):
            _falhar(falhas, 'falso-positivo',
                    f'{trecho!r} foi registrado no coletor sem ter sido mascarado')

    # --- Relatório --------------------------------------------------------
    print(f'Casos testados            : {len(CASOS)}')
    print(f'Casos de nao-mascaramento : {len(CASOS_NAO_MASCARAR)}')
    print(f'PHI capturado e religado  : {total_phi}')
    print()

    if not falhas:
        print('TODOS OS TESTES PASSARAM')
        print()
        print('  [ok] nao-regressao : sem coletor, saida identica a de antes')
        print('  [ok] round-trip    : desnumerar devolve a saida sem coletor')
        print('  [ok] cobertura     : nenhum PHI mascarado ficou sem valor preservado')
        print('  [ok] reconstrucao  : valores voltam as posicoes corretas')
        print('  [ok] falso-positivo: RG e CEP protegidos seguem intocados')
        return 0

    print(f'FALHARAM {len(falhas)} verificacoes:')
    for teste, detalhe in falhas:
        print(f'  [{teste}] {detalhe}')
    return 1


if __name__ == '__main__':
    sys.exit(main())
