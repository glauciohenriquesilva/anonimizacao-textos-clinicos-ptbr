# -*- coding: utf-8 -*-
# Corrige os 3 novos casos de HEUE perdido como O, encontrados na segunda
# rodada da auditoria exaustiva (21/07/2026, 3011 sentencas).

from anotador.models import Sentenca

ALVOS = [22198, 22772, 22913]
total = 0

for sid in ALVOS:
    s = Sentenca.objects.get(id=sid)
    tokens = s.tokens
    anot = {a.posicao: a for a in s.anotacoes.all()}
    for i, tok in enumerate(tokens):
        if tok.upper().strip('.,;:()') == 'HEUE' and anot.get(i) and anot[i].label == 'O':
            obj = anot[i]
            obj.label = 'B-INSTITUICAO'
            obj.save()
            total += 1
            print(f'OK id={sid} pos={i} token="{tok}" O -> B-INSTITUICAO')

print()
print(f'Total de registros corrigidos: {total}')
