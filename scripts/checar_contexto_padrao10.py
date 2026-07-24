# -*- coding: utf-8 -*-
from anotador.models import Sentenca

CASOS = [(20364,43),(20774,14),(20774,88),(21160,10),(21699,30),(21839,29),
         (22150,21),(22150,32),(22208,25),(22656,13),(22979,27)]

for sid, pos in CASOS:
    s = Sentenca.objects.get(id=sid)
    tokens = s.tokens
    anot = {a.posicao: a.label for a in s.anotacoes.all()}
    janela_ini = max(0, pos-5)
    janela_fim = min(len(tokens), pos+6)
    partes = []
    for i in range(janela_ini, janela_fim):
        lbl = anot.get(i, 'O')
        marca = f'[{tokens[i]}/{lbl}]' if lbl != 'O' else tokens[i]
        partes.append(marca)
    print(f'id={sid} pos={pos}: ' + ' '.join(partes))
