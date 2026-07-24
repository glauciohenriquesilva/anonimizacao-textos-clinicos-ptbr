# -*- coding: utf-8 -*-
import re
from anotador.models import Sentenca

SESSAO_ID = 5
M = r'[A-ZÁÉÍÓÚÀÈÌÒÙÃÕÂÊÎÔÛÇ]'
m = r'[a-záéíóúàèìòùãõâêîôûç]'
PADRAO10 = re.compile(rf'^([A-Za-zÀ-ÿ]{{2,}})\.({M}{m}+)$')

sentencas = Sentenca.objects.filter(sessao_id=SESSAO_ID).prefetch_related('anotacoes')

candidatos = []
for s in sentencas:
    tokens = s.tokens
    anot = {a.posicao: a.label for a in s.anotacoes.all()}
    if not anot:
        continue
    for i, tok in enumerate(tokens):
        match = PADRAO10.match(tok)
        if match and anot.get(i, 'O') != 'O':
            candidatos.append((s.id, i, tok, anot[i], match.group(1), match.group(2)))

print(f'Total de candidatos (token bate no Padrao 10 E ja tem rotulo != O): {len(candidatos)}')
print()
for sid, pos, tok, label, prefixo, sufixo in candidatos:
    print(f'id={sid} pos={pos} token="{tok}" label={label}  ->  prefixo="{prefixo}" | sufixo="{sufixo}"')
