#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auditoria das sequências BIO do corpus anotado.

    python scripts/conferir_gold.py --sessao 5

Verifica se a anotação obedece ao esquema BIO. A regra é simples: um token marcado como
`I-TIPO` só faz sentido se o token anterior for `B-TIPO` ou `I-TIPO` do mesmo tipo. Um
`I-` que aparece sozinho, ou logo depois de um tipo diferente, descreve uma entidade que
começa no meio, o que não existe.

Por que isso importa
====================
A tela de anotação deixa marcar qualquer label em qualquer token, sem verificar a
sequência. É cômodo para anotar rápido, mas permite gravar combinações inválidas, e nada
no caminho entre o clique e o arquivo CoNLL reclama.

O efeito aparece depois, em dois lugares:

  No treinamento, o modelo recebe exemplos de uma estrutura que o esquema não admite, e
  aprende a reproduzi-la.

  Na avaliação, o `seqeval` precisa decidir o que fazer com um `I-` órfão. Em modo IOB2
  ele costuma tratá-lo como início de entidade, o que significa que a métrica está
  medindo uma entidade que o anotador não marcou como tal.

Nenhum dos dois quebra de forma visível. Os dois deslocam o resultado em silêncio, que é
o motivo de valer a pena olhar.

Este script apenas relata. Corrigir o gold standard é decisão de quem anotou, porque
significa alterar o gabarito do experimento.
"""

import argparse
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'anonclin.settings')

import django  # noqa: E402
django.setup()

from anonimizacao.services.leitor_gold import (  # noqa: E402
    carregar_gold,
    descrever_relatorio,
)


def analisar(sentencas):
    """
    Percorre o corpus procurando sequências BIO inválidas.

    Devolve a lista de ocorrências e um resumo por tipo de entidade.
    """
    ocorrencias = []
    por_tipo = Counter()
    por_sentenca = defaultdict(int)
    labels_usadas = Counter()

    for sentenca in sentencas:
        tokens = sentenca['tokens']
        labels = sentenca['labels']
        labels_usadas.update(labels)

        if len(tokens) != len(labels):
            ocorrencias.append({
                'tipo_problema': 'tamanho',
                'doc_id':        sentenca['doc_id'],
                'ordem':         sentenca['ordem'],
                'detalhe':       f'{len(tokens)} tokens para {len(labels)} labels',
            })
            continue

        anterior = 'O'
        for posicao, label in enumerate(labels):
            if label.startswith('I-'):
                tipo = label[2:]
                if anterior not in (f'B-{tipo}', f'I-{tipo}'):
                    ocorrencias.append({
                        'tipo_problema': 'I_sem_B',
                        'sentenca_pk':   sentenca.get('sentenca_pk'),
                        'doc_id':        sentenca['doc_id'],
                        'ordem':         sentenca['ordem'],
                        'posicao':       posicao,
                        'label':         label,
                        'label_anterior': anterior,
                        'entidade':      tipo,
                        'token':         tokens[posicao],
                    })
                    por_tipo[tipo] += 1
                    por_sentenca[sentenca['ordem']] += 1
            anterior = label

    return ocorrencias, por_tipo, por_sentenca, labels_usadas


def main():
    parser = argparse.ArgumentParser(
        description='Audita as sequências BIO do corpus anotado.'
    )
    parser.add_argument('--sessao', type=int, required=True)
    parser.add_argument('--anotador', type=int, default=None)
    parser.add_argument('--listar', type=int, default=15,
                        help='Quantas ocorrências detalhar (default 15).')
    args = parser.parse_args()

    print(f'Lendo a sessao {args.sessao}...')
    gold, contagem = carregar_gold(args.sessao, args.anotador)
    print(descrever_relatorio(contagem))

    ocorrencias, por_tipo, por_sentenca, labels_usadas = analisar(gold)

    total_tokens = sum(len(s['tokens']) for s in gold)
    total_entidades = sum(1 for s in gold for l in s['labels'] if l.startswith('B-'))

    print()
    print('CORPUS')
    print('------')
    print(f'  sentencas          : {len(gold)}')
    print(f'  tokens             : {total_tokens}')
    print(f'  entidades (B-)     : {total_entidades}')
    print()
    print('  distribuicao de labels:')
    for label, quantidade in sorted(labels_usadas.items(),
                                    key=lambda item: -item[1]):
        if label == 'O':
            continue
        print(f'    {label:<18} {quantidade:>6}')

    print()
    print('SEQUENCIAS INVALIDAS')
    print('--------------------')
    if not ocorrencias:
        print('  nenhuma. O corpus obedece ao esquema BIO.')
        return 0

    print(f'  ocorrencias        : {len(ocorrencias)}')
    print(f'  sentencas afetadas : {len(por_sentenca)} de {len(gold)} '
          f'({len(por_sentenca) / len(gold) * 100:.2f}%)')
    print()
    print('  por tipo de entidade:')
    for tipo, quantidade in por_tipo.most_common():
        # Quantos B- existem desse tipo, para dimensionar o problema
        b_do_tipo = sum(1 for s in gold for l in s['labels'] if l == f'B-{tipo}')
        proporcao = f'{quantidade / b_do_tipo * 100:.1f}% dos B-' if b_do_tipo else 'sem B-'
        print(f'    {tipo:<14} {quantidade:>5}   ({proporcao})')

    print()
    print(f'  primeiras {args.listar} ocorrencias:')
    for item in ocorrencias[:args.listar]:
        if item['tipo_problema'] == 'tamanho':
            print(f"    doc {item['doc_id']}, sentenca {item['ordem']}: {item['detalhe']}")
        else:
            print(f"    doc {item['doc_id']}, sentenca {item['ordem']}, "
                  f"posicao {item['posicao']}: {item['label']} "
                  f"depois de {item['label_anterior']}")

    # Agrupa por sentenca para que a revisao seja feita de uma vez em cada uma,
    # em vez de abrir a mesma sentenca varias vezes
    print()
    print('SENTENCAS A REVISAR')
    print('-------------------')
    print(f'  Abra cada uma na interface de anotacao e confira as posicoes indicadas.')
    print(f'  O endereco tem o formato /anotador/{args.sessao}/anotar/<id>/')
    print()
    agrupadas = defaultdict(list)
    for item in ocorrencias:
        if item['tipo_problema'] == 'I_sem_B':
            agrupadas[(item['sentenca_pk'], item['doc_id'], item['ordem'])].append(item)

    for (pk, doc_id, ordem), itens in sorted(agrupadas.items(), key=lambda x: x[0][2]):
        posicoes = ', '.join(str(i['posicao']) for i in itens)
        tipos = ', '.join(sorted({i['entidade'] for i in itens}))
        print(f'  sentenca {ordem:>5} (doc {doc_id}, id {pk})')
        print(f'      /anotador/{args.sessao}/anotar/{pk}/')
        print(f'      {len(itens)} ocorrencia(s) em {tipos}, nas posicoes {posicoes}')

    print()
    print('O QUE FAZER')
    print('-----------')
    print('  Um I- orfao quase sempre significa uma destas duas coisas:')
    print()
    print('  1. A entidade comeca ali e o anotador marcou I- em vez de B-.')
    print('     Nesse caso a correcao e trocar por B- e o span fica certo.')
    print()
    print('  2. O B- correspondente foi apagado ou nunca chegou a ser gravado.')
    print('     Nesse caso a entidade esta incompleta e precisa ser reanotada.')
    print()
    print('  Os dois casos se distinguem olhando o texto, entao a decisao e de quem')
    print('  anotou. Corrigir automaticamente trocando todo I- orfao por B- resolveria')
    print('  o formato, mas assumiria que o caso 1 vale sempre, e isso mudaria o')
    print('  gabarito do experimento sem ninguem ter olhado.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
