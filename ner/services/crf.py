# CRF Baseline — único modelo que roda local (CPU). Criado um novo arquivo para isso.

import joblib
import sklearn_crfsuite
from sklearn_crfsuite import metrics
from preprocessamento.services.preprocessamento import (
    tokenizar_word_level,
    extrair_features_sentenca,
)

# Início - 2) NER - 2.3) Treinamento dos Modelos - 2.3.1) CRF Baseline (local, CPU)
def ler_conll(caminho):
    # Lê um arquivo CoNLL e retorna listas de tokens e labels por sentença.
    # Retorna:
    #   sentencas_tokens : lista de listas de tokens
    #   sentencas_labels : lista de listas de labels BIO
    sentencas_tokens = []
    sentencas_labels = []
    tokens_atual = []
    labels_atual = []

    with open(caminho, encoding='utf-8') as f:
        for linha in f:
            linha = linha.rstrip('\n')
            if linha == '':
                if tokens_atual:
                    sentencas_tokens.append(tokens_atual)
                    sentencas_labels.append(labels_atual)
                    tokens_atual = []
                    labels_atual = []
            else:
                partes = linha.split('\t')
                tokens_atual.append(partes[0])
                labels_atual.append(partes[1])
        if tokens_atual:
            sentencas_tokens.append(tokens_atual)
            sentencas_labels.append(labels_atual)

    return sentencas_tokens, sentencas_labels


def treinar_crf(caminho_train, caminho_modelo):
    # Lê o train.conll, extrai features e treina o modelo CRF com L-BFGS.
    # Salva o modelo treinado em caminho_modelo (.joblib).

    tokens, labels = ler_conll(caminho_train)

    # Extrai features para cada sentença usando a função do pré-processamento
    X_train = [extrair_features_sentenca(t) for t in tokens]
    y_train = labels

    # Instancia o CRF com algoritmo L-BFGS e regularização L1+L2
    crf = sklearn_crfsuite.CRF(
        algorithm='lbfgs',
        c1=0.1,    # regularização L1 — promove esparsidade nas features
        c2=0.1,    # regularização L2 — penaliza pesos grandes
        max_iterations=100,
        all_possible_transitions=True,  # aprende transições mesmo não vistas no treino
    )

    crf.fit(X_train, y_train)

    # Persiste o modelo treinado em disco
    joblib.dump(crf, caminho_modelo)

    return crf


def avaliar_crf(crf, caminho_teste):
    # Avalia o modelo CRF no conjunto de teste e retorna métricas por entidade.

    tokens, labels = ler_conll(caminho_teste)
    X_teste = [extrair_features_sentenca(t) for t in tokens]
    y_teste = labels

    y_pred = crf.predict(X_teste)

    # Labels únicas excluindo O (não é entidade)
    labels_unicas = list(crf.classes_)
    labels_unicas = [l for l in labels_unicas if l != 'O']

    # Relatório detalhado por entidade (precision, recall, f1)
    relatorio = metrics.flat_classification_report(
        y_teste, y_pred, labels=labels_unicas, digits=4
    )

    return relatorio
# Fim - 2) NER - 2.3) Treinamento dos Modelos - 2.3.1) CRF Baseline (local, CPU)