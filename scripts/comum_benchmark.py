# -*- coding: utf-8 -*-
"""
Peças comuns aos benchmarks dos três braços (CRF e BERT).

Ficam aqui a divisão por paciente e a estatística, para que os dois benchmarks usem
EXATAMENTE as mesmas partições e o mesmo cálculo. Uma divisão escrita duas vezes acaba
divergindo, e aí CRF e BERT deixam de ser comparáveis sem que ninguém perceba.

Não depende do Django nem de bibliotecas de aprendizado de máquina, para poder ser usado
no servidor com GPU, onde só o corpus e o código vão.
"""

import json
import math
import random

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


def resumir_benchmark(resultados, versoes, n_particoes, delta):
    """
    Monta o resumo das duas avaliações (no texto real e no próprio corpus).

    Espera em cada partição os campos f1 e f1_proprio, com uma entrada por braço, e o
    campo sentencas com os tamanhos de treino e teste.
    """
    sementes = [str(s) for s in range(1, n_particoes + 1)]
    tamanhos = (resultados['particoes'][sementes[0]]['sentencas']['treino'],
                resultados['particoes'][sementes[0]]['sentencas']['teste'])

    def bloco(campo):
        f1_a = [resultados['particoes'][s][campo]['real'] for s in sementes]
        f1_b = [media([resultados['particoes'][s][campo][v] for v in versoes])
                for s in sementes]
        saida = {
            'f1_real': {'media': round(media(f1_a), 4), 'desvio': round(desvio(f1_a), 4)},
            'f1_surrogates': {
                'media': round(media(f1_b), 4), 'desvio': round(desvio(f1_b), 4),
                'desvio_medio_entre_versoes': round(media([
                    desvio([resultados['particoes'][s][campo][v] for v in versoes])
                    for s in sementes]), 4),
            },
            'B_menos_A': resumir_diferencas(
                [b - a for a, b in zip(f1_a, f1_b)], tamanhos[0], tamanhos[1], delta),
        }
        for braco in ('placeholder', 'celebridade'):
            f1_c = [resultados['particoes'][s][campo][braco] for s in sementes]
            saida[f'f1_{braco}'] = {'media': round(media(f1_c), 4),
                                    'desvio': round(desvio(f1_c), 4)}
            saida[f'{braco}_menos_A'] = resumir_diferencas(
                [c - a for a, c in zip(f1_a, f1_c)], tamanhos[0], tamanhos[1], delta)
        return saida

    return {'delta': delta,
            'avaliacao_no_texto_real': bloco('f1'),
            'avaliacao_no_proprio_corpus': bloco('f1_proprio')}
