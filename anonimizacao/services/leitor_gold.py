#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Leitura do corpus anotado (gold standard) para alimentar o gerador de surrogates.

Junta, numa estrutura só, as três coisas que o gerador precisa e que hoje vivem em
lugares diferentes:

  tokens e labels   vêm do banco de anotação, das tabelas do app `anotador`
  hash_paciente     vem do campo acrescentado na Fase 2, na própria Sentenca
  phi               vem do arquivo *_phi.jsonl que a Fase 1 passou a gerar

Qual label é a verdadeira
=========================
A regra segue a mesma do `exportador.exportar_conll_final`: a adjudicação tem prioridade,
e onde ela não existe vale a anotação do anotador escolhido. Isso funciona nos dois
momentos do projeto sem precisar mudar código: hoje, com um anotador só, a tabela de
adjudicação está vazia e tudo vem da anotação individual; quando o segundo anotador
entrar e as divergências forem adjudicadas, a adjudicação passa a prevalecer sozinha.

O relatório devolvido diz quantas labels vieram de cada origem, para que a transição
entre os dois momentos seja visível em vez de silenciosa.

Sobre desempenho
================
As consultas são feitas em bloco, não sentença a sentença. O exportador existente
consulta duas tabelas dentro do laço, o que dá duas idas ao banco por sentença: com as
5.000 sentenças do Exp 002 são 10.000 consultas. Aqui são três, independentemente do
tamanho do corpus, ao custo de manter as labels em memória durante a leitura.
"""

import json
import os
from collections import defaultdict

from anotador.models import Sentenca, AnotacaoToken, AdjudicacaoToken


def _anotador_padrao(sessao_id):
    """
    Escolhe o anotador quando nenhum foi indicado.

    Com um anotador só, que é a situação atual do projeto, a escolha é óbvia. Com mais
    de um, exigir a indicação explícita evita que o corpus seja gerado a partir de quem
    calhou de aparecer primeiro na consulta.
    """
    # O .order_by() vazio antes do .distinct() e obrigatorio aqui. O Meta de
    # AnotacaoToken define ordering = ['sentenca', 'posicao'], e o Django inclui as
    # colunas de ordenacao no SELECT sempre que ha ordering no Meta. O DISTINCT passa
    # a considerar tambem essas colunas e nao elimina duplicata nenhuma: em vez de um
    # anotador, a consulta devolve uma linha por token anotado. Com as 191.118
    # anotacoes da sessao 5 do Exp 002, o resultado eram 191.118 "anotadores".
    anotadores = sorted(
        AnotacaoToken.objects
        .filter(sentenca__sessao_id=sessao_id)
        .values_list('anotador_id', flat=True)
        .order_by()
        .distinct()
    )
    if not anotadores:
        raise ValueError(
            f'A sessão {sessao_id} não tem nenhuma anotação registrada. '
            f'Não há gold standard para ler.'
        )
    if len(anotadores) > 1:
        raise ValueError(
            f'A sessão {sessao_id} tem {len(anotadores)} anotadores '
            f'(ids {anotadores}). Informe qual usar como base, com --anotador. '
            f'Onde houver adjudicação ela prevalece de qualquer forma.'
        )
    return anotadores[0]


def carregar_mapa_phi(caminho):
    """
    Lê o arquivo *_phi.jsonl e indexa por (doc_id, sentenca_idx).

    Esse arquivo contém os valores reais de data, telefone, CPF, CEP e e-mail, então é
    material sensível: fica no perímetro, nunca é versionado e nunca acompanha o corpus
    gerado.
    """
    if not caminho:
        return {}
    if not os.path.exists(caminho):
        raise FileNotFoundError(
            f'Mapa de PHI não encontrado em {caminho}. Ele é gerado pelo '
            f'pré-processamento quando executado com capturar_phi=True.'
        )

    mapa = {}
    with open(caminho, encoding='utf-8') as arquivo:
        for linha in arquivo:
            linha = linha.strip()
            if not linha:
                continue
            registro = json.loads(linha)
            chave = (registro['doc_id'], registro['sentenca_idx'])
            mapa[chave] = registro.get('phi') or []
    return mapa


def carregar_gold(sessao_id, anotador_id=None, caminho_phi=None):
    """
    Devolve (sentencas, relatorio) prontos para o gerador de surrogates.

    Cada sentença é um dicionário com tokens, labels, hash_paciente, phi, doc_id,
    doc_type e sentenca_idx.

    Só entram sentenças que foram efetivamente anotadas. Uma sentença pendente tem todas
    as labels em O, e incluí-la faria o corpus gerado parecer maior do que o trabalho de
    anotação realmente cobriu.
    """
    if anotador_id is None:
        anotador_id = _anotador_padrao(sessao_id)

    # Consulta 1: as sentenças da sessão
    sentencas = list(
        Sentenca.objects
        .filter(sessao_id=sessao_id)
        .order_by('ordem')
        .values('id', 'doc_id', 'doc_type', 'ordem', 'tokens',
                'hash_paciente', 'sentenca_idx')
    )

    # Consulta 2: todas as anotações do anotador escolhido, de uma vez
    anotacoes = defaultdict(dict)
    for sentenca_id, posicao, label in (
        AnotacaoToken.objects
        .filter(sentenca__sessao_id=sessao_id, anotador_id=anotador_id)
        .values_list('sentenca_id', 'posicao', 'label')
    ):
        anotacoes[sentenca_id][posicao] = label

    # Consulta 3: todas as adjudicações da sessão, de uma vez
    adjudicacoes = defaultdict(dict)
    for sentenca_id, posicao, label in (
        AdjudicacaoToken.objects
        .filter(sentenca__sessao_id=sessao_id)
        .values_list('sentenca_id', 'posicao', 'label')
    ):
        adjudicacoes[sentenca_id][posicao] = label

    mapa_phi = carregar_mapa_phi(caminho_phi)

    resultado = []
    contagem = {
        'sentencas_na_sessao':      len(sentencas),
        'sentencas_sem_anotacao':   0,
        'sentencas_sem_paciente':   0,
        'sentencas_sem_phi':        0,
        'labels_de_adjudicacao':    0,
        'labels_de_anotacao':       0,
        'labels_ausentes':          0,
    }

    for sentenca in sentencas:
        sentenca_id = sentenca['id']
        labels_anotadas = anotacoes.get(sentenca_id)
        labels_adjudicadas = adjudicacoes.get(sentenca_id, {})

        if not labels_anotadas and not labels_adjudicadas:
            contagem['sentencas_sem_anotacao'] += 1
            continue

        tokens = sentenca['tokens'] or []
        labels = []
        for posicao in range(len(tokens)):
            if posicao in labels_adjudicadas:
                labels.append(labels_adjudicadas[posicao])
                contagem['labels_de_adjudicacao'] += 1
            elif labels_anotadas and posicao in labels_anotadas:
                labels.append(labels_anotadas[posicao])
                contagem['labels_de_anotacao'] += 1
            else:
                # Token sem registro. Trata como fora de entidade, que é o default do
                # próprio modelo, mas conta para que a lacuna apareça no relatório.
                labels.append('O')
                contagem['labels_ausentes'] += 1

        if not sentenca['hash_paciente']:
            contagem['sentencas_sem_paciente'] += 1

        chave_phi = (sentenca['doc_id'], sentenca['sentenca_idx'])
        phi = mapa_phi.get(chave_phi)
        if phi is None and mapa_phi:
            contagem['sentencas_sem_phi'] += 1
            phi = []

        resultado.append({
            # A PK entra para que auditorias consigam apontar a sentenca na interface
            # de anotacao, onde a revisao acontece. Ela nao vai para o corpus gerado.
            'sentenca_pk':   sentenca_id,
            'doc_id':        sentenca['doc_id'],
            'doc_type':      sentenca['doc_type'],
            'ordem':         sentenca['ordem'],
            'sentenca_idx':  sentenca['sentenca_idx'],
            'hash_paciente': sentenca['hash_paciente'],
            'tokens':        tokens,
            'labels':        labels,
            'phi':           phi or [],
        })

    contagem['sentencas_lidas'] = len(resultado)
    contagem['anotador_id'] = anotador_id
    contagem['mapa_phi_carregado'] = bool(mapa_phi)
    return resultado, contagem


def descrever_relatorio(contagem):
    """Formata o relatório da leitura para exibição no terminal."""
    linhas = [
        f"  anotador usado como base : {contagem['anotador_id']}",
        f"  sentencas na sessao      : {contagem['sentencas_na_sessao']}",
        f"  sentencas lidas          : {contagem['sentencas_lidas']}",
    ]
    if contagem['sentencas_sem_anotacao']:
        linhas.append(
            f"  sentencas sem anotacao   : {contagem['sentencas_sem_anotacao']} "
            f"(ficaram de fora, ainda nao foram anotadas)"
        )
    linhas.extend([
        f"  labels de adjudicacao    : {contagem['labels_de_adjudicacao']}",
        f"  labels de anotacao       : {contagem['labels_de_anotacao']}",
    ])
    if contagem['labels_ausentes']:
        linhas.append(
            f"  labels ausentes          : {contagem['labels_ausentes']} "
            f"(tokens sem registro, assumidos como O)"
        )
    if contagem['sentencas_sem_paciente']:
        linhas.append(
            f"  sentencas sem paciente   : {contagem['sentencas_sem_paciente']} "
            f"(corpus anterior a Fase 2; a consistencia cai para o nivel do documento)"
        )
    if contagem['mapa_phi_carregado'] and contagem['sentencas_sem_phi']:
        linhas.append(
            f"  sentencas fora do mapa   : {contagem['sentencas_sem_phi']} "
            f"(corpus e mapa de PHI podem ser de execucoes diferentes)"
        )
    if not contagem['mapa_phi_carregado']:
        linhas.append(
            "  mapa de PHI              : nao informado, as datas e demais valores de "
            "regex permanecerao como placeholder"
        )
    return '\n'.join(linhas)
