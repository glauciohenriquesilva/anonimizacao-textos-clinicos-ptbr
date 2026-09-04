#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Confere se o corpus reprocessado reproduz o corpus original e liga o gold ao mapa de PHI.

    python scripts/conferir_reprocessamento.py \
        --antigo outputs/preprocessamento/Experimento_002_corpus.jsonl \
        --novo   outputs/reprocessamento/Experimento_002_reproc_corpus.jsonl \
        --sessao 5

A pergunta que este script responde
===================================
O corpus do Exp 002 foi gerado antes das Fases 1 e 2, então não tem mapa de PHI nem
vínculo com o paciente. A pergunta é se dá para recuperar essas duas coisas sem reanotar
nada, e ela se decompõe em duas:

  1. O reprocessamento produz o mesmo corpus? Se sim, o código não mudou de forma que
     afete a tokenização, e os CSVs em mãos são os originais.

  2. As sentenças já anotadas podem ser localizadas no corpus reprocessado? Se sim, cada
     uma ganha seu `sentenca_idx` e seu `hash_paciente`, e o mapa de PHI passa a encaixar.

Por que a resposta 1 provavelmente será "não"
=============================================
O histórico do banco mostra que o mesmo conjunto de documentos já produziu corpora
diferentes: as execuções 4 e 5, de 13/07/2026, deram 25.215 sentenças; a execução 10, de
15/07, que é a do Exp 002, deu 26.824 sobre os mesmos 6.059 documentos. A segmentação
mudou em dois dias. De 15/07 para cá houve mais correções de regex, então esperar
igualdade exata seria otimismo.

Por isso a comparação global aqui é diagnóstico, não veto. O que decide se uma sentença
pode ser ligada ao seu PHI é outra coisa, mais local e mais verificável: os tokens.

O critério real de segurança
============================
Uma sentença anotada só é casada quando três condições valem ao mesmo tempo:

  a) existe no corpus novo, dentro do mesmo `doc_id`, exatamente uma sentença com a lista
     de tokens idêntica;
  b) o documento onde ela foi encontrada é reconhecidamente o mesmo documento, medido
     pela proporção de tokens que os dois corpora compartilham naquele `doc_id`, sem
     olhar como o texto foi dividido em sentenças;
  c) o `doc_type` bate.

A condição (b) existe porque `doc_id` é o índice posicional do DataFrame, não um
identificador estável. Se a quantidade ou a ordem dos documentos mudar, o mesmo número
passa a apontar para outro documento, e uma coincidência de tokens ligaria a sentença ao
PHI de outra pessoa. Comparar o conteúdo do documento inteiro é o que impede isso.

O casamento é por conteúdo, e não por posição, porque a `ordem` guardada no banco é a
posição dentro da sessão de anotação, não dentro do documento: a seleção estratificada
não preservou a posição original.

O que ele faz com o que descobre
================================
Por padrão, nada além de relatar. Com `--aplicar`, grava `sentenca_idx` e `hash_paciente`
nas sentenças que passaram nas três condições, numa transação única. Nenhuma label é
tocada, e as sentenças que não passaram ficam exatamente como estão.
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'anonclin.settings')

import django  # noqa: E402
django.setup()

from django.db import transaction  # noqa: E402

from anotador.models import Sentenca  # noqa: E402


def ler_corpus(caminho):
    """
    Lê o corpus.jsonl e devolve {doc_id: documento}.

    Um registro por documento, com `sentencas_tokens` dentro. O arquivo do Exp 002 tem
    12 MB, então cabe em memória sem cerimônia; se um dia não couber, a comparação
    precisará ser feita em fluxo, documento a documento nos dois arquivos ao mesmo tempo.
    """
    if not os.path.exists(caminho):
        sys.exit(f'Corpus nao encontrado: {caminho}')

    documentos = {}
    with open(caminho, encoding='utf-8') as arquivo:
        for numero, linha in enumerate(arquivo, 1):
            linha = linha.strip()
            if not linha:
                continue
            try:
                registro = json.loads(linha)
            except json.JSONDecodeError as erro:
                sys.exit(f'{caminho}, linha {numero}: JSON invalido ({erro})')
            documentos[registro['doc_id']] = registro
    return documentos


def sacola_de_tokens(documento):
    """
    Devolve a contagem de tokens do documento inteiro, ignorando a divisão em sentenças.

    É esta a medida usada para decidir se dois `doc_id` iguais são o mesmo documento, e a
    escolha é deliberada. O que mudou entre as execuções de julho foi justamente a
    segmentação: os mesmos 6.059 documentos passaram de 25.215 para 26.824 sentenças.
    Comparar sentenças puniria essa mudança como se fosse troca de documento, quando o
    texto é o mesmo.

    Já um documento trocado tem outro texto, e o vocabulário denuncia isso na hora.
    """
    contagem = Counter()
    for tokens in (documento.get('sentencas_tokens') or []):
        contagem.update(tokens)
    return contagem


def jaccard_ponderado(contagem_a, contagem_b):
    """
    Similaridade entre duas contagens de tokens: soma dos mínimos sobre soma dos máximos.

    Vale 1,0 quando os documentos têm exatamente os mesmos tokens nas mesmas quantidades,
    independentemente de como foram divididos em sentenças, e cai proporcionalmente ao que
    difere. Documentos vazios nos dois lados contam como iguais, porque não há evidência
    de troca.
    """
    if not contagem_a and not contagem_b:
        return 1.0
    chaves = set(contagem_a) | set(contagem_b)
    intersecao = sum(min(contagem_a.get(k, 0), contagem_b.get(k, 0)) for k in chaves)
    uniao = sum(max(contagem_a.get(k, 0), contagem_b.get(k, 0)) for k in chaves)
    return intersecao / uniao if uniao else 1.0


def comparar_corpora(antigo, novo):
    """
    Compara os dois corpora documento a documento.

    Devolve (relatorio, similaridade), onde `similaridade` é {doc_id: proporção} com a
    fração de tokens que os dois corpora compartilham naquele documento. É esse número, e
    não a igualdade total, que decide depois se um documento pode ser usado para casar
    sentenças anotadas.

    A comparação é de tokens, não de texto: é a lista de tokens que foi para a anotação, e
    é ela que precisa bater. Diferença de espaçamento no original não importa; diferença
    de tokenização importa muito, porque desloca as posições das labels.
    """
    relatorio = {
        'docs_antigo':        len(antigo),
        'docs_novo':          len(novo),
        'docs_so_no_antigo':  sorted(set(antigo) - set(novo))[:20],
        'docs_so_no_novo':    sorted(set(novo) - set(antigo))[:20],
        'total_so_no_antigo': len(set(antigo) - set(novo)),
        'total_so_no_novo':   len(set(novo) - set(antigo)),
        'docs_identicos':     0,
        'docs_com_diferenca': 0,
        'sentencas_antigo':   0,
        'sentencas_novo':     0,
        'sentencas_iguais':   0,
        'sentencas_difer':    0,
        'motivos':            Counter(),
        'exemplos':           [],
    }
    similaridade = {}

    comuns = sorted(set(antigo) & set(novo))
    for doc_id in comuns:
        sentencas_antigas = antigo[doc_id].get('sentencas_tokens') or []
        sentencas_novas = novo[doc_id].get('sentencas_tokens') or []
        relatorio['sentencas_antigo'] += len(sentencas_antigas)
        relatorio['sentencas_novo'] += len(sentencas_novas)

        similaridade[doc_id] = jaccard_ponderado(
            sacola_de_tokens(antigo[doc_id]), sacola_de_tokens(novo[doc_id])
        )

        diferente = False

        if antigo[doc_id].get('doc_type') != novo[doc_id].get('doc_type'):
            relatorio['motivos']['doc_type diferente'] += 1
            diferente = True

        if len(sentencas_antigas) != len(sentencas_novas):
            relatorio['motivos']['quantidade de sentencas'] += 1
            diferente = True
            if len(relatorio['exemplos']) < 10:
                relatorio['exemplos'].append(
                    f'doc {doc_id}: {len(sentencas_antigas)} sentencas no antigo, '
                    f'{len(sentencas_novas)} no novo'
                )

        for indice, (tokens_a, tokens_b) in enumerate(
            zip(sentencas_antigas, sentencas_novas)
        ):
            if tokens_a == tokens_b:
                relatorio['sentencas_iguais'] += 1
                continue

            relatorio['sentencas_difer'] += 1
            diferente = True
            if len(tokens_a) != len(tokens_b):
                relatorio['motivos']['quantidade de tokens'] += 1
            else:
                relatorio['motivos']['conteudo dos tokens'] += 1

            if len(relatorio['exemplos']) < 10:
                relatorio['exemplos'].append(
                    f'doc {doc_id}, sentenca {indice}:\n'
                    f'      antigo: {tokens_a[:12]}\n'
                    f'      novo  : {tokens_b[:12]}'
                )

        if diferente:
            relatorio['docs_com_diferenca'] += 1
        else:
            relatorio['docs_identicos'] += 1

    return relatorio, similaridade


def indexar_por_conteudo(documentos):
    """
    Monta {(doc_id, tupla_de_tokens): [indices]} para o casamento por conteúdo.

    A lista de índices é o que permite distinguir o casamento único do ambíguo: duas
    sentenças idênticas dentro do mesmo documento produzem duas entradas na mesma lista.
    """
    indice = defaultdict(list)
    for doc_id, documento in documentos.items():
        for posicao, tokens in enumerate(documento.get('sentencas_tokens') or []):
            indice[(doc_id, tuple(tokens))].append(posicao)
    return indice


def casar_sentencas_anotadas(sessao_id, antigo, novo, similaridade, limiar):
    """
    Localiza cada sentença anotada dentro do corpus reprocessado.

    Devolve (casadas, relatorio), onde `casadas` é a lista de tuplas
    (sentenca_pk, sentenca_idx, hash_paciente) para as que passaram em todas as condições.
    """
    indice = indexar_por_conteudo(novo)

    sentencas = list(
        Sentenca.objects
        .filter(sessao_id=sessao_id)
        .order_by('ordem')
        .values('id', 'doc_id', 'doc_type', 'ordem', 'tokens',
                'sentenca_idx', 'hash_paciente')
    )

    casadas = []
    relatorio = {
        'sentencas_na_sessao': len(sentencas),
        'casamento_unico':     0,
        'casamento_ambiguo':   0,
        'sem_casamento':       0,
        'doc_ausente':         0,
        'doc_pouco_similar':   0,
        'doc_type_diferente':  0,
        'ja_preenchidas':      0,
        'sem_hash_paciente':   0,
        'docs_reprovados':     set(),
        'exemplos_falha':      [],
    }

    def anotar_falha(mensagem):
        if len(relatorio['exemplos_falha']) < 12:
            relatorio['exemplos_falha'].append(mensagem)

    for sentenca in sentencas:
        doc_id = sentenca['doc_id']
        tokens = sentenca['tokens'] or []
        trecho = ' '.join(tokens[:8])

        if doc_id not in novo:
            relatorio['doc_ausente'] += 1
            anotar_falha(f"sentenca {sentenca['ordem']}: doc {doc_id} nao existe no "
                         f'corpus novo')
            continue

        # O documento precisa ser reconhecidamente o mesmo. Sem isso, uma coincidência de
        # tokens ligaria a sentença ao PHI de outra pessoa, porque doc_id é apenas a
        # posição no DataFrame.
        if novo[doc_id].get('doc_type') != sentenca['doc_type']:
            relatorio['doc_type_diferente'] += 1
            relatorio['docs_reprovados'].add(doc_id)
            anotar_falha(f"sentenca {sentenca['ordem']}: doc {doc_id} era "
                         f"{sentenca['doc_type']} e agora e "
                         f"{novo[doc_id].get('doc_type')}")
            continue

        parecido = similaridade.get(doc_id)
        if parecido is None or parecido < limiar:
            relatorio['doc_pouco_similar'] += 1
            relatorio['docs_reprovados'].add(doc_id)
            anotar_falha(f"sentenca {sentenca['ordem']}: doc {doc_id} tem apenas "
                         f'{(parecido or 0) * 100:.0f}% de tokens em comum com o '
                         f'antigo, abaixo do limiar de {limiar * 100:.0f}%')
            continue

        posicoes = indice.get((doc_id, tuple(tokens)), [])

        if len(posicoes) == 1:
            relatorio['casamento_unico'] += 1
            hash_paciente = novo[doc_id].get('hash_paciente')
            if not hash_paciente:
                relatorio['sem_hash_paciente'] += 1
            if sentenca['sentenca_idx'] is not None:
                relatorio['ja_preenchidas'] += 1
            casadas.append((sentenca['id'], posicoes[0], hash_paciente))
        elif len(posicoes) > 1:
            relatorio['casamento_ambiguo'] += 1
            anotar_falha(f"sentenca {sentenca['ordem']} (doc {doc_id}): aparece "
                         f'{len(posicoes)} vezes no documento. "{trecho}"')
        else:
            relatorio['sem_casamento'] += 1
            anotar_falha(f"sentenca {sentenca['ordem']} (doc {doc_id}): nao encontrada "
                         f'no corpus novo. "{trecho}"')

    return casadas, relatorio


def aplicar(casadas):
    """
    Grava sentenca_idx e hash_paciente nas sentenças que passaram nas três condições.

    Numa transação só: gravar metade seria pior que não gravar, porque o corpus ficaria
    parcialmente ligado ao mapa de PHI e a diferença passaria despercebida.

    Nenhuma label é tocada. Só os dois campos acrescentados na Fase 2.
    """
    with transaction.atomic():
        objetos = [
            Sentenca(id=pk, sentenca_idx=idx, hash_paciente=hp)
            for pk, idx, hp in casadas
        ]
        Sentenca.objects.bulk_update(
            objetos, ['sentenca_idx', 'hash_paciente'], batch_size=500
        )
    return len(casadas)


def main():
    parser = argparse.ArgumentParser(
        description='Confere o reprocessamento e liga o gold standard ao mapa de PHI.'
    )
    parser.add_argument('--antigo', required=True,
                        help='corpus.jsonl gerado originalmente.')
    parser.add_argument('--novo', required=True,
                        help='corpus.jsonl gerado pelo reprocessamento.')
    parser.add_argument('--sessao', type=int, default=None,
                        help='Sessão de anotação a casar com o corpus novo. Sem ela, o '
                             'script só compara os dois arquivos.')
    parser.add_argument('--limiar-doc', type=float, default=0.90,
                        help='Proporção mínima de tokens em comum para aceitar que o '
                             'doc_id aponta para o mesmo documento (default 0.90). A '
                             'medida ignora a segmentação, então re-segmentar não '
                             'derruba o valor.')
    parser.add_argument('--aplicar', action='store_true',
                        help='Grava sentenca_idx e hash_paciente nas sentencas casadas. '
                             'Sem esta opcao nada e escrito no banco.')
    args = parser.parse_args()

    print('Lendo os dois corpora...')
    antigo = ler_corpus(args.antigo)
    novo = ler_corpus(args.novo)

    relatorio, similaridade = comparar_corpora(antigo, novo)

    print()
    print('COMPARACAO DOS CORPORA')
    print('----------------------')
    print(f"  documentos no antigo : {relatorio['docs_antigo']}")
    print(f"  documentos no novo   : {relatorio['docs_novo']}")
    print(f"  documentos identicos : {relatorio['docs_identicos']}")
    print(f"  documentos alterados : {relatorio['docs_com_diferenca']}")
    print(f"  sentencas no antigo  : {relatorio['sentencas_antigo']}")
    print(f"  sentencas no novo    : {relatorio['sentencas_novo']}")

    if relatorio['total_so_no_antigo'] or relatorio['total_so_no_novo']:
        print()
        print(f"  so no antigo : {relatorio['total_so_no_antigo']} "
              f"{relatorio['docs_so_no_antigo']}")
        print(f"  so no novo   : {relatorio['total_so_no_novo']} "
              f"{relatorio['docs_so_no_novo']}")

    if similaridade:
        valores = sorted(similaridade.values())
        meio = valores[len(valores) // 2]
        abaixo = sum(1 for v in valores if v < args.limiar_doc)
        print()
        print('  similaridade por documento (tokens em comum, ignorando a segmentacao):')
        print(f'    mediana            : {meio * 100:.1f}%')
        print(f'    minima             : {valores[0] * 100:.1f}%')
        print(f'    abaixo do limiar   : {abaixo} de {len(valores)} '
              f'({abaixo / len(valores) * 100:.1f}%)')

    identico = (
        relatorio['total_so_no_antigo'] == 0
        and relatorio['total_so_no_novo'] == 0
        and relatorio['docs_com_diferenca'] == 0
    )

    if relatorio['motivos']:
        print()
        print('  motivos das diferencas:')
        for motivo, quantidade in relatorio['motivos'].most_common():
            print(f'    {motivo:<28} {quantidade:>6}')

    if relatorio['exemplos']:
        print()
        print('  exemplos:')
        for exemplo in relatorio['exemplos']:
            print(f'    {exemplo}')

    print()
    if identico:
        print('  Os dois corpora sao identicos. O reprocessamento reproduz o Exp 002 e')
        print('  os CSVs usados sao os originais.')
    else:
        print('  Os corpora diferem. Isso nao inviabiliza o casamento: o que decide e a')
        print('  igualdade token a token de cada sentenca, dentro de um documento')
        print('  reconhecidamente o mesmo. Os numeros acima dizem o tamanho da diferenca.')

    if args.sessao is None:
        return 0 if identico else 1

    print()
    titulo = f'CASAMENTO COM A SESSAO {args.sessao}'
    print(titulo)
    print('-' * len(titulo))
    casadas, casamento = casar_sentencas_anotadas(
        args.sessao, antigo, novo, similaridade, args.limiar_doc
    )

    total = casamento['sentencas_na_sessao']
    if not total:
        print(f'  A sessao {args.sessao} nao tem sentencas. Nada a casar.')
        return 1

    proporcao = casamento['casamento_unico'] / total * 100
    print(f'  sentencas na sessao   : {total}')
    print(f"  casadas com seguranca : {casamento['casamento_unico']} ({proporcao:.2f}%)")
    print(f"  casamento ambiguo     : {casamento['casamento_ambiguo']}")
    print(f"  nao encontradas       : {casamento['sem_casamento']}")
    print(f"  documento ausente     : {casamento['doc_ausente']}")
    print(f"  documento pouco similar: {casamento['doc_pouco_similar']} "
          f"(em {len(casamento['docs_reprovados'])} documentos)")
    if casamento['doc_type_diferente']:
        print(f"  doc_type divergente   : {casamento['doc_type_diferente']}")
    if casamento['sem_hash_paciente']:
        print(f"  sem hash_paciente     : {casamento['sem_hash_paciente']} "
              f'(o corpus novo foi gerado sem propagar_paciente?)')
    if casamento['ja_preenchidas']:
        print(f"  ja tinham sentenca_idx: {casamento['ja_preenchidas']} "
              f'(serao sobrescritas)')

    if casamento['exemplos_falha']:
        print()
        print('  exemplos de falha:')
        for exemplo in casamento['exemplos_falha']:
            print(f'    {exemplo}')

    nao_casadas = total - casamento['casamento_unico']

    print()
    print('  O QUE ISSO SIGNIFICA')
    print('  --------------------')
    if nao_casadas == 0:
        print('  Todas as sentencas anotadas foram localizadas. O mapa de PHI encaixa')
        print('  integralmente e o corpus com surrogates pode ser gerado sem perda.')
    else:
        print(f'  {nao_casadas} sentencas ficam sem PHI e sem paciente. Elas continuam')
        print('  validas para o corpus, mas nelas as datas permanecem como placeholder')
        print('  e a consistencia de nome cai para o nivel do documento.')
        print(f'  Isso e uma limitacao a declarar, proporcional a {nao_casadas / total * 100:.1f}%')
        print('  do corpus, nao um impedimento.')

    print()
    if not args.aplicar:
        print('  Nada foi gravado. Para preencher sentenca_idx e hash_paciente nas')
        print(f'  {len(casadas)} sentencas casadas, rode de novo com --aplicar.')
    elif not casadas:
        print('  Nenhuma sentenca passou nas condicoes de seguranca. Nada a gravar.')
        return 1
    elif casamento['sem_hash_paciente'] == casamento['casamento_unico']:
        print('  Todas as sentencas casadas ficaram sem hash_paciente, o que indica que')
        print('  o corpus novo foi gerado sem propagar_paciente=True. Gravar assim')
        print('  resolveria metade do problema e esconderia a outra metade.')
        print('  Rode o reprocessamento de novo com propagar_paciente antes de aplicar.')
        return 1
    else:
        gravadas = aplicar(casadas)
        print(f'  {gravadas} sentencas atualizadas com sentenca_idx e hash_paciente.')
        print('  Nenhuma label foi tocada.')
        print()
        print('  Proximo passo: gerar o corpus com o mapa de PHI.')
        print()
        print(f'    python scripts/gerar_corpus_surrogate.py --sessao {args.sessao} '
              f'--versoes 10 \\')
        print('        --phi outputs/reprocessamento/'
              'Experimento_002_reproc_corpus_phi.jsonl \\')
        print('        --saida outputs/surrogates')

    return 0 if nao_casadas == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
