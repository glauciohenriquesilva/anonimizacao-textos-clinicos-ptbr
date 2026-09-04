#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste do gerador de surrogates e da sua aplicação sobre o corpus.

    python scripts/testar_surrogates.py

Roda inteiramente sobre um corpus sintético escrito à mão. Não lê banco, não abre
arquivo de dado, não precisa de Django. Pode ser executado a qualquer momento.

O que ele verifica:

  1. CONSISTÊNCIA: a mesma pessoa recebe sempre o mesmo nome fictício, e um homônimo
     que é outra pessoa recebe um nome diferente. É a regra combinada com o orientador.
  2. VARIAÇÃO ENTRE VERSÕES: mudar a semente muda todos os surrogates, que é o que
     permite gerar N versões do mesmo corpus.
  3. INTERVALOS DE DATA: o deslocamento é fixo por paciente, então a distância entre
     dois atendimentos do mesmo paciente sobrevive à substituição.
  4. NUNCA IGUAL AO ORIGINAL: um surrogate idêntico ao valor real não anonimiza nada.
  5. ALINHAMENTO: depois da substituição, cada sentença continua com uma label por
     token e as sequências BIO seguem válidas, mesmo quando o surrogate tem um número
     de tokens diferente do original.
  6. NADA DE PHI PARA TRÁS: nenhum placeholder sobra no corpus gerado, e o gerador não
     encontrou nenhum tipo que não saiba tratar.

Saída: relatório no terminal e código de saída 0 (tudo certo) ou 1 (alguma falha).
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anonimizacao.services.surrogates import GeradorSurrogates  # noqa: E402
from anonimizacao.services.aplicar_surrogates import (  # noqa: E402
    gerar_corpus,
    conferir_alinhamento,
)

# ---------------------------------------------------------------------------
# Corpus sintético. Nenhum dado real: todos os nomes e números são inventados.
#
# Reproduz a estrutura que o corpus verdadeiro tem depois das Fases 1 e 2:
#   tokens        já normalizados, com placeholder no lugar do PHI de regex
#   labels        anotação BIO do gold standard
#   hash_paciente identidade do paciente, vinda da Fase 2
#   phi           valores originais do PHI de regex, vindos da Fase 1
# ---------------------------------------------------------------------------

CORPUS = [
    {'doc_id': 1, 'hash_paciente': 'pacA', 'sentenca_idx': 0,
     'tokens': ['Paciente', 'JOAO', 'DA', 'SILVA', ',', 'atendido', 'em', '__DATA__',
                'no', 'HOSPITAL', 'SANTA', 'CASA', '.'],
     'labels': ['O', 'B-PESSOA', 'I-PESSOA', 'I-PESSOA', 'O', 'O', 'O', 'O',
                'O', 'B-INSTITUICAO', 'I-INSTITUICAO', 'I-INSTITUICAO', 'O'],
     'phi': [{'posicao': 7, 'tipo': 'DATA', 'valor': '2025-01-10'}]},

    {'doc_id': 1, 'hash_paciente': 'pacA', 'sentenca_idx': 1,
     'tokens': ['Retorno', 'de', 'JOAO', 'DA', 'SILVA', 'em', '__DATA__', '.'],
     'labels': ['O', 'O', 'B-PESSOA', 'I-PESSOA', 'I-PESSOA', 'O', 'O', 'O'],
     'phi': [{'posicao': 6, 'tipo': 'DATA', 'valor': '2025-01-17'}]},

    # Homônimo: mesmo nome escrito, outra pessoa
    {'doc_id': 2, 'hash_paciente': 'pacB', 'sentenca_idx': 0,
     'tokens': ['JOAO', 'DA', 'SILVA', 'reside', 'na', 'RUA', 'DAS', 'FLORES',
                ',', 'tel', '__TELEFONE__', '.'],
     'labels': ['B-PESSOA', 'I-PESSOA', 'I-PESSOA', 'O', 'O', 'B-ENDERECO',
                'I-ENDERECO', 'I-ENDERECO', 'O', 'O', 'O', 'O'],
     'phi': [{'posicao': 10, 'tipo': 'TELEFONE', 'valor': '(27) 99706-2830'}]},

    # Nome de uma parte só e instituição em sigla
    {'doc_id': 3, 'hash_paciente': 'pacC', 'sentenca_idx': 0,
     'tokens': ['ANA', 'encaminhada', 'ao', 'HEUE', 'em', '__DATA__', '.'],
     'labels': ['B-PESSOA', 'O', 'O', 'B-INSTITUICAO', 'O', 'O', 'O'],
     'phi': [{'posicao': 5, 'tipo': 'DATA', 'valor': '2025-06-01'}]},

    # Sentença sem PHI nenhum, para garantir que passa intacta
    {'doc_id': 3, 'hash_paciente': 'pacC', 'sentenca_idx': 1,
     'tokens': ['Paciente', 'estavel', ',', 'dieta', 'zero', 'mantida', '.'],
     'labels': ['O'] * 7,
     'phi': []},
]


def texto_da_entidade(sentenca, sufixo):
    """Junta os tokens cuja label termina no tipo pedido, para conferir consistência."""
    return ' '.join(
        token for token, label in zip(sentenca['tokens'], sentenca['labels'])
        if label.endswith(sufixo)
    )


def main():
    falhas = []

    def registrar(teste, detalhe):
        falhas.append((teste, detalhe))

    gerador = GeradorSurrogates(seed=1)
    corpus, relatorio = gerar_corpus(CORPUS, gerador)

    # --- 1. Consistência por identidade -----------------------------------
    pessoa_a0 = texto_da_entidade(corpus[0], 'PESSOA')
    pessoa_a1 = texto_da_entidade(corpus[1], 'PESSOA')
    pessoa_b = texto_da_entidade(corpus[2], 'PESSOA')

    if pessoa_a0 != pessoa_a1:
        registrar('consistencia',
                  f'mesmo paciente recebeu nomes diferentes: {pessoa_a0!r} e {pessoa_a1!r}')
    if pessoa_a0 == pessoa_b:
        registrar('consistencia',
                  f'homonimos de pacientes distintos receberam o mesmo nome: {pessoa_b!r}')

    # --- 2. Variação entre versões ----------------------------------------
    outra_versao, _ = gerar_corpus(CORPUS, GeradorSurrogates(seed=2))
    if texto_da_entidade(outra_versao[0], 'PESSOA') == pessoa_a0:
        registrar('variacao',
                  'a semente 2 produziu o mesmo nome da semente 1')

    # --- 3. Intervalos de data preservados --------------------------------
    def data_da_sentenca(sentenca):
        for token in sentenca['tokens']:
            try:
                return date.fromisoformat(token)
            except ValueError:
                continue
        return None

    d0, d1 = data_da_sentenca(corpus[0]), data_da_sentenca(corpus[1])
    if d0 is None or d1 is None:
        registrar('datas', 'as datas substituidas nao foram encontradas no corpus gerado')
    else:
        intervalo_original = (date(2025, 1, 17) - date(2025, 1, 10)).days
        if (d1 - d0).days != intervalo_original:
            registrar('datas',
                      f'intervalo mudou: {intervalo_original} dias viraram {(d1 - d0).days}')

    # --- 4. Nenhum surrogate igual ao original ----------------------------
    originais = {'JOAO DA SILVA', 'ANA', 'HOSPITAL SANTA CASA', 'HEUE',
                 'RUA DAS FLORES', '2025-01-10', '2025-01-17', '2025-06-01',
                 '(27) 99706-2830'}
    for indice, sentenca in enumerate(corpus):
        texto = ' '.join(sentenca['tokens'])
        for valor in originais:
            if valor in texto:
                registrar('valor-original',
                          f'sentenca {indice} ainda contem o valor real {valor!r}')

    # --- 5. Alinhamento de tokens e labels --------------------------------
    for problema in conferir_alinhamento(corpus):
        registrar('alinhamento', problema)

    # --- 6. Nada de PHI para tras -----------------------------------------
    if relatorio['placeholders_restantes']:
        registrar('placeholder',
                  f"{relatorio['placeholders_restantes']} placeholders sobraram no corpus")
    if relatorio['gerador']['tipos_nao_suportados']:
        registrar('tipo',
                  f"tipos sem tratamento: {relatorio['gerador']['tipos_nao_suportados']}")
    if relatorio['gerador']['colisoes_nao_resolvidas']:
        registrar('colisao',
                  f"{relatorio['gerador']['colisoes_nao_resolvidas']} valores nao puderam "
                  f"ser diferenciados do original (catalogo pequeno demais)")

    # --- Relatório ---------------------------------------------------------
    print('CORPUS GERADO')
    print('-------------')
    for antes, depois in zip(CORPUS, corpus):
        print()
        print('  original :', ' '.join(antes['tokens']))
        print('  surrogate:', ' '.join(depois['tokens']))

    print()
    print('NUMEROS')
    print('-------')
    print(f"  sentencas               : {relatorio['sentencas']}")
    print(f"  entidades distintas     : {relatorio['gerador']['entidades_distintas']}")
    print(f"  pacientes com shift     : {relatorio['gerador']['pacientes_com_shift']}")
    print(f"  colisoes evitadas       : {relatorio['gerador']['colisoes_evitadas']}")
    print(f"  placeholders restantes  : {relatorio['placeholders_restantes']}")
    for nome, valor in relatorio['avisos'].items():
        if valor:
            print(f'  aviso {nome:<18}: {valor}')

    print()
    if not falhas:
        print('TODOS OS TESTES PASSARAM')
        print()
        print('  [ok] consistencia   : mesma pessoa recebe o mesmo nome, homonimo recebe outro')
        print('  [ok] variacao       : sementes diferentes produzem versoes diferentes')
        print('  [ok] datas          : intervalos entre atendimentos preservados')
        print('  [ok] valor-original : nenhum valor real sobrou no corpus')
        print('  [ok] alinhamento    : uma label por token, sequencias BIO validas')
        print('  [ok] placeholder    : nenhum PHI de regex ficou sem substituicao')
        return 0

    print(f'FALHARAM {len(falhas)} verificacoes:')
    for teste, detalhe in falhas:
        print(f'  [{teste}] {detalhe}')
    return 1


if __name__ == '__main__':
    sys.exit(main())
