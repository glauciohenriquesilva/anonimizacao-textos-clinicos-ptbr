import json
import joblib
from seqeval.metrics import classification_report, f1_score
from preprocessamento.services.preprocessamento import (
    extrair_features_sentenca,
    tokenizar_word_level,
)

# Início - 2) NER - 2.4) Avaliação NER - 2.4.1) Predição no conjunto de teste (cada modelo)
def prever_crf(caminho_modelo, caminho_teste_conll):
    # Carrega o modelo CRF salvo em disco e faz predição no conjunto de teste.
    # Retorna as labels reais e as preditas para cálculo de métricas.
    from ner.services.crf import ler_conll

    crf = joblib.load(caminho_modelo)
    tokens, y_real = ler_conll(caminho_teste_conll)
    X_teste = [extrair_features_sentenca(t) for t in tokens]
    y_pred  = crf.predict(X_teste)

    return y_real, y_pred


def prever_bert(caminho_modelo, caminho_teste_conll):
    # Carrega o modelo BERT fine-tunado e faz predição no conjunto de teste.
    # Retorna as labels reais e as preditas alinhadas ao nível de token word-level.
    import torch
    from transformers import AutoTokenizer, AutoModelForTokenClassification
    from ner.services.crf import ler_conll
    from preprocessamento.services.preprocessamento import tokenizar_e_alinhar_bert

    tokenizer = AutoTokenizer.from_pretrained(caminho_modelo)
    modelo    = AutoModelForTokenClassification.from_pretrained(caminho_modelo)
    modelo.eval()

    id2label = modelo.config.id2label
    label2id = modelo.config.label2id

    tokens_lista, y_real = ler_conll(caminho_teste_conll)

    y_pred = []
    for tokens in tokens_lista:
        labels_ids = [label2id.get(l, 0) for l in ['O'] * len(tokens)]
        encoding, _ = tokenizar_e_alinhar_bert(tokens, labels_ids, tokenizer)

        input_ids      = torch.tensor(encoding['input_ids'])
        attention_mask = torch.tensor(encoding['attention_mask'])

        with torch.no_grad():
            saida = modelo(input_ids=input_ids, attention_mask=attention_mask)

        # Pega as predições do primeiro chunk (sentença curta)
        logits   = saida.logits[0]
        pred_ids = logits.argmax(dim=-1).tolist()

        # Alinha predições de volta ao nível word-level (descarta subtokens e especiais)
        word_ids = encoding.word_ids(batch_index=0)
        pred_labels  = []
        palavra_anterior = None
        for word_id, pred_id in zip(word_ids, pred_ids):
            if word_id is None or word_id == palavra_anterior:
                continue
            pred_labels.append(id2label[pred_id])
            palavra_anterior = word_id

        y_pred.append(pred_labels)

    return y_real, y_pred
# Fim - 2) NER - 2.4) Avaliação NER - 2.4.1) Predição no conjunto de teste (cada modelo)

# Início - 2) NER - 2.4) Avaliação NER - 2.4.2) F1 entity-level geral (seqeval, micro-avg)
def calcular_f1_entity_level(y_real, y_pred):
    # Calcula F1 micro-averaged no nível de entidade usando seqeval.
    # O seqeval avalia entidades completas (span-level), não token a token —
    # uma entidade só é correta se todos os seus tokens forem previstos corretamente.
    from seqeval.metrics import precision_score, recall_score

    relatorio  = classification_report(y_real, y_pred, output_dict=True)
    f1_micro   = f1_score(y_real, y_pred, average='micro')
    precision  = precision_score(y_real, y_pred, average='micro')
    recall     = recall_score(y_real, y_pred, average='micro')

    return {
        'f1_micro':  round(float(f1_micro), 4),
        'precision': round(float(precision), 4),
        'recall':    round(float(recall), 4),
        'relatorio': relatorio,
    }
# Fim - 2) NER - 2.4) Avaliação NER - 2.4.2) F1 entity-level geral (seqeval, micro-avg)

# Início - 2) NER - 2.4) Avaliação NER - 2.4.3) F1 por tipo de entidade PHI
def calcular_f1_por_entidade(y_real, y_pred):
    # Calcula precision, recall e F1 separadamente para cada tipo de entidade PHI.
    # Útil para identificar quais entidades o modelo acerta/erra mais.
    relatorio = classification_report(y_real, y_pred, output_dict=True)

    # Filtra apenas as entidades PHI (exclui chaves de agregação do seqeval)
    chaves_agregacao = {'micro avg', 'macro avg', 'weighted avg'}
    por_entidade = {
        entidade: {
            'precision': round(metricas['precision'], 4),
            'recall':    round(metricas['recall'], 4),
            'f1':        round(metricas['f1-score'], 4),
            'support':   metricas['support'],
        }
        for entidade, metricas in relatorio.items()
        if entidade not in chaves_agregacao
    }

    return por_entidade
# Fim - 2) NER - 2.4) Avaliação NER - 2.4.3) F1 por tipo de entidade PHI

# Início - 2) NER - 2.4) Avaliação NER - 2.4.4) F1 token-level (comparativo)
def calcular_f1_token_level(y_real, y_pred):
    # Calcula F1 no nível de token individual (não span) usando sklearn.
    # Usado como métrica comparativa com trabalhos anteriores que não usam seqeval.
    from sklearn.metrics import classification_report as sklearn_report

    # Achata as listas de listas em listas planas
    y_real_flat = [label for sentenca in y_real for label in sentenca]
    y_pred_flat = [label for sentenca in y_pred for label in sentenca]

    relatorio = sklearn_report(
        y_real_flat, y_pred_flat,
        output_dict=True,
        zero_division=0,
    )

    return {
        'f1_macro':   round(relatorio['macro avg']['f1-score'], 4),
        'f1_weighted': round(relatorio['weighted avg']['f1-score'], 4),
        'relatorio':  relatorio,
    }
# Fim - 2) NER - 2.4) Avaliação NER - 2.4.4) F1 token-level (comparativo)

# Início - 2) NER - 2.4) Avaliação NER - 2.4.5) Tabela comparativa dos 5 modelos
def gerar_tabela_comparativa(resultados_modelos):
    # Monta um DataFrame comparativo com as métricas principais de cada modelo.
    # resultados_modelos: dict com nome do modelo → dict de métricas
    # Exemplo:
    # {
    #   'CRF':           {'f1_micro': 0.72, 'f1_macro': 0.68, ...},
    #   'BioBERTpt-clin': {'f1_micro': 0.85, ...},
    # }
    import pandas as pd

    linhas = []
    for modelo, metricas in resultados_modelos.items():
        linhas.append({
            'Modelo':      modelo,
            'F1_Entity':   metricas.get('f1_micro', '-'),
            'F1_Token':    metricas.get('f1_macro', '-'),
            'Precision':   metricas.get('precision', '-'),
            'Recall':      metricas.get('recall', '-'),
        })

    df = pd.DataFrame(linhas)
    # Ordena do melhor para o pior F1 entity-level
    df = df.sort_values('F1_Entity', ascending=False).reset_index(drop=True)
    return df
# Fim - 2) NER - 2.4) Avaliação NER - 2.4.5) Tabela comparativa dos 5 modelos

