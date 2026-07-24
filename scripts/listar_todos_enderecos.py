# -*- coding: utf-8 -*-
from anotador.models import Sentenca

SESSAO_ID = 5
MARCADOR_RUA = {'RUA', 'AV', 'AV.', 'AVENIDA', 'BAIRRO', 'Nº', 'N°', 'NO', 'LOGRADOURO',
                'TRAVESSA', 'ALAMEDA', 'ESTRADA', 'RODOVIA', 'QUADRA', 'LOTE', 'APTO', 'APT', 'CEP'}

sentencas = Sentenca.objects.filter(sessao_id=SESSAO_ID)
linhas = []

for s in sentencas:
    tokens = s.tokens
    anot = {a.posicao: a.label for a in s.anotacoes.all()}
    if not anot:
        continue

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
    if not spans:
        continue

    tokens_upper = [t.upper().strip(',.:;()') for t in tokens]
    tem_marcador_rua = any(t in MARCADOR_RUA for t in tokens_upper)

    for span in spans:
        texto_span = ' '.join(tokens[i] for i in span)
        frase = ' '.join(tokens)
        linhas.append((len(span), tem_marcador_rua, s.id, s.ordem, texto_span, frase))

# ordenar: spans curtos e sem marcador de rua primeiro (candidatos mais suspeitos)
linhas.sort(key=lambda x: (x[1], x[0]))

print(f'Total de spans ENDERECO: {len(linhas)}')
print()
for tam, tem_rua, sid, ordem, texto_span, frase in linhas:
    flag = 'RUA/BAIRRO no contexto' if tem_rua else 'SEM marcador de rua'
    print(f'[{tam} tok | {flag}] id={sid} ordem={ordem} span="{texto_span}"')
    print(f'    {frase}')
