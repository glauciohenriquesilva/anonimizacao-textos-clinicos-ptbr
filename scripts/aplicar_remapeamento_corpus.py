# -*- coding: utf-8 -*-
# Task #25 -- Fase 3 (ESCRITA -- rodar localmente, fora do sandbox).
#
# Aplica o remapeamento automatico para as sentencas cujo plano foi validado como
# seguro pelas 3 regras da Fase 2 (dry run). Sentencas flagadas para revisao manual
# NAO sao tocadas -- ficam exatamente como estao ate serem revisadas na interface.
#
# Estrategia de escrita: para cada sentenca alterada, apaga TODAS as AnotacaoToken
# daquela sentenca e recria do zero nas novas posicoes, dentro de uma transacao
# atomica. Isso evita completamente o problema de colisao de UNIQUE constraint que
# exigia deslocamento em ordem decrescente nas correcoes pontuais anteriores --
# como a sentenca inteira e recalculada de uma vez, delete+create e mais simples e
# igualmente seguro.
#
# Antes de rodar: FACA BACKUP do banco (cópia do arquivo .sqlite3).

import difflib
from collections import defaultdict
from django.db import transaction
from anotador.models import Sentenca, AnotacaoToken
from preprocessamento.services.preprocessamento import (
    corrigir_erros_digitacao, normalizar_datas_no_texto, mascarar_datas_horas,
    mascarar_horas, mascarar_cpf, mascarar_telefone, mascarar_cep, mascarar_email,
    tokenizar_word_level,
)

FAMILIA_REGEX_ONLY = {'B-DATA', 'I-DATA', 'B-HORA', 'I-HORA', 'B-CONTATO', 'I-CONTATO'}
PLACEHOLDERS = ('__DATA__', '__HORA__', '__TELEFONE__', '__CPF__', '__CEP__', '__EMAIL__')

# Precedente estabelecido manualmente na sessao de 24/07/2026 (script
# corrigir_padrao10_anotado.py) para tokens "Palavra.PalavraSeguinte" que agora,
# apos o pipeline separar corretamente o ponto final em token proprio, precisam
# do mesmo veredito de entao aplicado as 3 posicoes resultantes.
# Formato: sentenca_id -> {posicao_relativa_no_novo_span: label}
PRECEDENTE_PADRAO10 = {
    20364: ['I-ENDERECO', 'O'],           # Palestina .  (Paciente ja separado antes, O preservado)
    20774: ['I-ENDERECO', 'O'],           # Almeida .    (Alberto ja separado antes, B-PESSOA preservado)
    21160: ['I-INSTITUICAO', 'O'],        # AFPES .      (Paciente ja separado antes, O preservado)
    21699: ['I-ENDERECO', 'O'],           # Serra .      (Sou ja separado antes, O preservado)
    21839: ['I-ENDERECO', 'O'],           # Floriano .   (Vou ja separado antes, O preservado)
    22150: ['I-PESSOA', 'O'],             # CONQUISTA .  (Informa ja separado antes, O preservado)
    22208: ['I-PESSOA', 'O'],             # Junior .     (Deixa ja separado antes, O preservado)
    22656: ['I-ENDERECO', 'O'],           # Cypreste .   (Contato ja separado antes, O preservado)
    22979: ['I-PESSOA', 'O'],             # Cristina .   (Repassou ja separado antes, O preservado)
}


# Julgamento de fronteira de entidade para os 28 casos flagados na auditoria de
# 24/07/2026 (relatorio_final_28_task25.json) que nao se enquadram nas regras
# automaticas 1/2/2b -- decidido caso a caso por Gláucio + Claude, com base no
# contexto completo de cada sentenca. 2 dos 28 (id 6354 RG, id 8669 CEP) nao
# precisam de entrada aqui: foram resolvidos corrigindo a colisao de regex direto
# em mascarar_telefone() (protecao contra rotulo RG/CEP), entao old_tokens ja bate
# com new_tokens para esses dois e nem entram mais no diff.
PRECEDENTE_FRONTEIRA_24072026 = {
    20227: ['I-ENDERECO', 'I-ENDERECO', 'I-ENDERECO'],  # AURORA , MUNICÍPIO -- endereco continua
    5439:  ['I-ENDERECO', 'I-ENDERECO', 'I-ENDERECO'],  # VALADARES 72 SANTA -- endereco continua
    5449:  ['O', 'O', 'B-PESSOA'],                       # ENF . GERISMAR -- ENF e titulo, nao nome
    5732:  ['O', 'O', 'B-PESSOA'],                       # SR . JADSON -- SR e titulo, nao nome
    5876:  ['I-INSTITUICAO', 'O', 'O'],                  # LINHARES . GENITORA -- institucion termina, frase nova
    21140: ['I-ENDERECO', 'O', 'O'],                     # Neiva , contato -- endereco termina, campo novo
    21318: ['I-DATA', 'O', 'O'],                         # 06 . SOLICITO -- data parcial termina, frase nova
    6340:  ['I-ENDERECO', 'I-ENDERECO'],                 # 0000037 NOVA -- endereco continua
    6540:  ['O', 'O', 'B-PESSOA'],                       # SRA . CLAUDETE -- SRA e titulo, nao nome
    6658:  ['O', 'O', 'B-PESSOA'],                       # SRA . RUDMARA -- SRA e titulo, nao nome
    22078: ['O', 'O', 'B-PESSOA'],                       # CIRURGIA.ATT , FABIANA -- ATT nao e nome
    7213:  ['I-ENDERECO', 'I-ENDERECO', 'I-ENDERECO'],   # QUATORZE 5 COHAB -- endereco continua
    7616:  ['B-PESSOA', 'I-PESSOA', 'I-PESSOA'],         # AGNALDO , ELCIO -- lista de irmaos, mesma convencao ja usada em "E ELZA" na mesma frase
    23169: ['I-ENDERECO', 'O', 'O'],                     # Velha . Reside -- endereco termina, frase nova
    23275: ['I-ENDERECO', 'O', 'O'],                     # Janeiro . Realizo -- endereco termina, frase nova
    8527:  ['B-PESSOA', 'O', 'B-PESSOA'],                # MIRIAN , MIRENEZ -- duas filhas, entidades separadas
    23818: ['B-PESSOA', 'O', 'O'],                       # Edimar . Questiono -- nome termina, frase nova
    23871: ['I-ENDERECO', 'O', 'O'],                     # Vitória . Familiares -- endereco termina, frase nova
    9014:  ['B-HORA', 'I-HORA'],                         # 15 HORAS -- hora por extenso, excecao manual (regex nao cobre "NN HORAS")
    9107:  ['B-ENDERECO', 'I-ENDERECO'],                 # 99999675 VITORIA -- endereco continua
    24111: ['I-ENDERECO', 'O', 'O'],                     # Cariacica . Informa -- endereco termina, frase nova
    24150: ['I-ENDERECO', 'O', 'O'],                     # ES . Nome -- endereco termina, campo novo
    9290:  ['I-ENDERECO', 'I-ENDERECO', 'I-ENDERECO'],   # CADORINI 28 BONSUCESSO -- endereco continua
    24377: ['I-DATA', 'O', 'O'],                         # 02 . SEGUNDO -- data parcial termina, frase nova (mesmo caso ja resolvido ao vivo em 24/07)
    24379: ['I-PESSOA', 'O', 'O'],                       # Maria . Relata -- nome termina, frase nova
    24529: ['I-INSTITUICAO', 'O', 'O'],                  # evangélico . Sr -- instituicao termina, frase nova
}


# Override de sentenca inteira: id=5449 tem DOIS casos "ENF.Nome" (GERISMAR e
# CHAYENE), e o difflib.SequenceMatcher alinha errado por causa da repeticao do
# padrao "ENF" + "." -- ao inves de um "replace 1->3" limpo pra cada ocorrencia,
# ele gera um replace+equal+insert fragmentado que nao bate com nenhuma regra
# automatica (e o pedaco 'insert' resolveria SILENCIOSAMENTE como O por vacuidade
# logica se nao fosse pego aqui -- felizmente o pedaco 'replace' falhou primeiro e
# flagou a sentenca inteira, entao nada foi escrito errado). Mapeamento completo
# calculado na mao pra essa sentenca: todas as 33 posicoes novas sao O, exceto
# RODRIGO(1), GERISMAR(14) e CHAYENE(31), que sao B-PESSOA.
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

        # Regra especial: precedente ja estabelecido manualmente nesta mesma sessao
        # para este exato caso "Palavra.PalavraSeguinte" (script corrigir_padrao10_
        # anotado.py, 21/07/2026), agora com o ponto separado em token proprio
        if precedente is not None and n_old == 1 and n_new == len(precedente):
            for k, label in enumerate(precedente):
                plano[j1 + k] = label
            continue

        # Regra especial: julgamento de fronteira de entidade decidido manualmente
        # para este caso especifico na auditoria de 24/07/2026
        if fronteira is not None and n_old == 1 and n_new == len(fronteira):
            for k, label in enumerate(fronteira):
                plano[j1 + k] = label
            continue

        # Regra 1: span todo O
        if all(l == 'O' for l in labels_envolvidos):
            for jp in range(j1, j2):
                plano[jp] = 'O'
            continue

        # Regra 2: familia regex-only (DATA/HORA/CONTATO, com 'O' misturado tambem
        # aceito) + placeholder no resultado -> regex agora resolve, reseta pra O
        if all(l == 'O' or l in FAMILIA_REGEX_ONLY for l in labels_envolvidos) and \
           any(ph in tok for tok in novos_span for ph in PLACEHOLDERS):
            for jp in range(j1, j2):
                plano[jp] = 'O'
            continue

        # Regra 2b: o(s) token(s) antigo(s) SAO, pelo proprio texto, um padrao
        # inequivoco de data/hora/CPF (independente do rotulo que tinham antes --
        # rotulo errado e erro de anotacao, nao uma decisao valida) E o resultado
        # contem um placeholder -> reseta pra O
        if all(eh_data_hora_cpf(tok) for tok in tokens_envolvidos) and \
           any(ph in tok for tok in novos_span for ph in PLACEHOLDERS):
            for jp in range(j1, j2):
                plano[jp] = 'O'
            continue

        return f'{tag} {n_old}->{n_new} em pos {i1}-{i2}', False

    return plano, True


total_processadas = 0
total_ok = 0
total_flagadas = 0
total_erros = 0
ids_flagados = []

sentencas = list(Sentenca.objects.all())
print(f'Processando {len(sentencas)} sentencas...')

for s in sentencas:
    tokens_antigos = s.tokens
    tokens_novos = reprocessar(tokens_antigos)

    if tokens_novos == tokens_antigos:
        continue

    total_processadas += 1

    anotacoes = list(AnotacaoToken.objects.filter(sentenca=s))
    por_anotador = defaultdict(dict)
    for a in anotacoes:
        por_anotador[a.anotador_id][a.posicao] = a.label

    planos_por_anotador = {}
    sentenca_ok = True

    if s.id in OVERRIDE_SENTENCA_COMPLETA:
        plano_override = OVERRIDE_SENTENCA_COMPLETA[s.id]
        if set(plano_override.keys()) == set(range(len(tokens_novos))):
            for anotador_id in por_anotador:
                planos_por_anotador[anotador_id] = plano_override
        else:
            sentenca_ok = False  # tamanho mudou desde que o override foi calculado -- nao arrisca

    else:
        for anotador_id, labels_por_posicao in por_anotador.items():
            plano, ok = planejar_remapeamento(s.id, tokens_antigos, tokens_novos, labels_por_posicao)
            if not ok:
                sentenca_ok = False
                break
            # checagem de seguranca: o plano tem que cobrir EXATAMENTE todas as posicoes
            # dos tokens novos, sem buraco nem duplicata
            if set(plano.keys()) != set(range(len(tokens_novos))):
                sentenca_ok = False
                plano = 'cobertura incompleta do plano'
                break
            planos_por_anotador[anotador_id] = plano

    if not sentenca_ok:
        total_flagadas += 1
        ids_flagados.append(s.id)
        continue

    try:
        with transaction.atomic():
            AnotacaoToken.objects.filter(sentenca=s).delete()
            s.tokens = tokens_novos
            s.save()
            novas_anotacoes = []
            for anotador_id, plano in planos_por_anotador.items():
                for pos, label in plano.items():
                    novas_anotacoes.append(AnotacaoToken(
                        sentenca=s, anotador_id=anotador_id, posicao=pos, label=label,
                    ))
            AnotacaoToken.objects.bulk_create(novas_anotacoes)
        total_ok += 1
    except Exception as e:
        total_erros += 1
        print(f'ERRO id={s.id}: {e}')

print()
print(f'Total de sentencas com token alterado: {total_processadas}')
print(f'Remapeadas com sucesso: {total_ok}')
print(f'Flagadas (nao tocadas, precisam revisao manual): {total_flagadas}')
print(f'Erros: {total_erros}')
print()
print('IDs flagados para revisao manual (ver relatorio_revisao_manual_task25.md):')
print(sorted(ids_flagados))
