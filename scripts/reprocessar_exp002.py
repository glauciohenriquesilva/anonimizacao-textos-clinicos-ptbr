#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reexecuta o pré-processamento do Exp 002 com captura de PHI e vínculo de paciente.

    python scripts/reprocessar_exp002.py ^
        --prescricoes caminho\\para\\prescricoes.csv ^
        --pareceres   caminho\\para\\pareceres.csv

Para que serve
==============
O corpus do Exp 002 foi gerado antes das Fases 1 e 2. Ele não tem o mapa de PHI e não tem
o vínculo com o paciente. Sem essas duas coisas, o gerador de surrogates deixa as datas
como placeholder e mantém a consistência de nomes apenas dentro de cada documento, o que
é insuficiente: DATA sozinha responde por cerca de 37% das entidades anotadas.

Este script produz o que falta. Ele roda a mesma pipeline sobre os mesmos CSVs, agora com
`capturar_phi=True` e `propagar_paciente=True`, gravando num diretório separado. Depois,
`scripts/conferir_reprocessamento.py` compara o resultado com o corpus original e diz se
os dois são idênticos. Se forem, o mapa de PHI encaixa nas sentenças já anotadas e nada
precisa ser reanotado.

O que ele não faz
=================
Não sobrescreve nada do Exp 002. A saída vai para `outputs/reprocessamento/` por padrão,
e o corpus de 24/07 que está em `outputs/preprocessamento/` permanece intacto. Também não
registra execução no banco: isto é uma conferência, não um experimento novo.

Sobre os CSVs
=============
Precisam ser os mesmos que geraram o Exp 002. Se forem outros, o corpus vai sair diferente
e a conferência vai acusar, que é justamente o ponto. Enquanto a conferência não passar,
não há garantia de que os arquivos em mãos são os originais.

🔴 O arquivo `*_corpus_phi.jsonl` gerado aqui concentra PHI real em forma estruturada.
Nunca versionar, nunca publicar, nunca sair do perímetro institucional. O .gitignore já
cobre o padrão `*_phi.jsonl`, mas a responsabilidade não é do .gitignore.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'anonclin.settings')

import django  # noqa: E402
django.setup()

from preprocessamento.services.preprocessamento import (  # noqa: E402
    executar_preprocessamento,
)


def main():
    parser = argparse.ArgumentParser(
        description='Reexecuta o pré-processamento do Exp 002 com PHI e paciente.'
    )
    parser.add_argument('--prescricoes', required=True,
                        help='CSV de prescrições usado no Exp 002.')
    parser.add_argument('--pareceres', required=True,
                        help='CSV de pareceres usado no Exp 002.')
    parser.add_argument('--saida', default='outputs/reprocessamento',
                        help='Diretório de saída (default outputs/reprocessamento).')
    parser.add_argument('--prefixo', default='Experimento_002_reproc_',
                        help='Prefixo dos arquivos gerados.')
    parser.add_argument('--n-anotacao', type=int, default=5000,
                        help='Total de sentenças da seleção estratificada. O Exp 002 usou '
                             '5000. Só afeta o corpus_anotacao.jsonl, que aqui é '
                             'subproduto.')
    args = parser.parse_args()

    for rotulo, caminho in (('prescricoes', args.prescricoes),
                            ('pareceres', args.pareceres)):
        if not os.path.exists(caminho):
            sys.exit(f'CSV de {rotulo} nao encontrado: {caminho}')

    os.makedirs(args.saida, exist_ok=True)
    caminho_conll = os.path.join(args.saida, f'{args.prefixo}corpus.conll')
    caminho_jsonl = os.path.join(args.saida, f'{args.prefixo}corpus.jsonl')

    print('Reprocessando com capturar_phi=True e propagar_paciente=True')
    print(f'  prescricoes : {args.prescricoes}')
    print(f'  pareceres   : {args.pareceres}')
    print(f'  saida       : {os.path.abspath(args.saida)}')
    print()

    inicio = time.time()
    resultado = executar_preprocessamento(
        arquivo_prescricoes=args.prescricoes,
        arquivo_pareceres=args.pareceres,
        caminho_conll=caminho_conll,
        caminho_jsonl=caminho_jsonl,
        amostra=None,
        n_total_anotacao=args.n_anotacao,
        capturar_phi=True,
        propagar_paciente=True,
    )
    duracao = time.time() - inicio

    caminho_phi = caminho_jsonl[:-len('.jsonl')] + '_phi.jsonl'

    print('RESULTADO')
    print('---------')
    print(f"  documentos   : {resultado['total_documentos']}")
    print(f"  prescricoes  : {resultado['total_prescricoes']}")
    print(f"  pareceres    : {resultado['total_pareceres']}")
    print(f"  sentencas    : {resultado['total_sentencas']}")
    print(f'  duracao      : {duracao / 60:.1f} min')
    print()
    print('ARQUIVOS')
    print('--------')
    print(f'  corpus  : {caminho_jsonl}')
    print(f'  conll   : {caminho_conll}')
    print(f"  anotacao: {resultado['caminho_anotacao']}")
    if os.path.exists(caminho_phi):
        print(f'  mapa PHI: {caminho_phi}   <-- ARQUIVO SENSIVEL, nao versionar')
    else:
        print('  mapa PHI: NAO FOI GERADO. Verifique se capturar_phi chegou ate a '
              'exportacao.')

    print()
    print('Confira agora se este corpus reproduz o do Exp 002:')
    print()
    print('  python scripts/conferir_reprocessamento.py \\')
    print('      --antigo outputs/preprocessamento/Experimento_002_corpus.jsonl \\')
    print(f'      --novo {caminho_jsonl} \\')
    print('      --sessao 5')
    return 0


if __name__ == '__main__':
    sys.exit(main())
