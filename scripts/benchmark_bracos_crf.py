# -*- coding: utf-8 -*-
"""
Fase 6, primeira parte: benchmark dos três braços com o CRF.

Pergunta que este script responde: um CRF treinado no corpus com surrogates atinge, no
texto real, o mesmo F1 de um CRF treinado no corpus real?

COMO O EXPERIMENTO É MONTADO

  Braço A   corpus_real.jsonl              identificadores verdadeiros
  Braço B   corpus_v01.jsonl a vNN.jsonl   surrogates verossímeis, uma versão por semente
  Braço C   corpus_placeholder.jsonl       marcadores numerados
            corpus_celebridade.jsonl       nomes muito conhecidos

Todos os arquivos têm as mesmas sentenças na mesma ordem. Só muda o que aparece no lugar
dos identificadores.

DIVISÃO POR PACIENTE

Treino, validação e teste são separados por paciente, nunca por sentença. Quase 70% das
sentenças dividem o paciente com outra, e uma divisão ao acaso colocaria o mesmo nome no
treino e no teste. O modelo acertaria por ter decorado, não por ter aprendido.

A divisão é repetida K vezes, cada uma com sua semente. O CRF é determinístico, então é
a repetição da divisão que mostra quanto o resultado oscila, inclusive no braço A.

DUAS AVALIAÇÕES PARA CADA TREINO

Cada modelo treinado é avaliado duas vezes, nas mesmas sentenças de teste:

  no texto real      responde se o corpus liberável serve para treinar um modelo que
                     vai rodar em prontuário de verdade (a QP2 dos slides);
  no próprio corpus  responde se um resultado medido no corpus liberável se parece com
                     o que se mediria no real. É a hipótese do orientador (reunião de
                     06/10/2026): a base com marcadores dá resultado otimista demais, e a
                     base verossímil fica perto do real.

No braço A as duas avaliações coincidem.

ESTATÍSTICA

Para cada partição calcula-se dF1 = F1(B) - F1(A), com F1(B) sendo a média das versões.
Sobre os K valores de dF1 saem a média, o intervalo de confiança de 90% e, se a margem
for informada com --delta, o teste de equivalência TOST. A margem precisa ser decidida
ANTES de olhar o resultado. Sem --delta o script não testa nada, só descreve.

Ressalva conhecida: as K partições reaproveitam as mesmas sentenças, então os K valores
não são independentes e o intervalo sai mais estreito do que deveria. O relatório traz
também o intervalo com a correção de Nadeau e Bengio (2003), que é o número a citar.

Somente leitura dos corpora. Imprime e grava apenas números.

Uso:
    python scripts/benchmark_bracos_crf.py --dir outputs/surrogates_exp004_r3 --particoes 5 \
        --saida outputs/surrogates_exp004_r3/benchmark_crf_duplo.json
"""

import argparse
import json
import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'anonclin.settings')

import django  # noqa: E402
django.setup()

import sklearn_crfsuite  # noqa: E402
from seqeval.metrics import classification_report, f1_score  # noqa: E402

from preprocessamento.services.preprocessamento import extrair_features_sentenca  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum_benchmark import (  # noqa: E402
    contar_entidades, dividir_por_paciente, ler_corpus, metricas_seqeval, resumir_benchmark,
)

def treinar(tokens_treino, labels_treino):
    """Treina um CRF com os hiperparâmetros do Exp 002."""
    crf = sklearn_crfsuite.CRF(
        algorithm='lbfgs', c1=0.1, c2=0.1, max_iterations=300,
        all_possible_transitions=True,
    )
    crf.fit([extrair_features_sentenca(t) for t in tokens_treino], labels_treino)
    return crf


def avaliar(crf, x_teste, y_teste):
    """Devolve (F1 micro, F1 por entidade, métricas completas) nas sentenças dadas."""
    return metricas_seqeval(y_teste, crf.predict(x_teste))


def main():
    parser = argparse.ArgumentParser(description='Benchmark dos tres bracos com CRF.')
    parser.add_argument('--dir', required=True, help='Pasta da geracao de surrogates.')
    parser.add_argument('--particoes', type=int, default=5,
                        help='Quantas divisoes treino/teste por paciente (padrao 5).')
    parser.add_argument('--versoes', type=int, default=None,
                        help='Limita o numero de versoes do braco B. Util para teste.')
    parser.add_argument('--delta', type=float, default=None,
                        help='Margem de equivalencia em pontos de F1 (ex.: 0.02). '
                             'Deve ser fixada antes de ver qualquer resultado.')
    parser.add_argument('--saida', default=None,
                        help='Arquivo JSON de resultados. Padrao: <dir>/benchmark_crf.json')
    args = parser.parse_args()

    caminho_saida = args.saida or os.path.join(args.dir, 'benchmark_crf.json')

    with open(os.path.join(args.dir, 'grupos_paciente.json'), encoding='utf-8') as arquivo:
        grupos = json.load(arquivo)

    versoes = sorted(
        nome[len('corpus_'):-len('.jsonl')] for nome in os.listdir(args.dir)
        if nome.startswith('corpus_v') and nome.endswith('.jsonl')
    )
    if args.versoes:
        versoes = versoes[:args.versoes]
    bracos = ['real'] + versoes + ['placeholder', 'celebridade']

    print('Lendo os corpora...')
    corpora = {}
    for braco in bracos:
        corpora[braco] = ler_corpus(os.path.join(args.dir, f'corpus_{braco}.jsonl'))
        if len(corpora[braco][0]) != len(grupos):
            sys.exit(f'corpus_{braco}.jsonl tem {len(corpora[braco][0])} sentencas e '
                     f'grupos_paciente.json tem {len(grupos)}. Gere tudo de novo.')
    print(f'  {len(grupos)} sentencas, {len(set(grupos))} pacientes, '
          f'{len(versoes)} versoes do braco B')

    # Retoma de onde parou: cada treino concluído já está gravado no arquivo de saída.
    resultados = {'particoes': {}}
    if os.path.exists(caminho_saida):
        with open(caminho_saida, encoding='utf-8') as arquivo:
            resultados = json.load(arquivo)
        print(f'  retomando de {caminho_saida}')

    tokens_reais, labels_reais = corpora['real']

    for semente in range(1, args.particoes + 1):
        chave = str(semente)
        treino, validacao, teste = dividir_por_paciente(grupos, semente)
        particao = resultados['particoes'].setdefault(
            chave, {'f1': {}, 'por_entidade': {}, 'f1_proprio': {}, 'por_entidade_proprio': {},
                    'metricas': {}, 'metricas_proprio': {}})
        particao['sentencas'] = {'treino': len(treino), 'validacao': len(validacao),
                                 'teste': len(teste)}
        particao['entidades_teste'] = contar_entidades(labels_reais, teste)
        particao['entidades_treino'] = contar_entidades(labels_reais, treino)

        print()
        print(f'PARTICAO {semente}: treino {len(treino)}, validacao {len(validacao)}, '
              f'teste {len(teste)}')
        print(f"  entidades no teste: {particao['entidades_teste']}")

        x_teste = [extrair_features_sentenca(tokens_reais[i]) for i in teste]
        y_teste = [labels_reais[i] for i in teste]

        for braco in bracos:
            if braco in particao['f1']:
                print(f"  {braco:<12} F1 {particao['f1'][braco]:.4f}  (ja calculado)")
                continue
            inicio = time.time()
            tokens, labels = corpora[braco]
            crf = treinar([tokens[i] for i in treino], [labels[i] for i in treino])
            f1, por_entidade, metricas = avaliar(crf, x_teste, y_teste)
            f1_p, por_entidade_p, metricas_p = avaliar(
                crf, [extrair_features_sentenca(tokens[i]) for i in teste],
                [labels[i] for i in teste])
            particao['f1'][braco] = f1
            particao['por_entidade'][braco] = por_entidade
            particao['f1_proprio'][braco] = f1_p
            particao['por_entidade_proprio'][braco] = por_entidade_p
            particao.setdefault('metricas', {})[braco] = metricas
            particao.setdefault('metricas_proprio', {})[braco] = metricas_p
            print(f'  {braco:<12} F1 no real {f1:.4f} | no proprio {f1_p:.4f}  '
                  f'({time.time() - inicio:.0f}s)')
            with open(caminho_saida, 'w', encoding='utf-8') as arquivo:
                json.dump(resultados, arquivo, ensure_ascii=False, indent=2)

    # ---- Resumo ----------------------------------------------------------------
    resumo = resumir_benchmark(resultados, versoes, args.particoes, args.delta)
    resultados['resumo'] = resumo
    with open(caminho_saida, 'w', encoding='utf-8') as arquivo:
        json.dump(resultados, arquivo, ensure_ascii=False, indent=2)

    print()
    print('RESUMO')
    print('------')
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    print()
    if args.delta is None:
        print('Nenhuma margem informada: o resultado acima e descritivo, nao um teste.')
    print(f'Resultados gravados em {caminho_saida}')


if __name__ == '__main__':
    main()
