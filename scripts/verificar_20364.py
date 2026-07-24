# -*- coding: utf-8 -*-
from anotador.models import Sentenca, AnotacaoToken

s = Sentenca.objects.get(id=20364)
print(f'tokens: {len(s.tokens)}')
print(f'token[43]: "{s.tokens[43]}"')
anot = AnotacaoToken.objects.filter(sentenca_id=20364).order_by('posicao')
posicoes = [a.posicao for a in anot]
print(f'total registros: {len(posicoes)}')
print(f'posicoes duplicadas: {[p for p in set(posicoes) if posicoes.count(p) > 1]}')
print(f'max posicao: {max(posicoes)}, min: {min(posicoes)}')
# verifica se e uma sequencia continua 0..N-1
esperado = set(range(len(s.tokens)))
faltando = esperado - set(posicoes)
sobrando = set(posicoes) - esperado
print(f'posicoes faltando: {sorted(faltando)[:20]}')
print(f'posicoes sobrando (fora do range de tokens): {sorted(sobrando)[:20]}')
print(f'label na posicao 43: {[a.label for a in anot if a.posicao == 43]}')
print(f'label na posicao 44: {[a.label for a in anot if a.posicao == 44]}')
