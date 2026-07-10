import sys
sys.path.insert(0, '.')

import joblib
from seqeval.metrics import classification_report, f1_score
from preprocessamento.services.preprocessamento import extrair_features_sentenca


def ler_conll(caminho):
    sents_t, sents_l = [], []
    t, l = [], []
    with open(caminho, encoding='utf-8') as f:
        for linha in f:
            linha = linha.rstrip()
            if not linha:
                if t:
                    sents_t.append(t)
                    sents_l.append(l)
                    t, l = [], []
            else:
                partes = linha.split('\t')
                t.append(partes[0])
                l.append(partes[1])
    if t:
        sents_t.append(t)
        sents_l.append(l)
    return sents_t, sents_l


crf = joblib.load('outputs/ner/crf_model.joblib')
log = crf.training_log_

print(f'max_iterations config : {crf.max_iterations}')
print(f'Iteracoes realizadas  : {len(log.iterations)}')
print(f'Convergiu?            : {"SIM" if len(log.iterations) < crf.max_iterations else "NAO (atingiu limite)"}')
print(f'Error norm (ultima)   : {log.last_iteration["error_norm"]:.5f}')
print(f'Loss (ultima)         : {log.last_iteration["loss"]:.4f}')
print()

toks, labs = ler_conll('outputs/ner/test.conll')
X = [extrair_features_sentenca(t) for t in toks]
y_pred = crf.predict(X)

print(classification_report(labs, y_pred, digits=4))
print('micro-F1:', round(f1_score(labs, y_pred), 4))
