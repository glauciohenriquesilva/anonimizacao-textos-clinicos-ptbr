# -*- coding: utf-8 -*-
from collections import defaultdict
from anotador.models import Sentenca

SESSAO_ID = 5
ENTIDADES = ['PESSOA', 'DATA', 'ENDERECO', 'CONTATO', 'DOCUMENTO', 'HORA', 'INSTITUICAO']
PROIBIDAS_NO_GOLD = {'DATA', 'HORA', 'CONTATO'}  # decisao 2026-06-19: tratadas so por regex

sentencas = list(Sentenca.objects.filter(sessao_id=SESSAO_ID).prefetch_related('anotacoes'))

total_sentencas_anotadas = 0
total_tokens = 0
contagem_spans = defaultdict(int)
contagem_tokens_label = defaultdict(int)
comprimentos_span = defaultdict(list)

spans_proibidos = []
bio_orfaos = []
spans_por_tipo_texto = defaultdict(lambda: defaultdict(set))  # texto_normalizado -> tipo -> set(sentenca_id)

titulos = {'sr', 'sra', 'dr', 'dra'}
titulos_inconsistentes = []

for s in sentencas:
    tokens = s.tokens
    anot_qs = list(s.anotacoes.all())
    if not anot_qs:
        continue
    total_sentencas_anotadas += 1
    total_tokens += len(tokens)
    anot = {a.posicao: a.label for a in anot_qs}

    for i, lbl in anot.items():
        contagem_tokens_label[lbl] += 1

    # checagem 1: labels proibidas no gold standard
    for i, lbl in anot.items():
        if lbl != 'O':
            tipo = lbl.split('-', 1)[1]
            if tipo in PROIBIDAS_NO_GOLD:
                spans_proibidos.append((s.id, s.ordem, i, tokens[i] if i < len(tokens) else '?', lbl))

    # checagem 2: BIO orfao (I-X sem B-X ou I-X imediatamente antes)
    for i in range(len(tokens)):
        lbl = anot.get(i, 'O')
        if lbl.startswith('I-'):
            tipo = lbl.split('-', 1)[1]
            prev = anot.get(i - 1, 'O') if i > 0 else 'O'
            prev_tipo = prev.split('-', 1)[1] if prev != 'O' else None
            if prev == 'O' or prev_tipo != tipo:
                bio_orfaos.append((s.id, s.ordem, i, tokens[i], lbl, prev))

    # checagem 3: reconstrucao de spans por tipo + consistencia sr/dr
    spans = []
    cur = []
    cur_tipo = None
    for i in range(len(tokens)):
        lbl = anot.get(i, 'O')
        if lbl != 'O':
            tipo = lbl.split('-', 1)[1]
            if lbl.startswith('B-') and cur:
                spans.append((cur, cur_tipo))
                cur = []
            cur.append(i)
            cur_tipo = tipo
        else:
            if cur:
                spans.append((cur, cur_tipo))
                cur = []
                cur_tipo = None
    if cur:
        spans.append((cur, cur_tipo))

    for span, tipo in spans:
        contagem_spans[tipo] += 1
        comprimentos_span[tipo].append(len(span))
        texto = ' '.join(tokens[i] for i in span).strip().upper()
        spans_por_tipo_texto[texto][tipo].add(s.id)

    # checagem 4: titulos sr/sra/dr/dra sempre com o nome seguinte anotado
    for i, tok in enumerate(tokens):
        if tok.lower().strip('.') in titulos:
            lbl_titulo = anot.get(i, 'O')
            prox_lbl = anot.get(i + 1, 'O') if i + 1 < len(tokens) else 'O'
            if prox_lbl == 'O' and lbl_titulo == 'O':
                # nem o titulo nem o proximo token foram marcados -- pode ser legitimo
                # (titulo seguido de pontuacao, nao de nome) -- so flag se o proximo token
                # comeca com maiuscula e parece um nome (heuristica leve)
                prox = tokens[i + 1] if i + 1 < len(tokens) else ''
                if prox and prox[0].isupper() and prox.isalpha() and len(prox) > 2:
                    titulos_inconsistentes.append((s.id, s.ordem, tok, prox))

print('=' * 70)
print(f'AUDITORIA GERAL — sessao {SESSAO_ID}')
print('=' * 70)
print(f'Sentencas com pelo menos 1 anotacao: {total_sentencas_anotadas}')
print(f'Total de tokens nessas sentencas: {total_tokens}')
print()
print('--- Contagem de tokens por label ---')
for lbl, n in sorted(contagem_tokens_label.items(), key=lambda x: -x[1]):
    print(f'  {lbl:20s} {n}')
print()
print('--- Contagem de spans (entidades completas) por tipo ---')
for tipo in ENTIDADES:
    n = contagem_spans.get(tipo, 0)
    comps = comprimentos_span.get(tipo, [])
    media = sum(comps) / len(comps) if comps else 0
    print(f'  {tipo:15s} spans={n:5d}  comprimento_medio={media:.2f} tokens')
print()

print('=' * 70)
print(f'CHECAGEM 1 — Labels proibidas no gold standard (DATA/HORA/CONTATO): {len(spans_proibidos)}')
print('=' * 70)
for sid, ordem, pos, tok, lbl in spans_proibidos[:30]:
    print(f'  id={sid} ordem={ordem} pos={pos} token="{tok}" label={lbl}')
if len(spans_proibidos) > 30:
    print(f'  ... e mais {len(spans_proibidos) - 30}')
print()

print('=' * 70)
print(f'CHECAGEM 2 — Tags I- orfas (sem B- ou I- do mesmo tipo antes): {len(bio_orfaos)}')
print('=' * 70)
for sid, ordem, pos, tok, lbl, prev in bio_orfaos[:30]:
    print(f'  id={sid} ordem={ordem} pos={pos} token="{tok}" label={lbl} (anterior="{prev}")')
if len(bio_orfaos) > 30:
    print(f'  ... e mais {len(bio_orfaos) - 30}')
print()

print('=' * 70)
print('CHECAGEM 3 — Mesmo texto anotado com tipos de entidade diferentes')
print('=' * 70)
conflitos = {txt: tipos for txt, tipos in spans_por_tipo_texto.items() if len(tipos) > 1}
print(f'Textos com mais de um tipo de entidade no corpus: {len(conflitos)}')
for txt, tipos in list(conflitos.items())[:40]:
    resumo = ', '.join(f'{tipo}({len(ids)}x)' for tipo, ids in tipos.items())
    print(f'  "{txt}" -> {resumo}')
if len(conflitos) > 40:
    print(f'  ... e mais {len(conflitos) - 40}')
print()

print('=' * 70)
print(f'CHECAGEM 4 — Titulo (Sr/Sra/Dr/Dra) seguido de provavel nome nao anotado: {len(titulos_inconsistentes)}')
print('=' * 70)
for sid, ordem, tit, prox in titulos_inconsistentes[:30]:
    print(f'  id={sid} ordem={ordem} titulo="{tit}" proximo="{prox}" (nenhum marcado)')
if len(titulos_inconsistentes) > 30:
    print(f'  ... e mais {len(titulos_inconsistentes) - 30}')
