# -*- coding: utf-8 -*-
from anotador.models import Sentenca

for sid, pos in [(20004, 11), (20009, 20), (20013, 47), (20014, 28)]:
    s = Sentenca.objects.get(id=sid)
    tokens = s.tokens
    janela = tokens[max(0,pos-3):pos+6]
    print(f'id={sid} pos={pos}: ...{" ".join(janela)}...')
