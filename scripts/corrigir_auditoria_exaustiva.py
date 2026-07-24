# -*- coding: utf-8 -*-
# Corrige os achados SEGUROS da auditoria exaustiva (21/07/2026):
#
# A) Siglas de hospital (HEUE, HEC) que apareceram como O em vez de B-INSTITUICAO
#    -- correcao inequivoca, mesmo padrao ja usado 30+ vezes no resto do corpus.
#
# B) Spans de 1 token contaminados por erro de digitacao (Padroes 6/7/8) que foram
#    forcados como entidade em vez de O -- revertidos para O, mesma convencao ja
#    aplicada no caso "CIRURGIA.ATT,FABIANA" (nao força rotulo em token que mistura
#    PHI com texto nao-PHI, pois isso injeta ruido contraditorio no treino).
#
# NAO mexe em:
#  - "CRM 7061Validado" e "1323046Motivo" (contaminacao parcial em span de 2 tokens
#    do tipo DOCUMENTO -- corrigir aqui exigiria decisao token-a-token mais fina,
#    deixado para revisao manual)
#  - "CNS : 700507954980553 3" (digito extra suspeito no final -- precisa conferir
#    contra o texto original antes de decidir se e parte do numero ou nao)
#  - CRN / CREFITO como DOCUMENTO (isso e uma decisao de escopo a formalizar, nao
#    uma correcao de anotacao ja feita)

from anotador.models import Sentenca, AnotacaoToken

total = 0

# ---------------------------------------------------------------------------
# A) HEUE / HEC faltando como INSTITUICAO
# ---------------------------------------------------------------------------
ALVOS_HOSPITAL = [20551, 21615, 21819, 22095]  # 22095 tem 2 ocorrencias

for sid in ALVOS_HOSPITAL:
    s = Sentenca.objects.get(id=sid)
    tokens = s.tokens
    anot = {a.posicao: a for a in s.anotacoes.all()}
    for i, tok in enumerate(tokens):
        tu = tok.upper().strip('.,;:()')
        if tu in ('HEUE', 'HEC') and anot.get(i) and anot[i].label == 'O':
            obj = anot[i]
            obj.label = 'B-INSTITUICAO'
            obj.save()
            total += 1
            print(f'OK id={sid} pos={i} token="{tok}" O -> B-INSTITUICAO')

# ---------------------------------------------------------------------------
# B) Tokens contaminados forcados como entidade -> revertidos para O
# ---------------------------------------------------------------------------
CONTAMINADOS = [
    (20030, 'PATRICIA,24', 'B-PESSOA'),
    (20654, '32222814Josemar', 'B-PESSOA'),
    (20798, 'Cinthia,porém', 'B-PESSOA'),
    (22128, 'MIRIAN,MIRENEZ', 'B-PESSOA'),
    (22150, 'Rodrigues.Realizo', 'B-PESSOA'),
    (21436, 'Social.Mylena', 'B-INSTITUICAO'),
    (21709, '15hHEUE', 'B-INSTITUICAO'),
]

for sid, texto_esperado, label_esperado in CONTAMINADOS:
    s = Sentenca.objects.get(id=sid)
    tokens = s.tokens
    anot = {a.posicao: a for a in s.anotacoes.all()}
    achou = False
    for i, tok in enumerate(tokens):
        if tok == texto_esperado and anot.get(i) and anot[i].label == label_esperado:
            obj = anot[i]
            antigo = obj.label
            obj.label = 'O'
            obj.save()
            total += 1
            print(f'OK id={sid} pos={i} token="{tok}" {antigo} -> O')
            achou = True
            break
    if not achou:
        print(f'NAO ENCONTRADO id={sid} texto="{texto_esperado}" label_esperado={label_esperado} (conferir manualmente)')

print()
print(f'Total de registros corrigidos: {total}')
