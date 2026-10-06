# -*- coding: utf-8 -*-
"""
Gera o braço A do experimento: o corpus real, sobre as mesmas sentenças dos surrogates.

O corpus anotado guarda datas, telefones e outros identificadores estruturais como
marcadores (__DATA__, __TELEFONE__). Usá-lo assim como braço A seria injusto: o braço B
tem uma data fictícia onde o A teria um marcador, e a diferença entre os dois deixaria de
ser só o valor do identificador. Aqui o valor real volta para o lugar do marcador, pelo
mesmo caminho de código que produz os surrogates.

Lê `sentencas_usadas.json` da pasta de saída, de modo que o braço A tenha exatamente as
sentenças dos outros braços, na mesma ordem. Linha N de `corpus_real.jsonl` corresponde
à linha N de `corpus_v01.jsonl`.

Grava também `grupos_paciente.json`: para cada linha, um número que identifica o
paciente. É o que permite dividir treino e teste por paciente. O número é um contador,
não o hash, e não tem relação com o prontuário.

ATENCAO: `corpus_real.jsonl` contém texto clínico real, com nomes e datas verdadeiros.
Fica em outputs/, que o .gitignore cobre. Nunca copiar, anexar ou versionar.

Uso:
    python scripts/gerar_braco_real.py --sessao 5 \
        --phi outputs/reprocessamento/Experimento_002_reproc_corpus_phi.jsonl \
        --saida outputs/surrogates_exp004
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'anonclin.settings')

import django  # noqa: E402
django.setup()

from anonimizacao.services.aplicar_surrogates import (  # noqa: E402
    conferir_alinhamento,
    gerar_corpus,
)
from anonimizacao.services.leitor_gold import carregar_gold  # noqa: E402
from anonimizacao.services.registro_surrogates import hash_arquivo  # noqa: E402
from anonimizacao.services.surrogates import GeradorSurrogates  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description='Gera o braco A (corpus real).')
    parser.add_argument('--sessao', type=int, required=True)
    parser.add_argument('--phi', required=True)
    parser.add_argument('--saida', required=True,
                        help='Pasta de uma geracao de surrogates ja concluida.')
    args = parser.parse_args()

    caminho_usadas = os.path.join(args.saida, 'sentencas_usadas.json')
    if not os.path.exists(caminho_usadas):
        sys.exit(f'{caminho_usadas} nao existe. Gere os surrogates com --so-casadas antes.')
    with open(caminho_usadas, encoding='utf-8') as arquivo:
        usadas = set(json.load(arquivo))

    gold, _ = carregar_gold(args.sessao, None, args.phi)
    gold = [s for s in gold if s['sentenca_pk'] in usadas]
    if len(gold) != len(usadas):
        sys.exit(f'Esperava {len(usadas)} sentencas e encontrei {len(gold)}. A sessao '
                 'mudou desde a geracao dos surrogates?')

    gerador = GeradorSurrogates(seed=0, modo=GeradorSurrogates.MODO_ORIGINAL)
    corpus, relatorio = gerar_corpus(gold, gerador)
    problemas = conferir_alinhamento(corpus)

    # Mesma conferência de ordem que protege a comparação linha a linha entre os braços.
    caminho_v01 = os.path.join(args.saida, 'corpus_v01.jsonl')
    divergencias = 0
    if os.path.exists(caminho_v01):
        with open(caminho_v01, encoding='utf-8') as arquivo:
            linhas = [json.loads(linha) for linha in arquivo]
        divergencias = abs(len(linhas) - len(corpus))
        for sentenca, outro in zip(corpus, linhas):
            # Mesmo documento e mesma quantidade de entidades anotadas na mesma linha.
            entidades_a = sum(1 for label in sentenca['labels'] if label.startswith('B-'))
            entidades_b = sum(1 for label in outro['labels'] if label.startswith('B-'))
            if outro['doc_id'] != sentenca['doc_id'] or entidades_a != entidades_b:
                divergencias += 1

    caminho = os.path.join(args.saida, 'corpus_real.jsonl')
    with open(caminho, 'w', encoding='utf-8') as arquivo:
        for sentenca in corpus:
            arquivo.write(json.dumps({
                'doc_id':   sentenca['doc_id'],
                'doc_type': sentenca['doc_type'],
                'tokens':   sentenca['tokens'],
                'labels':   sentenca['labels'],
            }, ensure_ascii=False) + '\n')

    numeros = {}
    grupos = [numeros.setdefault(s['hash_paciente'], len(numeros)) for s in gold]
    with open(os.path.join(args.saida, 'grupos_paciente.json'), 'w',
              encoding='utf-8') as arquivo:
        json.dump(grupos, arquivo)

    resumo = {
        'sentencas':              len(corpus),
        'pacientes':              len(numeros),
        'placeholders_restantes': relatorio['placeholders_restantes'],
        'problemas_alinhamento':  len(problemas),
        'ordem_divergente_de_v01': divergencias,
        'avisos':                 relatorio['avisos'],
        'sha256':                 hash_arquivo(caminho),
    }
    with open(os.path.join(args.saida, 'relatorio_braco_real.json'), 'w',
              encoding='utf-8') as arquivo:
        json.dump(resumo, arquivo, ensure_ascii=False, indent=2)

    print('BRACO A (corpus real)')
    print('---------------------')
    for chave, valor in resumo.items():
        print(f'  {chave:<26}: {valor}')
    print()
    print(f'Gravado em {caminho}')
    print('ATENCAO: este arquivo contem texto clinico real. Nao copiar nem versionar.')


if __name__ == '__main__':
    main()
