from anotador.models import Sentenca

titulos = {'sr', 'sra', 'dr', 'dra'}
sessao_id = 5

sentencas = Sentenca.objects.filter(sessao_id=sessao_id)
print(f'Total de sentencas na sessao {sessao_id}: {sentencas.count()}')

total_anotacoes = 0
achados = 0

for s in sentencas:
    tokens = s.tokens
    anotacoes = {a.posicao: a.label for a in s.anotacoes.all()}
    total_anotacoes += len(anotacoes)
    for i, tok in enumerate(tokens):
        if tok.lower() in titulos:
            achados += 1
            label_titulo = anotacoes.get(i, '(sem anotacao)')
            nome_prox = tokens[i + 1] if i + 1 < len(tokens) else None
            label_prox = anotacoes.get(i + 1, '(sem anotacao)') if i + 1 < len(tokens) else None
            print(f'Sentenca id={s.id} ordem={s.ordem} pos={i}: token="{tok}" label="{label_titulo}" | proximo="{nome_prox}" label="{label_prox}"')

print(f'Total de anotacoes na sessao: {total_anotacoes}')
print(f'Total de ocorrencias de titulos (sr/sra/dr/dra): {achados}')
