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


def metricas_seqeval(y_real, y_previsto):
    """
    Devolve (f1, f1_por_entidade, metricas) no padrão do seqeval, por entidade.

    Além do F1, guarda precisão e cobertura (recall). Para anonimização, a cobertura é a
    métrica que mais importa: cada entidade que o modelo deixa de encontrar é um
    identificador real que fica no texto. É a dimensão L, de privacidade.
    """
    from seqeval.metrics import classification_report, f1_score

    relatorio = classification_report(y_real, y_previsto, output_dict=True, zero_division=0)
    por_entidade, metricas = {}, {'por_entidade': {}}
    for nome, v in relatorio.items():
        bloco = {'precisao': round(v['precision'], 4), 'cobertura': round(v['recall'], 4),
                 'f1': round(v['f1-score'], 4), 'suporte': int(v['support'])}
        if nome == 'micro avg':
            metricas['micro'] = bloco
        elif nome not in ('macro avg', 'weighted avg'):
            metricas['por_entidade'][nome] = bloco
            por_entidade[nome] = bloco['f1']
    return round(f1_score(y_real, y_previsto), 4), por_entidade, metricas


def resumir_benchmark(resultados, versoes, n_particoes, delta):
    """
    Monta o resumo das duas avaliações (no texto real e no próprio corpus).

    Espera em cada partição os campos f1 e f1_proprio, com uma entrada por braço, e o
    campo sentencas com os tamanhos de treino e teste.
    """
    sementes = [str(s) for s in range(1, n_particoes + 1)]
    tamanhos = (resultados['particoes'][sementes[0]]['sentencas']['treino'],
                resultados['particoes'][sementes[0]]['sentencas']['teste'])

    def bloco(campo, chave=None):
        # Sem chave, lê o F1 guardado em `campo`. Com chave, lê a métrica micro de mesmo
        # nome dentro de `campo` (usado para a cobertura).
        def ler(s, braco):
            valor = resultados['particoes'][s][campo][braco]
            return valor['micro'][chave] if chave else valor

        nome = chave or 'f1'          # prefixo dos campos: f1_real, cobertura_real...
        f1_a = [ler(s, 'real') for s in sementes]
        f1_b = [media([ler(s, v) for v in versoes]) for s in sementes]
        saida = {
            f'{nome}_real': {'media': round(media(f1_a), 4),
                             'desvio': round(desvio(f1_a), 4)},
            f'{nome}_surrogates': {
                'media': round(media(f1_b), 4), 'desvio': round(desvio(f1_b), 4),
                'desvio_medio_entre_versoes': round(media([
                    desvio([ler(s, v) for v in versoes]) for s in sementes]), 4),
            },
            'B_menos_A': resumir_diferencas(
                [b - a for a, b in zip(f1_a, f1_b)], tamanhos[0], tamanhos[1], delta),
        }
        for braco in ('placeholder', 'celebridade'):
            f1_c = [ler(s, braco) for s in sementes]
            saida[f'{nome}_{braco}'] = {'media': round(media(f1_c), 4),
                                    'desvio': round(desvio(f1_c), 4)}
            saida[f'{braco}_menos_A'] = resumir_diferencas(
                [c - a for a, c in zip(f1_a, f1_c)], tamanhos[0], tamanhos[1], delta)
        return saida

    resumo = {'delta': delta,
              'avaliacao_no_texto_real': bloco('f1'),
              'avaliacao_no_proprio_corpus': bloco('f1_proprio')}
    # A cobertura só existe nas rodadas que guardaram as métricas completas.
    primeira = resultados['particoes'][sementes[0]]
    if primeira.get('metricas'):
        resumo['cobertura_no_texto_real'] = bloco('metricas', 'cobertura')
        resumo['cobertura_no_proprio_corpus'] = bloco('metricas_proprio', 'cobertura')
    return resumo


if __name__ == '__main__':
    # Recalcula o resumo de um arquivo de resultados já existente, sem treinar nada.
    #   python scripts/comum_benchmark.py <arquivo.json> [--delta 0.02]
    import sys
    caminho = sys.argv[1]
    delta = float(sys.argv[sys.argv.index('--delta') + 1]) if '--delta' in sys.argv else None
    with open(caminho, encoding='utf-8') as arquivo:
        resultados = json.load(arquivo)
    primeira = resultados['particoes'][min(resultados['particoes'], key=int)]
    versoes = sorted(b for b in primeira['f1'] if b.startswith('v'))
    resultados['resumo'] = resumir_benchmark(
        resultados, versoes, len(resultados['particoes']), delta)
    with open(caminho, 'w', encoding='utf-8') as arquivo:
        json.dump(resultados, arquivo, ensure_ascii=False, indent=2)
    print(json.dumps(resultados['resumo'], ensure_ascii=False, indent=2))
