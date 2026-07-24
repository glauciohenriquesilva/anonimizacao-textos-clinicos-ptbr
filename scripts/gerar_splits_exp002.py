# Gera os splits train/dev/test (Iterative Stratification, 70/15/15) para o
# corpus final do Experimento 002, reaproveitando a mesma metodologia do Exp 001.

import json
from ner.services.anotacao import dividir_corpus, verificar_distribuicao, exportar_splits_conll

caminho_conll = 'outputs/preprocessamento/Experimento_002_corpus_v2_24072026.conll'
diretorio_saida = 'outputs/ner/exp002'

treino, dev, teste = dividir_corpus(caminho_conll)

print(f'Treino: {len(treino)} sentencas')
print(f'Dev:    {len(dev)} sentencas')
print(f'Teste:  {len(teste)} sentencas')
print(f'Total:  {len(treino) + len(dev) + len(teste)} sentencas')

verificacao = verificar_distribuicao(treino, dev, teste)
print()
print('Distribuicao por entidade:')
print(f"{'Entidade':15s} {'Treino':>8s} {'Dev':>8s} {'Teste':>8s}")
todas_entidades = sorted(verificacao['treino'].keys())
for ent in todas_entidades:
    print(f"{ent:15s} {verificacao['treino'].get(ent,0):>8d} {verificacao['dev'].get(ent,0):>8d} {verificacao['teste'].get(ent,0):>8d}")

print()
print('OK (nenhuma entidade zerada em dev/teste):', verificacao['ok'])
if not verificacao['ok']:
    print('Ausentes em dev:', verificacao['ausentes_dev'])
    print('Ausentes em teste:', verificacao['ausentes_teste'])

caminhos = exportar_splits_conll(treino, dev, teste, diretorio_saida)
print()
print('Arquivos gerados:', caminhos)
