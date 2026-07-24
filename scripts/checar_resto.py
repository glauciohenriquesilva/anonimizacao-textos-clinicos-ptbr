# -*- coding: utf-8 -*-
from anotador.models import Sentenca

SESSAO_ID = 5
sentencas = Sentenca.objects.filter(sessao_id=SESSAO_ID).prefetch_related('anotacoes')

for s in sentencas:
    tokens = s.tokens
    anot = {a.posicao: a.label for a in s.anotacoes.all()}
    if not anot:
        continue
    for i, lbl in anot.items():
        if lbl == 'B-CONTATO':
            print(f'CONTATO: id={s.id} token="{tokens[i]}" ctx=...{" ".join(tokens[max(0,i-4):i+5])}...')

    # spans de 2 tokens de DATA
    spans = []
    cur = []
    for i in range(len(tokens)):
        l = anot.get(i, 'O')
        if l in ('B-DATA', 'I-DATA'):
            if l == 'B-DATA' and cur:
                spans.append(cur); cur = []
            cur.append(i)
        else:
            if cur:
                spans.append(cur); cur = []
    if cur:
        spans.append(cur)
    for span in spans:
        if len(span) == 2:
            texto = ' '.join(tokens[i] for i in span)
            ctx = ' '.join(tokens[max(0,span[0]-3):span[-1]+4])
            print(f'DATA 2tok: id={s.id} "{texto}" ctx=...{ctx}...')
