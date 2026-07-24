# -*- coding: utf-8 -*-
from anotador.models import Sentenca

SESSAO_ID = 5
sentencas = Sentenca.objects.filter(sessao_id=SESSAO_ID).prefetch_related('anotacoes')

for s in sentencas:
    tokens = s.tokens
    anot = {a.posicao: a.label for a in s.anotacoes.all()}
    if not anot:
        continue
    for i, tok in enumerate(tokens):
        tu = tok.upper().strip('.,;:()')
        if tu in ('HEUE', 'HEC') and anot.get(i, 'O') == 'O':
            ctx = ' '.join(tokens[max(0,i-5):i+6])
            print(f'id={s.id} token="{tok}" label=O | ...{ctx}...')
