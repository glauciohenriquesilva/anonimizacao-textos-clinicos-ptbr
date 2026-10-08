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

FRACAO_TESTE = 0.15
FRACAO_VALIDACAO = 0.15


def ler_corpus(caminho):
    """Devolve (lista de tokens, lista de labels), uma entrada por sentença."""
    tokens, labels = [], []
    with open(caminho, encoding='utf-8') as arquivo:
        for linha in arquivo:
            registro = json.loads(linha)
            tokens.append(registro['tokens'])
            labels.append(registro['labels'])
    return tokens, labels


def dividir_por_paciente(grupos, semente):
    """
    Sorteia pacientes inteiros para teste e validação até atingir 15% das sentenças em
    cada um. O resto é treino. Devolve três listas de índices de sentença.

    Nenhum paciente fica em duas partições. É essa a garantia contra vazamento.
    """
    por_paciente = {}
    for indice, paciente in enumerate(grupos):
        por_paciente.setdefault(paciente, []).append(indice)

    pacientes = sorted(por_paciente)
    random.Random(semente).shuffle(pacientes)

    total = len(grupos)
    teste, validacao, treino = [], [], []
    for paciente in pacientes:
        if len(teste) < FRACAO_TESTE * total:
            teste.extend(por_paciente[paciente])
        elif len(validacao) < FRACAO_VALIDACAO * total:
            validacao.extend(por_paciente[paciente])
        else:
            treino.extend(por_paciente[paciente])
    return sorted(treino), sorted(validacao), sorted(teste)


def contar_entidades(labels, indices):
    """Conta as entidades (labels B-) por tipo nas sentenças indicadas."""
    contagem = {}
    for indice in indices:
        for label in labels[indice]:
            if label.startswith('B-'):
                contagem[label[2:]] = contagem.get(label[2:], 0) + 1
    return contagem


def treinar(tokens_treino, labels_treino):
    """Treina um CRF com os hiperparâmetros do Exp 002."""
    crf = sklearn_crfsuite.CRF(
        algorithm='lbfgs', c1=0.1, c2=0.1, max_iterations=300,
        all_possible_transitions=True,
    )
    crf.fit([extrair_features_sentenca(t) for t in tokens_treino], labels_treino)
    return crf


def avaliar(crf, x_teste, y_teste):
    """Devolve (F1 micro, F1 por entidade) do modelo nas sentenças de teste dadas."""
    previsto = crf.predict(x_teste)
    relatorio = classification_report(y_teste, previsto, output_dict=True, zero_division=0)
    por_entidade = {
        nome: round(valores['f1-score'], 4)
        for nome, valores in relatorio.items()
        if nome not in ('micro avg', 'macro avg', 'weighted avg')
    }
    return round(f1_score(y_teste, previsto), 4), por_entidade


def media(valores):
    return sum(valores) / len(valores)


def desvio(valores):
    if len(valores) < 2:
        return 0.0
    m = media(valores)
    return math.sqrt(sum((v - m) ** 2 for v in valores) / (len(valores) - 1))


def resumir_diferencas(diferencas, n_treino, n_teste, delta):
    """
    Média, intervalo de 90% e, havendo margem, o TOST sobre as diferenças por partição.

    Sai em duas versões: a ingênua, que trata as partições como independentes, e a
    corrigida de Nadeau e Bengio, que infla a variância pelo tanto de sentenças que as
    partições compartilham. A corrigida é a que deve ser citada.
    """
    from scipy import stats

    k = len(diferencas)
    m, s = media(diferencas), desvio(diferencas)
    saida = {'k': k, 'media': round(m, 4), 'desvio': round(s, 4)}
    if k < 2 or s == 0:
        saida['observacao'] = 'sem variacao ou menos de duas particoes: nao ha intervalo'
        return saida

    erros = {
        'ingenuo':   s * math.sqrt(1 / k),
        'corrigido': s * math.sqrt(1 / k + n_teste / n_treino),
    }
    critico = stats.t.ppf(0.95, k - 1)
    for nome, erro in erros.items():
        bloco = {
            'ic90': [round(m - critico * erro, 4), round(m + critico * erro, 4)],
        }
        if delta is not None:
            p_inferior = 1 - stats.t.cdf((m + delta) / erro, k - 1)   # H0: dF1 <= -delta
            p_superior = stats.t.cdf((m - delta) / erro, k - 1)       # H0: dF1 >= +delta
            bloco['tost_p'] = round(max(p_inferior, p_superior), 4)
            bloco['equivalente'] = bool(bloco['tost_p'] < 0.05)
        saida[nome] = bloco
    return saida


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
    tamanhos = None

    for semente in range(1, args.particoes + 1):
        chave = str(semente)
        treino, validacao, teste = dividir_por_paciente(grupos, semente)
        tamanhos = (len(treino), len(teste))
        particao = resultados['particoes'].setdefault(
            chave, {'f1': {}, 'por_entidade': {}, 'f1_proprio': {}, 'por_entidade_proprio': {}})
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
            f1, por_entidade = avaliar(crf, x_teste, y_teste)
            f1_p, por_entidade_p = avaliar(
                crf, [extrair_features_sentenca(tokens[i]) for i in teste],
                [labels[i] for i in teste])
            particao['f1'][braco] = f1
            particao['por_entidade'][braco] = por_entidade
            particao['f1_proprio'][braco] = f1_p
            particao['por_entidade_proprio'][braco] = por_entidade_p
            print(f'  {braco:<12} F1 no real {f1:.4f} | no proprio {f1_p:.4f}  '
                  f'({time.time() - inicio:.0f}s)')
            with open(caminho_saida, 'w', encoding='utf-8') as arquivo:
                json.dump(resultados, arquivo, ensure_ascii=False, indent=2)

    # ---- Resumo ----------------------------------------------------------------
    sementes = [str(s) for s in range(1, args.particoes + 1)]
    f1_a = [resultados['particoes'][s]['f1']['real'] for s in sementes]
    f1_b = [media([resultados['particoes'][s]['f1'][v] for v in versoes]) for s in sementes]
    desvio_versoes = [desvio([resultados['particoes'][s]['f1'][v] for v in versoes])
                      for s in sementes]

    resumo = {
        'delta': args.delta,
        'f1_real':       {'media': round(media(f1_a), 4), 'desvio': round(desvio(f1_a), 4)},
        'f1_surrogates': {'media': round(media(f1_b), 4), 'desvio': round(desvio(f1_b), 4),
                          'desvio_medio_entre_versoes': round(media(desvio_versoes), 4)},
        'B_menos_A': resumir_diferencas(
            [b - a for a, b in zip(f1_a, f1_b)], tamanhos[0], tamanhos[1], args.delta),
    }
    for braco in ('placeholder', 'celebridade'):
        f1_c = [resultados['particoes'][s]['f1'][braco] for s in sementes]
        resumo[f'f1_{braco}'] = {'media': round(media(f1_c), 4),
                                 'desvio': round(desvio(f1_c), 4)}
        resumo[f'{braco}_menos_A'] = resumir_diferencas(
            [c - a for a, c in zip(f1_a, f1_c)], tamanhos[0], tamanhos[1], args.delta)

    # Avaliação no próprio corpus: a hipótese do orientador.
    proprio = {}
    f1_a_proprio = [resultados['particoes'][s]['f1_proprio']['real'] for s in sementes]
    f1_b_proprio = [media([resultados['particoes'][s]['f1_proprio'][v] for v in versoes])
                    for s in sementes]
    proprio['f1_real'] = {'media': round(media(f1_a_proprio), 4),
                          'desvio': round(desvio(f1_a_proprio), 4)}
    proprio['f1_surrogates'] = {'media': round(media(f1_b_proprio), 4),
                                'desvio': round(desvio(f1_b_proprio), 4)}
    proprio['B_menos_A'] = resumir_diferencas(
        [b - a for a, b in zip(f1_a_proprio, f1_b_proprio)], tamanhos[0], tamanhos[1],
        args.delta)
    for braco in ('placeholder', 'celebridade'):
        f1_c = [resultados['particoes'][s]['f1_proprio'][braco] for s in sementes]
        proprio[f'f1_{braco}'] = {'media': round(media(f1_c), 4),
                                  'desvio': round(desvio(f1_c), 4)}
        proprio[f'{braco}_menos_A'] = resumir_diferencas(
            [c - a for a, c in zip(f1_a_proprio, f1_c)], tamanhos[0], tamanhos[1],
            args.delta)
    resumo['avaliacao_no_proprio_corpus'] = proprio

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
