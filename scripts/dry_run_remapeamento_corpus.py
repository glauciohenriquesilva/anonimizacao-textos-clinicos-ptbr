# -*- coding: utf-8 -*-
# Task #25 -- Fase 2 (DRY RUN, somente leitura) -- v4 FINAL.
# Mesma logica exata do script de escrita (aplicar_remapeamento_corpus.py), incluindo
# os 2 fixes de regex (RG/CEP vs telefone) e os 26 julgamentos de fronteira de
# entidade decididos manualmente. Usado so para conferir os numeros finais antes de
# rodar de verdade.

import difflib
from collections import defaultdict
from anotador.models import Sentenca, AnotacaoToken
from preprocessamento.services.preprocessamento import (
    corrigir_erros_digitacao, normalizar_datas_no_texto, mascarar_datas_horas,
    mascarar_horas, mascarar_cpf, mascarar_telefone, mascarar_cep, mascarar_email,
    tokenizar_word_level,
)

FAMILIA_REGEX_ONLY = {'B-DATA', 'I-DATA', 'B-HORA', 'I-HORA', 'B-CONTATO', 'I-CONTATO'}
PLACEHOLDERS = ('__DATA__', '__HORA__', '__TELEFONE__', '__CPF__', '__CEP__', '__EMAIL__')

PRECEDENTE_PADRAO10 = {
    20364: ['I-ENDERECO', 'O'],
    20774: ['I-ENDERECO', 'O'],
    21160: ['I-INSTITUICAO', 'O'],
    21699: ['I-ENDERECO', 'O'],
    21839: ['I-ENDERECO', 'O'],
    22150: ['I-PESSOA', 'O'],
    22208: ['I-PESSOA', 'O'],
    22656: ['I-ENDERECO', 'O'],
    22979: ['I-PESSOA', 'O'],
}

PRECEDENTE_FRONTEIRA_24072026 = {
    20227: ['I-ENDERECO', 'I-ENDERECO', 'I-ENDERECO'],
    5439:  ['I-ENDERECO', 'I-ENDERECO', 'I-ENDERECO'],
    5449:  ['O', 'O', 'B-PESSOA'],
    5732:  ['O', 'O', 'B-PESSOA'],
    5876:  ['I-INSTITUICAO', 'O', 'O'],
    21140: ['I-ENDERECO', 'O', 'O'],
    21318: ['I-DATA', 'O', 'O'],
    6340:  ['I-ENDERECO', 'I-ENDERECO'],
    6540:  ['O', 'O', 'B-PESSOA'],
    6658:  ['O', 'O', 'B-PESSOA'],
    22078: ['O', 'O', 'B-PESSOA'],
    7213:  ['I-ENDERECO', 'I-ENDERECO', 'I-ENDERECO'],
    7616:  ['B-PESSOA', 'I-PESSOA', 'I-PESSOA'],
    23169: ['I-ENDERECO', 'O', 'O'],
    23275: ['I-ENDERECO', 'O', 'O'],
    8527:  ['B-PESSOA', 'O', 'B-PESSOA'],
    23818: ['B-PESSOA', 'O', 'O'],
    23871: ['I-ENDERECO', 'O', 'O'],
    9014:  ['B-HORA', 'I-HORA'],
    9107:  ['B-ENDERECO', 'I-ENDERECO'],
    24111: ['I-ENDERECO', 'O', 'O'],
    24150: ['I-ENDERECO', 'O', 'O'],
    9290:  ['I-ENDERECO', 'I-ENDERECO', 'I-ENDERECO'],
    24377: ['I-DATA', 'O', 'O'],
    24379: ['I-PESSOA', 'O', 'O'],
    24529: ['I-INSTITUICAO', 'O', 'O'],
}


OVERRIDE_SENTENCA_COMPLETA = {
    5449: {i: ('B-PESSOA' if i in (1, 14, 31) else 'O') for i in range(33)},
}


def eh_data_hora_cpf(token):
    import re
    return bool(
        re.fullmatch(r'\d{4}-\d{2}-\d{2}', token) or
        re.fullmatch(r'\d{1,2}:\d{1,2}', token) or
        re.fullmatch(r'\d{3}\.\d{3}\.\d{3}[-.]\d{2}', token)
    )


def reprocessar(tokens):
    texto = ' '.join(tokens)
    texto = corrigir_erros_digitacao(texto)
    texto = normalizar_datas_no_texto(texto)
    texto = mascarar_datas_horas(texto)
    texto = mascarar_horas(texto)
    texto = mascarar_cpf(texto)
    texto = mascarar_telefone(texto)
    texto = mascarar_cep(texto)
    texto = mascarar_email(texto)
    return tokenizar_word_level(texto)


def planejar_remapeamento(sentenca_id, tokens_antigos, tokens_novos, labels_por_posicao):
    sm = difflib.SequenceMatcher(None, tokens_antigos, tokens_novos, autojunk=False)
    plano = {}
    precedente = PRECEDENTE_PADRAO10.get(sentenca_id)
    fronteira = PRECEDENTE_FRONTEIRA_24072026.get(sentenca_id)

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            offset = j1 - i1
            for p in range(i1, i2):
                plano[p + offset] = labels_por_posicao.get(p, 'O')
            continue

        labels_envolvidos = [labels_por_posicao.get(p, 'O') for p in range(i1, i2)]
        tokens_envolvidos = tokens_antigos[i1:i2]
        novos_span = tokens_novos[j1:j2]
        n_old, n_new = i2 - i1, j2 - j1

        if precedente is not None and n_old == 1 and n_new == len(precedente):
            for k, label in enumerate(precedente):
                plano[j1 + k] = label
            continue

        if fronteira is not None and n_old == 1 and n_new == len(fronteira):
            for k, label in enumerate(fronteira):
                plano[j1 + k] = label
            continue

        if all(l == 'O' for l in labels_envolvidos):
            for jp in range(j1, j2):
                plano[jp] = 'O'
            continue

        if all(l == 'O' or l in FAMILIA_REGEX_ONLY for l in labels_envolvidos) and \
           any(ph in tok for tok in novos_span for ph in PLACEHOLDERS):
            for jp in range(j1, j2):
                plano[jp] = 'O'
            continue

        if all(eh_data_hora_cpf(tok) for tok in tokens_envolvidos) and \
           any(ph in tok for tok in novos_span for ph in PLACEHOLDERS):
            for jp in range(j1, j2):
                plano[jp] = 'O'
            continue

        return f'{tag} {n_old}->{n_new} em pos {i1}-{i2}', False

    return plano, True


total_afetadas = 0
auto_ok = 0
flagadas = []

for s in Sentenca.objects.all().iterator(chunk_size=500):
    tokens_antigos = s.tokens
    tokens_novos = reprocessar(tokens_antigos)

    if tokens_novos == tokens_antigos:
        continue

    total_afetadas += 1

    anotacoes = list(AnotacaoToken.objects.filter(sentenca=s))
    por_anotador = defaultdict(dict)
    for a in anotacoes:
        por_anotador[a.anotador_id][a.posicao] = a.label

    sentenca_ok = True
    motivo_falha = None

    if s.id in OVERRIDE_SENTENCA_COMPLETA:
        plano_override = OVERRIDE_SENTENCA_COMPLETA[s.id]
        if set(plano_override.keys()) != set(range(len(tokens_novos))):
            sentenca_ok = False
            motivo_falha = 'override desatualizado'
    else:
        for anotador_id, labels_por_posicao in por_anotador.items():
            plano, ok = planejar_remapeamento(s.id, tokens_antigos, tokens_novos, labels_por_posicao)
            if not ok:
                sentenca_ok = False
                motivo_falha = plano
                break
            if set(plano.keys()) != set(range(len(tokens_novos))):
                sentenca_ok = False
                motivo_falha = 'cobertura incompleta'
                break

    if sentenca_ok:
        auto_ok += 1
    else:
        flagadas.append((s.id, s.ordem, motivo_falha))

print(f'Total de sentencas afetadas (tokens mudam): {total_afetadas}')
print(f'Remapeamento automatico possivel: {auto_ok}')
print(f'Flagadas para revisao manual: {len(flagadas)}')
print()
for sid, ordem, motivo in flagadas:
    print(f'  id={sid} ordem={ordem}: {motivo}')
