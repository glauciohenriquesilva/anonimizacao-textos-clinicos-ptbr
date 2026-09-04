# -*- coding: utf-8 -*-
"""
Registro no banco das gerações de corpus com surrogates.

O que este módulo resolve
=========================
O gerador produz arquivos numa pasta. A pasta, sozinha, não conta a história: não diz
qual código gerou, se o mapa de PHI era o mesmo, nem se o arquivo que está lá hoje é o
que produziu os números citados no texto. Este módulo é a ponte entre o que foi gerado e
o que fica registrado, e existe separado dos modelos para que o script continue simples e
para que o cálculo de hash possa ser testado sem subir o Django.

O que não passa por aqui
========================
Conteúdo. As funções leem arquivos apenas em blocos, para calcular o hash, e nada do que
é lido fica em memória depois nem entra no banco. O mapa de PHI, em particular, é
identificado só pelo resumo criptográfico: guardar o hash permite conferir que a mesma
entrada foi usada numa geração posterior, sem que nenhum valor real saia do lugar.
"""

import hashlib
import os
import subprocess


def hash_arquivo(caminho, bloco=1024 * 1024):
    """
    Devolve o SHA-256 do arquivo, lido em blocos.

    A leitura em blocos importa: o corpus do Exp 002 tem 5.000 sentenças, e o mapa de PHI
    pode ser maior ainda. Carregar o arquivo inteiro só para resumir seria desperdício de
    memória sem ganho nenhum.

    Devolve string vazia quando o caminho não existe, porque a ausência do arquivo não é
    motivo para interromper o registro: é uma informação a mais, e ela fica visível no
    campo vazio.
    """
    if not caminho or not os.path.exists(caminho):
        return ''

    digestor = hashlib.sha256()
    with open(caminho, 'rb') as arquivo:
        for pedaco in iter(lambda: arquivo.read(bloco), b''):
            digestor.update(pedaco)
    return digestor.hexdigest()


def estado_do_repositorio(raiz=None):
    """
    Devolve (commit, sujo) do repositório onde o código está.

    O commit identifica a versão do gerador e dos catálogos de surrogates. O `sujo` diz se
    havia alteração não commitada no momento da geração, e é justamente esse segundo dado
    que costuma faltar: um commit anotado com a árvore suja não reproduz nada, porque o
    código que rodou não é o código que está no commit.

    Quando o git não está disponível, ou o diretório não é um repositório, devolve
    ('', False). Não faz sentido derrubar uma geração por causa disso.
    """
    raiz = raiz or os.getcwd()

    def executar(argumentos):
        try:
            saida = subprocess.run(
                ['git'] + argumentos, cwd=raiz, capture_output=True, text=True, timeout=15
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if saida.returncode != 0:
            return None
        return saida.stdout.strip()

    commit = executar(['rev-parse', 'HEAD'])
    if commit is None:
        return '', False

    pendencias = executar(['status', '--porcelain'])
    return commit, bool(pendencias)


def registrar_geracao(sessao_id, resumos, contagem, caminho_saida,
                      caminho_phi=None, experimento_id=None, obs=None,
                      raiz_repositorio=None):
    """
    Grava a geração e suas versões, e devolve o objeto criado.

    Recebe exatamente o que o script já tem em mãos ao terminar: a lista de resumos por
    versão, o relatório da leitura do gold e a pasta de saída. Os hashes dos arquivos são
    calculados aqui, depois de tudo gravado em disco, porque é o arquivo final que
    interessa conferir.

    Tudo acontece numa transação: ou a geração inteira fica registrada, ou nada fica. Meia
    geração no banco seria pior que nenhuma, porque pareceria completa.
    """
    from django.db import transaction

    from anonimizacao.models import GeracaoCorpusSurrogate, VersaoCorpusSurrogate

    commit, sujo = estado_do_repositorio(raiz_repositorio)
    verossimeis = [r for r in resumos
                   if r['modo'] == VersaoCorpusSurrogate.MODO_VEROSSIMIL]
    contraprova = len(resumos) > len(verossimeis)

    with transaction.atomic():
        geracao = GeracaoCorpusSurrogate.objects.create(
            sessao_id=sessao_id,
            experimento_id=experimento_id,
            anotador_base_id=contagem.get('anotador_id'),
            total_versoes=len(verossimeis),
            com_contraprova=contraprova,
            caminho_saida=os.path.abspath(caminho_saida),
            hash_mapa_phi=hash_arquivo(caminho_phi),
            commit_git=commit,
            repositorio_sujo=sujo,
            relatorio_leitura_json=contagem,
            obs=obs or None,
        )

        for resumo in resumos:
            caminho = os.path.join(caminho_saida, resumo['arquivo'])
            VersaoCorpusSurrogate.objects.create(
                geracao=geracao,
                rotulo=resumo['rotulo'],
                seed=resumo['seed'],
                modo=resumo['modo'],
                arquivo=resumo['arquivo'],
                hash_arquivo=hash_arquivo(caminho),
                bytes_arquivo=(os.path.getsize(caminho)
                               if os.path.exists(caminho) else None),
                sentencas=resumo['sentencas'],
                entidades_distintas=resumo['entidades_distintas'],
                pacientes_com_shift=resumo['pacientes_com_shift'],
                colisoes_evitadas=resumo['colisoes_evitadas'],
                colisoes_nao_resolvidas=resumo['colisoes_nao_resolvidas'],
                placeholders_restantes=resumo['placeholders_restantes'],
                problemas_alinhamento=resumo['problemas_alinhamento'],
                tipos_nao_suportados_json=resumo['tipos_nao_suportados'],
                avisos_json=resumo['avisos'],
            )

    return geracao


def conferir_integridade(geracao):
    """
    Refaz o hash dos arquivos de uma geração e diz o que mudou desde o registro.

    Serve para o momento em que os números vão para o texto: antes de citar um resultado,
    vale confirmar que o arquivo que produziu aquele resultado ainda é o mesmo. Devolve
    uma lista de problemas, vazia quando está tudo igual.
    """
    problemas = []
    for versao in geracao.versoes.all():
        caminho = os.path.join(geracao.caminho_saida, versao.arquivo)
        if not os.path.exists(caminho):
            problemas.append(f'{versao.rotulo}: arquivo ausente em {caminho}')
            continue
        if not versao.hash_arquivo:
            problemas.append(f'{versao.rotulo}: registrado sem hash, nada a conferir')
            continue
        atual = hash_arquivo(caminho)
        if atual != versao.hash_arquivo:
            problemas.append(
                f'{versao.rotulo}: o arquivo mudou depois de gerado '
                f'(registrado {versao.hash_arquivo[:12]}, atual {atual[:12]})'
            )
    return problemas


def descrever_geracao(geracao):
    """Formata o registro para exibição no terminal, logo depois de gravado."""
    linhas = [
        f'  registro id              : {geracao.id}',
        f'  sessao de anotacao       : {geracao.sessao_id}',
        f'  versoes verossimeis      : {geracao.total_versoes}',
        f'  bracos de contraprova    : {"sim" if geracao.com_contraprova else "nao"}',
    ]
    if geracao.commit_git:
        sufixo = ' (arvore suja)' if geracao.repositorio_sujo else ''
        linhas.append(f'  commit                   : {geracao.commit_git[:12]}{sufixo}')
    else:
        linhas.append('  commit                   : nao identificado')

    if geracao.hash_mapa_phi:
        linhas.append(f'  mapa de PHI (sha256)     : {geracao.hash_mapa_phi[:12]}')

    if not geracao.reproduzivel:
        linhas.append(
            '  ATENCAO: esta geracao nao e reproduzivel pelo que ficou registrado. '
            'Commite as alteracoes e gere de novo antes de usar estes numeros.'
        )
    return '\n'.join(linhas)
