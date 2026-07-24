# -*- coding: utf-8 -*-
# Corrige os 3 erros reais de anotacao encontrados na auditoria geral (21/07/2026):
# - DAIANE (id 20273) e Geralda (id 20342): nomes de pessoa marcados com label errado
# - JOSE THEOFILO DUTRA MAGALHAES (id 21859): nome de medico prestador marcado como DATA
# Nao altera nada alem desses tokens especificos.

from anotador.models import Sentenca

CORRECOES_SIMPLES = [
    # (sentenca_id, texto_esperado, label_atual_esperado)
    (20273, 'DAIANE', 'B-DATA'),
    (20342, 'Geralda', 'B-CONTATO'),
]

total = 0

for sid, texto_esperado, label_esperado in CORRECOES_SIMPLES:
    s = Sentenca.objects.get(id=sid)
    tokens = s.tokens
    anot = {a.posicao: a for a in s.anotacoes.all()}
    achou = False
    for i, tok in enumerate(tokens):
        if tok == texto_esperado and anot.get(i) and anot[i].label == label_esperado:
            obj = anot[i]
            antigo = obj.label
            obj.label = 'B-PESSOA'
            obj.save()
            total += 1
            print(f'OK id={sid} pos={i} token="{tok}" {antigo} -> B-PESSOA')
            achou = True
            break
    if not achou:
        print(f'NAO ENCONTRADO id={sid} texto="{texto_esperado}" label_esperado={label_esperado} (conferir manualmente)')

# Caso especial: JOSE THEOFILO DUTRA MAGALHAES (id 21859)
# THEOFILO, DUTRA e MAGALHAES estavam cada um como B-DATA isolado (deveriam ser
# continuacao do nome). Verifica o token anterior (esperado "JOSE") para decidir
# se a correcao vira B-PESSOA + I-PESSOA + I-PESSOA (se JOSE ainda nao for PESSOA)
# ou I-PESSOA + I-PESSOA + I-PESSOA (se JOSE ja estiver como B-PESSOA).
sid = 21859
s = Sentenca.objects.get(id=sid)
tokens = s.tokens
anot = {a.posicao: a for a in s.anotacoes.all()}

alvo_textos = ['THEOFILO', 'DUTRA', 'MAGALHAES']
posicoes = sorted(
    i for i, t in enumerate(tokens)
    if t in alvo_textos and anot.get(i) and anot[i].label in ('B-DATA', 'I-DATA')
)

if posicoes:
    pos_ant = posicoes[0] - 1
    label_ant = anot[pos_ant].label if pos_ant in anot else 'O'
    tok_ant = tokens[pos_ant] if pos_ant >= 0 else None
    print(f'Token anterior a THEOFILO: "{tok_ant}" label="{label_ant}"')

    if label_ant in ('B-PESSOA', 'I-PESSOA'):
        novo_label_primeiro = 'I-PESSOA'
    else:
        novo_label_primeiro = 'B-PESSOA'
        print(f'ATENCAO: token anterior ("{tok_ant}") nao esta como PESSOA — '
              f'corrija manualmente se for mesmo parte do nome (ex: "JOSE").')

    for idx, pos in enumerate(posicoes):
        obj = anot[pos]
        antigo = obj.label
        obj.label = novo_label_primeiro if idx == 0 else 'I-PESSOA'
        obj.save()
        total += 1
        print(f'OK id={sid} pos={pos} token="{tokens[pos]}" {antigo} -> {obj.label}')
else:
    print(f'NAO ENCONTRADO id={sid} tokens esperados={alvo_textos} (conferir manualmente)')

print()
print(f'Total de registros corrigidos: {total}')
