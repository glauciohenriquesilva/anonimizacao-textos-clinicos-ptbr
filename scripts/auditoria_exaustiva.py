# -*- coding: utf-8 -*-
from collections import defaultdict
from anotador.models import Sentenca

SESSAO_ID = 5

STOPWORDS_BORDA = {'DE','DA','DO','DOS','DAS','E','NO','NA','NOS','NAS','EM','COM',
                    'A','O','AO','AOS','À','ÀS','QUE','SEM'}

PARENTESCO = {'MAE','MÃE','PAI','FILHO','FILHA','IRMAO','IRMÃO','IRMA','IRMÃ',
              'ESPOSO','ESPOSA','PRIMA','PRIMO','TIO','TIA','AVO','AVÔ','AVÓ',
              'NETO','NETA','SOBRINHO','SOBRINHA','CONJUGE','CÔNJUGE','MADRASTA',
              'PADRASTO','ENTEADO','ENTEADA','CUNHADO','CUNHADA','NORA','GENRO',
              'SOGRO','SOGRA','COMPANHEIRO','COMPANHEIRA','GENITORA','GENITOR'}

ABREV_HOSPITAL = ['HESVV', 'HRAS', 'HEAC', 'HESA', 'HEUE', 'HEC', 'HINSG', 'HSAT', 'HDRAS']

sentencas = list(Sentenca.objects.filter(sessao_id=SESSAO_ID).prefetch_related('anotacoes'))

# estruturas de coleta
spans_por_tipo = defaultdict(list)  # tipo -> [(sentenca_id, [posicoes], texto)]
abrev_contagem = defaultdict(lambda: defaultdict(int))  # abrev -> label -> count
parentesco_incluido = []
fronteira_problema = []

total_sentencas_anotadas = 0

for s in sentencas:
    tokens = s.tokens
    anot = {a.posicao: a.label for a in s.anotacoes.all()}
    if not anot:
        continue
    total_sentencas_anotadas += 1

    # reconstroi spans por tipo
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
        texto = ' '.join(tokens[i] for i in span)
        spans_por_tipo[tipo].append((s.id, span, texto))

        # checagem de fronteira (so tipos onde isso importa)
        if tipo in ('PESSOA', 'ENDERECO', 'INSTITUICAO', 'DOCUMENTO'):
            primeiro = tokens[span[0]].upper().strip('.,;:')
            ultimo = tokens[span[-1]].upper().strip('.,;:')
            if primeiro in STOPWORDS_BORDA or ultimo in STOPWORDS_BORDA:
                fronteira_problema.append((s.id, tipo, texto))

        # checagem de parentesco incluido no span de PESSOA
        if tipo == 'PESSOA':
            for pos in span:
                if tokens[pos].upper().strip('.,;:') in PARENTESCO:
                    parentesco_incluido.append((s.id, texto, tokens[pos]))

    # checagem de abreviacoes de hospital
    for i, tok in enumerate(tokens):
        tok_upper = tok.upper().strip('.,;:()')
        if tok_upper in ABREV_HOSPITAL:
            lbl = anot.get(i, 'O')
            abrev_contagem[tok_upper][lbl] += 1

print('=' * 70)
print(f'AUDITORIA EXAUSTIVA — sessao {SESSAO_ID} — {total_sentencas_anotadas} sentencas anotadas')
print('=' * 70)

print()
print('--- Contagem atualizada de spans por tipo ---')
for tipo in ['PESSOA', 'ENDERECO', 'INSTITUICAO', 'DOCUMENTO', 'CONTATO', 'DATA', 'HORA']:
    n = len(spans_por_tipo.get(tipo, []))
    print(f'  {tipo:15s} {n}')

print()
print('=' * 70)
print(f'CHECAGEM A — Span comeca ou termina com preposicao/artigo isolado: {len(fronteira_problema)}')
print('=' * 70)
for sid, tipo, texto in fronteira_problema:
    print(f'  id={sid} [{tipo}] "{texto}"')

print()
print('=' * 70)
print(f'CHECAGEM B — Grau de parentesco incluido dentro do span de PESSOA: {len(parentesco_incluido)}')
print('=' * 70)
for sid, texto, palavra in parentesco_incluido:
    print(f'  id={sid} span="{texto}" (palavra de parentesco: "{palavra}")')

print()
print('=' * 70)
print('CHECAGEM C — Consistencia de siglas de hospital conhecidas (INSTITUICAO vs O)')
print('=' * 70)
for abrev in ABREV_HOSPITAL:
    labels = abrev_contagem.get(abrev)
    if not labels:
        continue
    resumo = ', '.join(f'{lbl}={n}' for lbl, n in sorted(labels.items(), key=lambda x: -x[1]))
    print(f'  {abrev:8s} -> {resumo}')

print()
print('=' * 70)
print('CHECAGEM D — Spans mais longos por tipo (outliers, top 3)')
print('=' * 70)
for tipo in ['PESSOA', 'INSTITUICAO', 'DOCUMENTO', 'ENDERECO']:
    lst = sorted(spans_por_tipo.get(tipo, []), key=lambda x: -len(x[1]))[:3]
    print(f'  {tipo}:')
    for sid, span, texto in lst:
        print(f'    id={sid} ({len(span)} tok) "{texto}"')

print()
print('=' * 70)
print('CHECAGEM E — Spans PESSOA/INSTITUICAO muito curtos (1 token, <=2 caracteres ou nao-alfa)')
print('=' * 70)
for tipo in ['PESSOA', 'INSTITUICAO']:
    for sid, span, texto in spans_por_tipo.get(tipo, []):
        if len(span) == 1 and (len(texto) <= 2 or not texto.isalpha()):
            print(f'  id={sid} [{tipo}] "{texto}"')

print()
print('=' * 70)
print('CHECAGEM F — Todos os spans DOCUMENTO (lista completa para revisao)')
print('=' * 70)
for sid, span, texto in spans_por_tipo.get('DOCUMENTO', []):
    print(f'  id={sid} "{texto}"')
