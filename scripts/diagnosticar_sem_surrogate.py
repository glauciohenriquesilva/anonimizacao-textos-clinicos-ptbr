# -*- coding: utf-8 -*-
"""
Conta, por tipo de PHI, quantas substituições devolveram o próprio valor original.

O gerador avisa quando um item do mapa de PHI sai igual ao que entrou, porque nesse caso
o valor real continua no corpus. Este script abre esse aviso por tipo e por modo, para
separar duas situações bem diferentes: um tipo que o gerador não sabe tratar, que é
defeito, e uma coincidência do sorteio, que é ruído.

Somente leitura. Imprime apenas contagens: nenhum valor de PHI vai para o terminal.

Uso:
    python scripts/diagnosticar_sem_surrogate.py --sessao 5 \
        --phi outputs/reprocessamento/Experimento_002_reproc_corpus_phi.jsonl
"""

import argparse
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'anonclin.settings')

import django  # noqa: E402
django.setup()

from anonimizacao.services.aplicar_surrogates import _coletar_substituicoes  # noqa: E402
from anonimizacao.services.leitor_gold import carregar_gold  # noqa: E402
from anonimizacao.services.surrogates import (  # noqa: E402
    GeradorSurrogates,
    deslocar_data_livre,
)


def forma(valor):
    """
    Reduz um valor ao seu formato: dígito vira 9, letra vira a, o resto fica.

    '12/03' vira '99/99' e 'março' vira 'aaaaa'. O formato mostra por que o gerador não
    reconheceu o valor sem revelar o valor.
    """
    return re.sub(r'[^\W\d_]', 'a', re.sub(r'\d', '9', valor or ''))


def listar_formas(gold, tipo_alvo, origem_alvo, limite=60):
    """Conta os formatos dos valores de um tipo. Nenhum valor é impresso."""
    descartavel = {'sobreposicao': 0, 'posicao_invalida': 0, 'token_inesperado': 0}
    formas = Counter()
    reconhecidos = 0
    for sentenca in gold:
        for sub in _coletar_substituicoes(sentenca['tokens'], sentenca['labels'],
                                         sentenca.get('phi'), descartavel):
            if sub['tipo'] == tipo_alvo and sub['origem'] == origem_alvo:
                # Só interessam os formatos que o gerador ainda não sabe deslocar.
                if deslocar_data_livre(sub['original'], 1) is not None:
                    reconhecidos += 1
                    continue
                formas[forma(sub['original'])] += 1
    print()
    print(f'{tipo_alvo} com origem {origem_alvo}: {reconhecidos} itens em formato '
          f'reconhecido, {sum(formas.values())} nao reconhecidos')
    print(f'FORMATOS NAO RECONHECIDOS ({len(formas)} formatos)')
    for texto, quantidade in formas.most_common(limite):
        print(f'  {quantidade:>5}  {texto}')
    resto = sum(q for _, q in formas.most_common()[limite:])
    if resto:
        print(f'  {resto:>5}  (demais formatos)')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sessao', type=int, required=True)
    parser.add_argument('--phi', required=True)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--formas', action='store_true',
                        help='Lista os formatos das datas anotadas a mao, em vez da '
                             'tabela por tipo.')
    args = parser.parse_args()

    gold, _ = carregar_gold(args.sessao, None, args.phi)
    gold = [s for s in gold if s['sentenca_idx'] is not None and s['hash_paciente']]
    print(f'sentencas consideradas: {len(gold)}')

    if args.formas:
        listar_formas(gold, 'DATA', 'anotacao')
        return

    for modo in (GeradorSurrogates.MODO_VEROSSIMIL, GeradorSurrogates.MODO_PLACEHOLDER,
                 GeradorSurrogates.MODO_CELEBRIDADE):
        gerador = GeradorSurrogates(seed=args.seed, modo=modo)
        total = Counter()       # itens por (origem, tipo)
        iguais = Counter()      # itens em que o surrogate saiu igual ao original
        descartavel = {'sobreposicao': 0, 'posicao_invalida': 0, 'token_inesperado': 0}

        for sentenca in gold:
            chave = sentenca['hash_paciente']
            for sub in _coletar_substituicoes(sentenca['tokens'], sentenca['labels'],
                                             sentenca.get('phi'), descartavel):
                rotulo = (sub['origem'], sub['tipo'])
                total[rotulo] += 1
                if gerador.gerar(sub['tipo'], sub['original'], chave) == sub['original']:
                    iguais[rotulo] += 1

        print()
        print(f'MODO {modo}')
        print(f"  {'origem':<10} {'tipo':<14} {'itens':>7} {'iguais':>7} {'%':>6}")
        for rotulo in sorted(total):
            n, k = total[rotulo], iguais[rotulo]
            print(f'  {rotulo[0]:<10} {rotulo[1]:<14} {n:>7} {k:>7} {100 * k / n:>5.1f}%')


if __name__ == '__main__':
    main()
