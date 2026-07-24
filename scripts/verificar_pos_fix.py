# -*- coding: utf-8 -*-
from anotador.models import Sentenca, AnotacaoToken

IDS = [20364, 20774, 21160, 21699, 21839, 22150, 22208, 22656, 22979]

for sid in IDS:
    s = Sentenca.objects.get(id=sid)
    n_tokens = len(s.tokens)
    anot = list(AnotacaoToken.objects.filter(sentenca_id=sid))
    posicoes = [a.posicao for a in anot]
    dup = [p for p in set(posicoes) if posicoes.count(p) > 1]
    esperado = set(range(n_tokens))
    faltando = esperado - set(posicoes)
    sobrando = set(posicoes) - esperado
    status = 'OK' if (len(anot) == n_tokens and not dup and not faltando and not sobrando) else 'PROBLEMA'
    print(f'id={sid}: tokens={n_tokens} registros={len(anot)} dup={dup} faltando={sorted(faltando)[:5]} sobrando={sorted(sobrando)[:5]} -> {status}')
