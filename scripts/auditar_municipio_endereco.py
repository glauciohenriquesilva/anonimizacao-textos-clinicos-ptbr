# -*- coding: utf-8 -*-
from anotador.models import Sentenca

SESSAO_ID = 5

GATILHO_MUNICIPIO = {'MUNICIPIO', 'MUNICÍPIO', 'CIDADE', 'RESIDE', 'RESIDENTE', 'NATURAL'}
MARCADOR_RUA = {'RUA', 'AV', 'AV.', 'AVENIDA', 'BAIRRO', 'Nº', 'N°', 'NO', 'LOGRADOURO',
                'TRAVESSA', 'ALAMEDA', 'ESTRADA', 'RODOVIA', 'QUADRA', 'LOTE', 'APTO', 'APT'}

sentencas = Sentenca.objects.filter(sessao_id=SESSAO_ID)
total_spans = 0
candidatos = []

for s in sentencas:
    tokens = s.tokens
    anot = {a.posicao: a.label for a in s.anotacoes.all()}
    if not anot:
        continue

    # reconstruir spans contiguos de ENDERECO
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
    total_spans += len(spans)

    tokens_upper = [t.upper() for t in tokens]
    tem_marcador_rua = any(t.strip(',.:;()') in MARCADOR_RUA for t in tokens_upper)

    for span in spans:
        ini, fim = span[0], span[-1]
        contexto_antes = tokens_upper[max(0, ini - 3):ini]
        gatilho = any(any(g in c for g in GATILHO_MUNICIPIO) for c in contexto_antes)
        span_len = len(span)
        if gatilho and not tem_marcador_rua and span_len <= 3:
            texto_span = ' '.join(tokens[i] for i in span)
            frase = ' '.join(tokens)
            candidatos.append((s.id, s.ordem, texto_span, frase))

print(f'Total de spans ENDERECO na sessao {SESSAO_ID}: {total_spans}')
print(f'Candidatos a "municipio isolado marcado como ENDERECO": {len(candidatos)}')
print()
for sid, ordem, texto_span, frase in candidatos:
    print(f'sentenca id={sid} ordem={ordem} span="{texto_span}"')
    print(f'   frase: {frase}')
