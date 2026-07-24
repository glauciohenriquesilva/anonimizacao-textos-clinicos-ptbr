# -*- coding: utf-8 -*-
from anotador.models import Sentenca, AnotacaoToken

ALVOS = [
    (20153, "NOVA VENECIA"),
    (20495, "Domingos Martins"),
    (20495, "Campo Grande / Cariacica"),
    (20740, "Vila Velha"),
    (20773, "SAO MATEUS"),
    (20804, "NOVA VENECIA"),
    (20818, "SÃO PAULO"),
    (20856, "SAO MATEUS"),
    (20991, "NOVA VENÉCIA"),
    (20628, "COLATINA"),
    (20867, "COLATINA"),
    (21522, "COLATINA"),
    (20835, "VILA VELHA"),
    (21550, "GUARAPARI"),
    (21867, "VILA VELHA"),
]

total_corrigidos = 0
nao_encontrados = []

for sid, span_texto in ALVOS:
    s = Sentenca.objects.get(id=sid)
    tokens = s.tokens
    anot = {a.posicao: a.label for a in s.anotacoes.all()}

    spans = []
    cur = []
    for i in range(len(tokens)):
        lbl = anot.get(i, 'O')
        if lbl in ('B-ENDERECO', 'I-ENDERECO'):
            if lbl == 'B-ENDERECO' and cur:
                spans.append(cur)
                cur = []
            cur.append(i)
        else:
            if cur:
                spans.append(cur)
                cur = []
    if cur:
        spans.append(cur)

    achou = False
    for span in spans:
        texto = ' '.join(tokens[i] for i in span)
        if texto == span_texto:
            achou = True
            n = AnotacaoToken.objects.filter(sentenca_id=sid, posicao__in=span).update(label='O')
            total_corrigidos += n
            print(f'OK id={sid} span="{texto}" ({len(span)} tokens, {n} registros) revertido para O')
            break
    if not achou:
        nao_encontrados.append((sid, span_texto))

print()
print(f'Total de registros AnotacaoToken corrigidos: {total_corrigidos}')
if nao_encontrados:
    print('NAO ENCONTRADOS (verificar manualmente):')
    for sid, texto in nao_encontrados:
        print(f'  id={sid} span="{texto}"')
