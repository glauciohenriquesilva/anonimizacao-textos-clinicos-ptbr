#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validação das sequências BIO no momento em que a anotação é gravada.

Por que isto existe
===================
A tela de anotação deixa marcar qualquer label em qualquer token. É cômodo para anotar
rápido, e ninguém quer um formulário que fique reclamando a cada clique. Mas isso permite
gravar um `I-ENDERECO` cujo token anterior não é `B-ENDERECO` nem `I-ENDERECO`, e uma
entidade que começa no meio não existe no esquema BIO.

O problema não aparece na hora. Ele aparece muito depois, em dois lugares silenciosos:
no treinamento, onde o modelo recebe exemplos de uma estrutura impossível e aprende a
reproduzi-la; e na avaliação, onde o `seqeval` precisa decidir o que fazer com um `I-`
órfão e acaba medindo uma entidade que o anotador não marcou como tal.

A auditoria de 02/09/2026 encontrou 22 dessas ocorrências no corpus do Exp 002, em 10
sentenças. Poucas em número, mas concentradas em ENDEREÇO, onde representam 7,5% das
entidades daquele tipo, e ENDEREÇO é justamente a categoria de pior F1.

O padrão observado foi sempre o mesmo: várias marcações espaçadas na mesma sentença,
sempre `I-` depois de `O`. É o que acontece quando a label `I-` fica selecionada no painel
e vai sendo aplicada a tokens isolados, um a um.

Como este módulo trata o caso
=============================
Ele corrige e conta. Um `I-TIPO` sem começo válido vira `B-TIPO`, que é a leitura correta
em praticamente todos os casos observados: o anotador queria marcar uma entidade que
começa ali. E devolve a lista do que mudou, para que a interface possa mostrar ao
anotador em vez de alterar o trabalho dele em silêncio.

Corrigir sem avisar teria o mesmo defeito que a ausência de validação: uma decisão
tomada por baixo, que ninguém revisa.
"""


def validar_sequencia_bio(labels):
    """
    Corrige `I-` órfãos e devolve (labels_corrigidas, correcoes).

    Uma label `I-TIPO` é válida quando a anterior é `B-TIPO` ou `I-TIPO`. Quando não é,
    ela vira `B-TIPO`, porque o caso comum é o anotador ter marcado o início da entidade
    com a label errada.

    Cada item de `correcoes` traz a posição, o que estava lá e o que ficou:

        {'posicao': 14, 'de': 'I-ENDERECO', 'para': 'B-ENDERECO',
         'anterior': 'O'}

    A lista vazia significa que a anotação já estava correta, que é o caso da grande
    maioria das sentenças.
    """
    corrigidas = list(labels)
    correcoes = []
    anterior = 'O'

    for posicao, label in enumerate(corrigidas):
        if label.startswith('I-'):
            tipo = label[2:]
            if anterior not in (f'B-{tipo}', f'I-{tipo}'):
                corrigidas[posicao] = f'B-{tipo}'
                correcoes.append({
                    'posicao':  posicao,
                    'de':       label,
                    'para':     f'B-{tipo}',
                    'anterior': anterior,
                })
        anterior = corrigidas[posicao]

    return corrigidas, correcoes


def descrever_correcoes(correcoes, tokens=None):
    """
    Monta a mensagem que a interface mostra ao anotador.

    Recebe os tokens quando disponíveis para citar a palavra corrigida, que é mais fácil
    de localizar na tela do que um número de posição.
    """
    if not correcoes:
        return ''

    partes = []
    for item in correcoes:
        posicao = item['posicao']
        if tokens and 0 <= posicao < len(tokens):
            referencia = f'"{tokens[posicao]}" (posição {posicao})'
        else:
            referencia = f'posição {posicao}'
        partes.append(f"{referencia}: {item['de']} ajustado para {item['para']}")

    if len(partes) == 1:
        return f'Uma marcação foi ajustada. {partes[0]}.'
    return (f'{len(partes)} marcações foram ajustadas, porque uma entidade não pode '
            f'começar com I-. ' + '; '.join(partes) + '.')
