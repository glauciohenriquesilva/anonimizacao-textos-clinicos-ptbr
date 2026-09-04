#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste do registro das gerações de corpus com surrogates.

    python scripts/testar_registro_surrogates.py --sessao 5

Confere que o registro grava o que promete e que a conferência de integridade detecta um
arquivo alterado.

Nada fica no banco
==================
A parte que escreve roda dentro de uma transação que é desfeita no final, de propósito.
Um teste que deixa registro para trás polui a mesma tabela que serve de histórico do
experimento, e daqui a alguns meses ninguém saberia distinguir uma geração de verdade de
um resíduo de teste.

Os arquivos usados são criados numa pasta temporária, com conteúdo inventado. O banco é
lido apenas para confirmar que a sessão existe.
"""

import argparse
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'anonclin.settings')

import django  # noqa: E402
django.setup()

from django.db import transaction  # noqa: E402

from anonimizacao.models import VersaoCorpusSurrogate  # noqa: E402
from anonimizacao.services.registro_surrogates import (  # noqa: E402
    conferir_integridade,
    estado_do_repositorio,
    hash_arquivo,
    registrar_geracao,
)


class Desfazer(Exception):
    """Sinal interno para abortar a transação depois das verificações."""


def resumo_falso(rotulo, seed, modo, arquivo):
    """Monta um resumo com a mesma forma que o gerador devolve."""
    return {
        'rotulo':                  rotulo,
        'seed':                    seed,
        'modo':                    modo,
        'arquivo':                 arquivo,
        'sentencas':               3,
        'entidades_distintas':     7,
        'pacientes_com_shift':     2,
        'colisoes_evitadas':       1,
        'colisoes_nao_resolvidas': 0,
        'placeholders_restantes':  0,
        'tipos_nao_suportados':    [],
        'avisos':                  [],
        'problemas_alinhamento':   0,
    }


def main():
    parser = argparse.ArgumentParser(description='Testa o registro de gerações.')
    parser.add_argument('--sessao', type=int, required=True,
                        help='Sessão de anotação existente, usada só como referência.')
    args = parser.parse_args()

    pasta = tempfile.mkdtemp(prefix='teste_registro_')
    falhas = []

    try:
        # 1. Hash de arquivo
        caminho = os.path.join(pasta, 'corpus_v01.jsonl')
        with open(caminho, 'w', encoding='utf-8') as arquivo:
            arquivo.write('{"tokens": ["a"], "labels": ["O"]}\n')

        digest = hash_arquivo(caminho)
        print('1. hash de arquivo')
        print(f'   sha256 : {digest[:16]}...')
        if len(digest) != 64:
            falhas.append('hash_arquivo nao devolveu um sha256 de 64 caracteres')
        if hash_arquivo(os.path.join(pasta, 'nao_existe.jsonl')) != '':
            falhas.append('hash_arquivo deveria devolver vazio para arquivo ausente')

        # O mesmo conteúdo tem de dar o mesmo hash, senão a conferência não vale nada
        copia = os.path.join(pasta, 'copia.jsonl')
        shutil.copyfile(caminho, copia)
        if hash_arquivo(copia) != digest:
            falhas.append('conteudos iguais deram hashes diferentes')

        # 2. Estado do repositório
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        commit, sujo = estado_do_repositorio(raiz)
        print()
        print('2. estado do repositorio')
        print(f'   commit : {commit[:12] if commit else "nao identificado"}')
        print(f'   sujo   : {sujo}')
        if commit and len(commit) != 40:
            falhas.append(f'commit com tamanho inesperado: {len(commit)}')

        # 3. Registro completo, desfeito ao final
        segundo = os.path.join(pasta, 'corpus_placeholder.jsonl')
        with open(segundo, 'w', encoding='utf-8') as arquivo:
            arquivo.write('{"tokens": ["b"], "labels": ["O"]}\n')

        resumos = [
            resumo_falso('v01', 1, VersaoCorpusSurrogate.MODO_VEROSSIMIL,
                         'corpus_v01.jsonl'),
            resumo_falso('placeholder', 1, VersaoCorpusSurrogate.MODO_PLACEHOLDER,
                         'corpus_placeholder.jsonl'),
        ]
        contagem = {'anotador_id': 1, 'mapa_phi_carregado': False, 'sentencas_lidas': 3}

        print()
        print('3. registro no banco (desfeito ao final)')
        try:
            with transaction.atomic():
                geracao = registrar_geracao(
                    sessao_id=args.sessao,
                    resumos=resumos,
                    contagem=contagem,
                    caminho_saida=pasta,
                    caminho_phi=None,
                    obs='registro de teste, nao deve sobreviver',
                    raiz_repositorio=raiz,
                )
                print(f'   geracao id          : {geracao.id}')
                print(f'   versoes gravadas    : {geracao.versoes.count()}')
                print(f'   verossimeis         : {geracao.total_versoes}')
                print(f'   com contraprova     : {geracao.com_contraprova}')
                print(f'   reproduzivel        : {geracao.reproduzivel}')

                if geracao.versoes.count() != 2:
                    falhas.append('deveriam ter sido gravadas 2 versoes')
                if geracao.total_versoes != 1:
                    falhas.append('total_versoes deveria contar so as verossimeis')
                if not geracao.com_contraprova:
                    falhas.append('com_contraprova deveria ser verdadeiro')

                versao = geracao.versoes.get(rotulo='v01')
                if versao.hash_arquivo != digest:
                    falhas.append('o hash gravado nao bate com o do arquivo')
                if not versao.limpa:
                    falhas.append('a versao sem pendencia deveria ser considerada limpa')

                # 4. Conferência de integridade, antes e depois de mexer no arquivo
                problemas = conferir_integridade(geracao)
                print()
                print('4. conferencia de integridade')
                print(f'   antes de alterar    : {len(problemas)} problema(s)')
                if problemas:
                    falhas.append(f'nao deveria haver problema ainda: {problemas}')

                with open(caminho, 'a', encoding='utf-8') as arquivo:
                    arquivo.write('{"tokens": ["c"], "labels": ["O"]}\n')

                problemas = conferir_integridade(geracao)
                print(f'   depois de alterar   : {len(problemas)} problema(s)')
                for item in problemas:
                    print(f'     {item}')
                if len(problemas) != 1:
                    falhas.append('a alteracao do arquivo deveria ter sido detectada')

                raise Desfazer()
        except Desfazer:
            print()
            print('   transacao desfeita, nada ficou no banco')

    finally:
        shutil.rmtree(pasta, ignore_errors=True)

    print()
    if falhas:
        print('FALHAS')
        for falha in falhas:
            print(f'  - {falha}')
        return 1

    print('Todas as verificacoes passaram.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
