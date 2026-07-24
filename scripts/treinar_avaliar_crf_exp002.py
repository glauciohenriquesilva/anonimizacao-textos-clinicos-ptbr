# Treina e avalia o CRF baseline no corpus final do Experimento 002.
# Mesma configuracao do Exp001 (L-BFGS, c1=0.1, c2=0.1, max_iterations=300).

from ner.services.crf import treinar_crf, avaliar_crf
import joblib

caminho_train = 'outputs/ner/exp002/train.conll'
caminho_test  = 'outputs/ner/exp002/test.conll'
caminho_modelo = 'outputs/ner/exp002/crf_model_exp002.joblib'

print('Treinando CRF (Exp002)...')
crf = treinar_crf(caminho_train, caminho_modelo)
print('Treinamento concluido. Modelo salvo em', caminho_modelo)

print()
print('Avaliando no test set...')
f1, relatorio = avaliar_crf(crf, caminho_test)
print(f'F1 micro (entity-level, seqeval): {f1:.4f}')
print()
print(relatorio)

with open('outputs/ner/exp002/crf_relatorio.txt', 'w', encoding='utf-8') as f:
    f.write(f'F1 micro (entity-level, seqeval): {f1:.4f}\n\n')
    f.write(relatorio)
