# -*- coding: utf-8 -*-
from anotador.models import Sentenca

SESSAO_ID = 5
sentencas = Sentenca.objects.filter(sessao_id=SESSAO_ID).prefetch_related('anotacoes')

achados = []
for s in sentencas:
    tokens = s.tokens
    anot = {a.posicao: a.label for a in s.anotacoes.all()}
    if not anot:
        continue
    for i, lbl in anot.items():
        if lbl == 'B-DATA':
            nxt = anot.get(i + 1, 'O')
            if nxt not in ('I-DATA',):
                achados.append((s.id, tokens[i], ' '.join(tokens[max(0,i-3):i+4])))

print(f'Total spans DATA de 1 token: {len(achados)}')
for sid, tok, ctx in achados:
    print(f'  id={sid} token="{tok}" | ...{ctx}...')
