#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aplicação dos surrogates sobre o corpus anotado.

Este módulo é a ponte entre duas coisas que a pipeline produz separadamente e que
precisam ser reunidas para gerar o corpus publicável:

  1. Os spans anotados à mão (PESSOA, ENDERECO, INSTITUICAO, DOCUMENTO). Eles vêm do
     gold standard, na forma de labels BIO alinhadas com os tokens.

  2. O mapa de PHI estrutural (DATA, HORA, TELEFONE, CPF, CEP, EMAIL). Esses nunca
     chegaram ao anotador: viraram placeholder ainda na normalização, e o valor original
     ficou guardado no arquivo *_phi.jsonl que a Fase 1 passou a gerar.

Metade do PHI vem de cada lado, que é consequência direta da arquitetura híbrida do
AnonClin. Se o gerador olhasse só para as anotações, todas as datas do corpus
continuariam sendo a palavra "__DATA__", e um texto clínico onde nenhuma data é uma data
não convence ninguém.

O cuidado principal aqui é o alinhamento. Substituir uma entidade por outra costuma mudar
a quantidade de tokens: "RUA DAS FLORES" tem três, e "RUA SANTA LUZIA, 1052" tem cinco.
Se as labels não forem refeitas junto, o corpus resultante fica com anotação apontando
para o token errado, e todo o experimento passa a medir ruído.
"""

import re

from anonimizacao.services.anonimizacao import extrair_spans_phi
from preprocessamento.services.preprocessamento import tokenizar_word_level


# Placeholders que o pipeline usa para o PHI tratado por regex. Um token nesse formato
# no corpus significa que ali havia um valor real, guardado no mapa de PHI.
RE_PLACEHOLDER = re.compile(r'^__[A-Z]+__$')


def _tokenizar_surrogate(texto):
    """
    Quebra o surrogate nos mesmos critérios usados no corpus.

    Usa a tokenização do próprio pipeline em vez de um split simples, senão o corpus
    gerado teria uma segmentação diferente da do corpus original e os dois deixariam de
    ser comparáveis. Se por algum motivo a tokenização devolver vazio, cai no texto
    inteiro como um token só, para nunca perder a entidade.
    """
    tokens = tokenizar_word_level(texto)
    return tokens if tokens else [texto]


def _rotular(tipo, quantidade):
    """Monta as labels BIO para uma entidade que ocupa `quantidade` tokens."""
    if quantidade <= 0:
        return []
    return [f'B-{tipo}'] + [f'I-{tipo}'] * (quantidade - 1)


def _coletar_substituicoes(tokens, labels, phi, avisos):
    """
    Reúne, numa lista só, tudo que precisa ser substituído nesta sentença.

    Cada item vira uma faixa [inicio, fim) de tokens, com o tipo da entidade e o valor
    original. As duas origens são tratadas juntas de propósito: aplicar primeiro uma e
    depois a outra faria a segunda trabalhar sobre índices que a primeira já deslocou.

    Quando um span anotado e um placeholder ocupam a mesma posição, a anotação humana
    prevalece. Isso acontece, por exemplo, quando o anotador marcou um "__DATA__" como
    B-DATA: as duas fontes descrevem o mesmo pedaço de texto, e usar as duas produziria
    substituição dupla.
    """
    substituicoes = []
    ocupadas = set()

    # Primeiro os spans anotados, que têm prioridade sobre o mapa
    for span in extrair_spans_phi(tokens, labels):
        inicio, fim = span['inicio'], span['fim']
        substituicoes.append({
            'inicio':   inicio,
            'fim':      fim,
            'tipo':     span['tipo'],
            'original': span.get('texto') or ' '.join(tokens[inicio:fim]),
            'origem':   'anotacao',
        })
        ocupadas.update(range(inicio, fim))

    # Depois o mapa de PHI, pulando o que a anotação já cobriu
    for item in (phi or []):
        posicao = item.get('posicao')
        if posicao is None or not (0 <= posicao < len(tokens)):
            avisos['posicao_invalida'] += 1
            continue
        if posicao in ocupadas:
            avisos['sobreposicao'] += 1
            continue
        if not RE_PLACEHOLDER.match(tokens[posicao]):
            # O mapa aponta para um token que não é placeholder. Sinal de que corpus e
            # mapa saíram de execuções diferentes e não estão mais alinhados.
            avisos['token_inesperado'] += 1
            continue
        substituicoes.append({
            'inicio':   posicao,
            'fim':      posicao + 1,
            'tipo':     item['tipo'],
            'original': item['valor'],
            'origem':   'mapa_phi',
        })
        ocupadas.add(posicao)

    # Da direita para a esquerda: assim cada substituição não desloca os índices das que
    # ainda faltam ser aplicadas.
    substituicoes.sort(key=lambda s: s['inicio'], reverse=True)
    return substituicoes


def aplicar_em_sentenca(tokens, labels, phi, gerador, chave, avisos):
    """
    Devolve (tokens_novos, labels_novas) com as entidades trocadas por surrogates.

    `chave` é a identidade usada para manter a consistência, normalmente o hash do
    paciente. É ela que garante que o mesmo João da Silva vire sempre o mesmo nome
    fictício, e que um homônimo receba outro.

    As labels são reconstruídas a partir do tamanho real do surrogate. É isso que mantém
    o corpus gerado utilizável para treinar NER: a anotação continua apontando para os
    tokens certos mesmo quando a entidade muda de comprimento.
    """
    tokens_novos = list(tokens)
    labels_novas = list(labels)

    for sub in _coletar_substituicoes(tokens, labels, phi, avisos):
        surrogate = gerador.gerar(sub['tipo'], sub['original'], chave)

        # Um tipo que o gerador não sabe tratar devolve o valor original. Deixar passar
        # em silêncio seria manter PHI real no corpus, então conta-se para conferência.
        if surrogate == sub['original'] and sub['origem'] == 'mapa_phi':
            avisos['sem_surrogate'] += 1

        novos = _tokenizar_surrogate(surrogate)
        tokens_novos[sub['inicio']:sub['fim']] = novos

        if sub['origem'] == 'anotacao':
            # Mantém a entidade anotada, agora com o comprimento do surrogate
            labels_novas[sub['inicio']:sub['fim']] = _rotular(sub['tipo'], len(novos))
        else:
            # PHI estrutural não é entidade do NER neste corpus: era placeholder e
            # continua fora da anotação, com label O em todos os tokens que ocupar.
            labels_novas[sub['inicio']:sub['fim']] = ['O'] * len(novos)

    return tokens_novos, labels_novas


def gerar_corpus(sentencas, gerador):
    """
    Aplica o gerador a um corpus inteiro.

    `sentencas` é uma lista de dicionários com as chaves:
        tokens        lista de tokens da sentença
        labels        labels BIO alinhadas com os tokens
        hash_paciente identidade para a consistência (opcional, ver abaixo)
        phi           itens do mapa de PHI desta sentença (opcional)
        doc_id        identificador do documento de origem (opcional)

    Sentenças sem `hash_paciente` caem no `doc_id` como identidade, e sem ele também,
    na posição da sentença. Nesse caso a consistência vale só dentro do documento, o que
    é uma degradação silenciosa: o relatório devolvido conta quantas sentenças ficaram
    nessa situação para que o problema apareça em vez de passar batido.

    Devolve (corpus_novo, relatorio).
    """
    avisos = {
        'sobreposicao':      0,   # span anotado e placeholder na mesma posição
        'posicao_invalida':  0,   # mapa aponta para fora da sentença
        'token_inesperado':  0,   # mapa aponta para token que não é placeholder
        'sem_surrogate':     0,   # gerador não soube tratar o tipo
        'sem_identidade':    0,   # sentença sem hash_paciente
    }

    corpus_novo = []
    for posicao, sentenca in enumerate(sentencas):
        chave = sentenca.get('hash_paciente')
        if not chave:
            avisos['sem_identidade'] += 1
            chave = f"doc:{sentenca.get('doc_id', posicao)}"

        tokens_novos, labels_novas = aplicar_em_sentenca(
            sentenca['tokens'],
            sentenca.get('labels') or ['O'] * len(sentenca['tokens']),
            sentenca.get('phi'),
            gerador,
            chave,
            avisos,
        )

        registro = dict(sentenca)
        registro['tokens'] = tokens_novos
        registro['labels'] = labels_novas
        registro.pop('phi', None)          # o mapa não acompanha o corpus gerado
        corpus_novo.append(registro)

    relatorio = {
        'sentencas':            len(corpus_novo),
        'avisos':               avisos,
        'gerador':              gerador.estatisticas(),
        'placeholders_restantes': sum(
            1 for s in corpus_novo for t in s['tokens'] if RE_PLACEHOLDER.match(t)
        ),
    }
    return corpus_novo, relatorio


def conferir_alinhamento(corpus):
    """
    Verifica se cada sentença tem uma label por token e se as sequências BIO são válidas.

    Roda depois da geração, como rede de segurança. Um I- sem B- antes indica que a
    reconstrução das labels errou em algum ponto, e é melhor descobrir isso aqui do que
    no meio do treinamento.
    """
    problemas = []
    for indice, sentenca in enumerate(corpus):
        tokens, labels = sentenca['tokens'], sentenca['labels']
        if len(tokens) != len(labels):
            problemas.append(
                f'sentenca {indice}: {len(tokens)} tokens para {len(labels)} labels'
            )
            continue
        anterior = 'O'
        for posicao, label in enumerate(labels):
            if label.startswith('I-'):
                tipo = label[2:]
                if anterior not in (f'B-{tipo}', f'I-{tipo}'):
                    problemas.append(
                        f'sentenca {indice}, posicao {posicao}: {label} sem B- antes'
                    )
            anterior = label
    return problemas
