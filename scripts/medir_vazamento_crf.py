# -*- coding: utf-8 -*-
"""
Mede quanto a divisão por sentença infla o F1, usando o CRF no braço real.

O Exp 002 dividiu treino e teste sorteando sentenças, sem olhar o paciente. Como 70% das
sentenças dividem paciente com outra, o mesmo nome de paciente, médico ou hospital podia
estar no treino e no teste. Este script mede o tamanho desse efeito: treina o mesmo CRF,
com os mesmos hiperparâmetros e as mesmas 4.682 sentenças, nas duas divisões, cinco vezes
cada, e compara.

  por paciente  a divisão do experimento novo (comum_benchmark.dividir_por_paciente)
  por sentença  sorteio de sentenças nas mesmas proporções, como no Exp 002

A divisão por sentença aqui é um sorteio simples. O Exp 002 também reservava ao menos uma
sentença de cada entidade para o teste antes de sortear o resto; essa reserva muda pouco
um conjunto de 4.682 sentenças e não muda o mecanismo do vazamento.

Somente leitura dos corpora. Imprime e grava apenas números.

Uso:
    python scripts/medir_vazamento_crf.py --dir outputs/surrogates_exp004_r4
"""

import argparse
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'anonclin.settings')

import django  # noqa: E402
django.setup()

import sklearn_crfsuite  # noqa: E402

from preprocessamento.services.preprocessamento import extrair_features_sentenca  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum_benchmark import (  # noqa: E402
    desvio, dividir_por_paciente, ler_corpus, media, metricas_seqeval,
)


def dividir_por_sentenca(n_sentencas, tamanho_teste, tamanho_validacao, semente):
    """Sorteia sentenças, sem olhar o paciente, nos mesmos tamanhos da divisão por paciente."""
    indices = list(range(n_sentencas))
    random.Random(semente).shuffle(indices)
    teste = indices[:tamanho_teste]
    validacao = indices[tamanho_teste:tamanho_teste + tamanho_validacao]
    treino = indices[tamanho_teste + tamanho_validacao:]
    return sorted(treino), sorted(validacao), sorted(teste)


def rodar(tokens, labels, treino, teste):
    crf = sklearn_crfsuite.CRF(algorithm='lbfgs', c1=0.1, c2=0.1, max_iterations=300,
                               all_possible_transitions=True)
    crf.fit([extrair_features_sentenca(tokens[i]) for i in treino], [labels[i] for i in treino])
    previsto = crf.predict([extrair_features_sentenca(tokens[i]) for i in teste])
    return metricas_seqeval([labels[i] for i in teste], previsto)


def pacientes_em_comum(grupos, treino, teste):
    """Fração das sentenças de teste cujo paciente também tem sentença no treino."""
    no_treino = {grupos[i] for i in treino}
    return sum(1 for i in teste if grupos[i] in no_treino) / len(teste)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--dir', required=True)
    p.add_argument('--particoes', type=int, default=5)
    a = p.parse_args()

    tokens, labels = ler_corpus(os.path.join(a.dir, 'corpus_real.jsonl'))
    with open(os.path.join(a.dir, 'grupos_paciente.json'), encoding='utf-8') as f:
        grupos = json.load(f)

    resultado = {'por_paciente': [], 'por_sentenca': []}
    for semente in range(1, a.particoes + 1):
        treino_p, val_p, teste_p = dividir_por_paciente(grupos, semente)
        treino_s, _, teste_s = dividir_por_sentenca(len(grupos), len(teste_p), len(val_p),
                                                   semente)
        for nome, treino, teste in (('por_paciente', treino_p, teste_p),
                                    ('por_sentenca', treino_s, teste_s)):
            inicio = time.time()
            f1, _, metricas = rodar(tokens, labels, treino, teste)
            linha = {'semente': semente, 'f1': f1,
                     'cobertura': metricas['micro']['cobertura'],
                     'precisao': metricas['micro']['precisao'],
                     'teste_com_paciente_no_treino': round(
                         pacientes_em_comum(grupos, treino, teste), 4),
                     'por_entidade': {e: v['f1'] for e, v in metricas['por_entidade'].items()}}
            resultado[nome].append(linha)
            print(f"  particao {semente}, {nome:<13} F1 {f1:.4f} | cobertura "
                  f"{linha['cobertura']:.4f} | teste com paciente no treino "
                  f"{linha['teste_com_paciente_no_treino']:.0%}  ({time.time() - inicio:.0f}s)")

    print('\nRESUMO')
    for nome in ('por_paciente', 'por_sentenca'):
        f1s = [l['f1'] for l in resultado[nome]]
        cob = [l['cobertura'] for l in resultado[nome]]
        com = [l['teste_com_paciente_no_treino'] for l in resultado[nome]]
        print(f'  {nome:<13} F1 {media(f1s):.4f} (dp {desvio(f1s):.4f}) | cobertura '
              f'{media(cob):.4f} | teste com paciente no treino {media(com):.0%}')
    dif = [s['f1'] - p['f1'] for p, s in zip(resultado['por_paciente'], resultado['por_sentenca'])]
    print(f'  inflacao do F1 pela divisao por sentenca: {media(dif):+.4f} (dp {desvio(dif):.4f})')
    for e in ('DATA', 'ENDERECO', 'INSTITUICAO', 'PESSOA'):
        dp = media([l['por_entidade'].get(e, 0) for l in resultado['por_paciente']])
        ds = media([l['por_entidade'].get(e, 0) for l in resultado['por_sentenca']])
        print(f'    {e:<12} por paciente {dp:.3f} | por sentenca {ds:.3f} | {ds - dp:+.3f}')

    caminho = os.path.join(a.dir, 'vazamento_crf.json')
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    print(f'\nGravado em {caminho}')


if __name__ == '__main__':
    main()
