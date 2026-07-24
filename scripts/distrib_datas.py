# -*- coding: utf-8 -*-
from collections import defaultdict
from anotador.models import Sentenca

SESSAO_ID = 5
sentencas = Sentenca.objects.filter(sessao_id=SESSAO_ID).prefetch_related('anotacoes')

dist = defaultdict(int)
exemplos_longos = []

for s in sentencas:
    tokens = s.tokens
    anot = {a.posicao: a.label for a in s.anotacoes.all()}
    if not anot:
        continue
    spans = []
    cur = []
    for i in range(len(tokens)):
        lbl = anot.get(i, 'O')
        if lbl in ('B-DATA', 'I-DATA'):
            if lbl == 'B-DATA' and cur:
                spans.append(cur)
                cur = []
            cur.append(i)
        else:
            if cur:
                spans.append(cur)
                cur = []
    if cur:
        spans.append(cur)

    for span in spans:
        dist[len(span)] += 1
        if len(span) >= 5:
            texto = ' '.join(tokens[i] for i in span)
            exemplos_longos.append((s.id, texto))

print('Distribuicao de comprimento de spans DATA (em tokens):')
for tam, n in sorted(dist.items()):
    print(f'  {tam} tokens: {n} spans')

print()
print(f'Exemplos com >=5 tokens (candidatos a data completa dd/mm/yyyy, {len(exemplos_longos)} total):')
for sid, texto in exemplos_longos[:20]:
    print(f'  id={sid}: "{texto}"')
