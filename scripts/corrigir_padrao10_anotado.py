# -*- coding: utf-8 -*-
# Corrige os 11 casos de tokens contaminados pelo Padrao 10 que ja tinham sido
# anotados (encontrados em varredura na base, 21/07/2026).
#
# Para cada caso: divide o token contaminado em dois tokens de verdade (prefixo
# com ponto + sufixo), reindexa TODAS as posicoes de AnotacaoToken depois do
# ponto de divisao (+1), e atribui o rotulo correto a cada metade.
#
# v2 (corrigido apos IntegrityError na v1): o deslocamento de posicoes agora
# roda em ordem DECRESCENTE (posicao mais alta primeiro), porque toda posicao
# de token tem uma linha AnotacaoToken (nao ha posicoes "vazias") -- deslocar
# em ordem crescente faz a posicao N tentar ocupar N+1 antes de N+1 ter sido
# liberada, violando a constraint unique_together (sentenca, anotador, posicao).
# Tambem envolve cada sentenca numa transacao atomica: se algo falhar, desfaz
# tudo daquela sentenca em vez de deixar estado parcial.

from django.db import transaction
from anotador.models import Sentenca, AnotacaoToken

CORRECOES = [
    (20364, 43, 'Palestina.Paciente', 'Palestina.', 'I-ENDERECO', 'Paciente', 'O'),
    (20774, 14, 'cá.Sr',              'cá.',        'O',          'Sr',       'B-PESSOA'),
    (20774, 88, 'Almeida.Alberto',    'Almeida.',   'I-ENDERECO', 'Alberto',  'B-PESSOA'),
    (21160, 10, 'AFPES.Paciente',     'AFPES.',     'I-INSTITUICAO', 'Paciente', 'O'),
    (21699, 30, 'Serra.Sou',          'Serra.',     'I-ENDERECO', 'Sou',      'O'),
    (21839, 29, 'Floriano.Vou',       'Floriano.',  'I-ENDERECO', 'Vou',      'O'),
    (22150, 21, 'CONQUISTA.Informa',  'CONQUISTA.', 'I-PESSOA',   'Informa',  'O'),
    (22150, 32, 'velha.Paciente',     'velha.',     'I-INSTITUICAO', 'Paciente', 'O'),
    (22208, 25, 'Junior.Deixa',       'Junior.',    'I-PESSOA',   'Deixa',    'O'),
    (22656, 13, 'Cypreste.Contato',   'Cypreste.',  'I-ENDERECO', 'Contato',  'O'),
    (22979, 27, 'Cristina.Repassou',  'Cristina.',  'I-PESSOA',   'Repassou', 'O'),
]

por_sentenca = {}
for sid, pos, texto, prefixo, lbl_pre, sufixo, lbl_suf in CORRECOES:
    por_sentenca.setdefault(sid, []).append((pos, texto, prefixo, lbl_pre, sufixo, lbl_suf))

total_tokens_divididos = 0
total_registros_atualizados = 0

for sid, itens in por_sentenca.items():
    itens.sort(key=lambda x: -x[0])  # posicao mais alta primeiro (entre correcoes da mesma sentenca)

    for pos, texto_esperado, prefixo, lbl_pre, sufixo, lbl_suf in itens:
        with transaction.atomic():
            s = Sentenca.objects.select_for_update().get(id=sid)
            tokens = s.tokens

            if tokens[pos] != texto_esperado:
                print(f'AVISO id={sid} pos={pos}: token atual "{tokens[pos]}" != esperado '
                      f'"{texto_esperado}" -- pulando')
                continue

            novos_tokens = tokens[:pos] + [prefixo, sufixo] + tokens[pos + 1:]

            # desloca em ordem DECRESCENTE -- libera a posicao de cima antes de
            # a de baixo tentar ocupa-la
            deslocar = list(
                AnotacaoToken.objects.filter(sentenca_id=sid, posicao__gt=pos).order_by('-posicao')
            )
            for a in deslocar:
                a.posicao += 1
                a.save()

            alvo = AnotacaoToken.objects.get(sentenca_id=sid, posicao=pos)
            alvo.label = lbl_pre
            alvo.save()

            AnotacaoToken.objects.create(
                sentenca_id=sid, anotador_id=alvo.anotador_id, posicao=pos + 1, label=lbl_suf,
            )

            s.tokens = novos_tokens
            s.save()

            total_tokens_divididos += 1
            total_registros_atualizados += len(deslocar) + 2
            print(f'OK id={sid} pos={pos}: "{texto_esperado}" dividido em '
                  f'"{prefixo}"({lbl_pre}) + "{sufixo}"({lbl_suf}) -- '
                  f'{len(tokens)} tokens -> {len(novos_tokens)} tokens')

print()
print(f'Total de tokens divididos: {total_tokens_divididos}')
print(f'Total de registros AnotacaoToken tocados: {total_registros_atualizados}')
