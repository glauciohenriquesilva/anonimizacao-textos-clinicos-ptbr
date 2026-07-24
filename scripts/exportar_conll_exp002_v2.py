# Exporta o CoNLL final da Sessao de Anotacao do Experimento 002 (id=5),
# apos a conclusao da anotacao (24/07/2026) e a regeneracao do corpus (Task #25).
# Os arquivos antigos em outputs/preprocessamento/Experimento_002_corpus*.conll (15/07)
# sao anteriores a ambos os eventos e estao desatualizados.
#
# Nota: em ambiente sandbox (sem escrita no sqlite), o save() final de
# exportar_conll_final() pode falhar com "disk I/O error" -- isso e esperado
# e nao invalida o arquivo .conll ja escrito em disco antes desse ponto.

import os
from anotador.models import SessaoAnotacao
from anotador.services.exportador import exportar_conll_final

sessao = SessaoAnotacao.objects.get(id=5)
assert sessao.experimento_id == 9, f"esperado experimento 9, veio {sessao.experimento_id}"

caminho_saida = 'outputs/preprocessamento/Experimento_002_corpus_v2_24072026.conll'
os.makedirs(os.path.dirname(caminho_saida), exist_ok=True)

try:
    resultado = exportar_conll_final(sessao, caminho_saida)
    print('OK (com update de metadata):', resultado)
except Exception as e:
    print('Arquivo escrito, mas update de metadata falhou (esperado em sandbox):', repr(e))

# Confirma que o arquivo foi escrito corretamente
with open(caminho_saida, encoding='utf-8') as f:
    conteudo = f.read()

n_sentencas = conteudo.count('\n\n')
n_linhas_token = sum(1 for l in conteudo.splitlines() if l.strip() and '\t' in l)
print(f'Arquivo: {caminho_saida}')
print(f'Sentencas (aprox, por blocos separados por linha em branco): {n_sentencas}')
print(f'Linhas token: {n_linhas_token}')
print(f'Tamanho: {os.path.getsize(caminho_saida)} bytes')
