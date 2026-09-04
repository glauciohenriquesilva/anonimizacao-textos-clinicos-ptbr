#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Identifica se um par de CSVs é o que gerou determinada execução de pré-processamento.

    python scripts/conferir_csv.py --prescricoes csv\\Prescricoes.csv ^
                                   --pareceres   csv\\Pareceres.csv

Por que isto existe
===================
Os CSVs de entrada não ficam versionados nem guardados: eles entram pela interface web e
somem. Quando é preciso reprocessar um experimento antigo, a primeira pergunta é se os
arquivos em mãos são os certos, e reprocessar para descobrir custa dezenas de minutos.

Este script responde em segundos, comparando as contagens com o que o banco registra em
`tb_anonclin_execucao_preprocessamento`. Se bater com alguma execução, ele diz qual.

O que ele imprime
=================
Só contagens e nomes de coluna. Nenhuma linha de texto clínico, nenhum identificador de
paciente, nenhuma amostra de conteúdo. Pode rodar e colar a saída em qualquer lugar.

A leitura usa os mesmos leitores do pipeline, então uma incompatibilidade de formato
aparece aqui como erro em vez de aparecer no meio do reprocessamento.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'anonclin.settings')

import django  # noqa: E402
django.setup()

from analise_exploratoria.services.exploracao import (  # noqa: E402
    ler_prescricoes,
    ler_pareceres,
)
from preprocessamento.models import ExecucaoPreprocessamento  # noqa: E402


COLUNAS_ESPERADAS = {
    'prescricoes': ['cd_paciente', 'dt_atendimento', 'ds_evolucao'],
    'pareceres':   ['cd_paciente', 'dt_atendimento', 'ds_parecer'],
}


def descrever(rotulo, df, caminho):
    """
    Imprime o que se pode dizer do arquivo sem expor conteúdo.

    As colunas ausentes importam mais que as presentes: `cd_paciente` faltando significa
    que o reprocessamento não conseguirá propagar o vínculo com o paciente, e o problema
    só apareceria no fim, com o corpus já gerado.
    """
    print(f'{rotulo}')
    print(f'  arquivo    : {os.path.basename(caminho)}')
    print(f'  registros  : {len(df)}')
    print(f'  colunas    : {len(df.columns)}')

    faltando = [c for c in COLUNAS_ESPERADAS[rotulo.lower()] if c not in df.columns]
    if faltando:
        print(f'  AUSENTES   : {faltando}')
    else:
        print('  colunas-alvo presentes (cd_paciente inclusive)')
    return len(df)


def main():
    parser = argparse.ArgumentParser(
        description='Diz se um par de CSVs corresponde a alguma execução registrada.'
    )
    parser.add_argument('--prescricoes', required=True)
    parser.add_argument('--pareceres', required=True)
    args = parser.parse_args()

    for caminho in (args.prescricoes, args.pareceres):
        if not os.path.exists(caminho):
            sys.exit(f'Arquivo nao encontrado: {caminho}')

    print('CONTAGENS')
    print('---------')
    total_presc = descrever('Prescricoes', ler_prescricoes(args.prescricoes),
                            args.prescricoes)
    print()
    total_par = descrever('Pareceres', ler_pareceres(args.pareceres), args.pareceres)

    print()
    print('EXECUCOES REGISTRADAS')
    print('---------------------')
    execucoes = list(
        ExecucaoPreprocessamento.objects
        .all()
        .order_by('id')
        .values('id', 'criado_em', 'amostra_por_tipo', 'total_prescricoes',
                'total_pareceres', 'total_documentos', 'total_sentencas',
                'experimento_id')
    )

    # Duas categorias, e a diferença entre elas importa muito.
    #
    # "Exato" é quando a execução processou o arquivo inteiro e chegou nas contagens que
    # o arquivo tem. Só isso identifica o par de CSVs.
    #
    # "Por amostragem" é quando a execução cortou os CSVs antes de processar, com
    # `amostra_por_tipo`. Nesse caso qualquer arquivo com registros suficientes satisfaz
    # a contagem, e a compatibilidade não diz nada: uma execução com amostra=1000 bate
    # com qualquer CSV de mil linhas ou mais. Misturar as duas listas faria o script
    # parecer indeciso quando na verdade a resposta é clara.
    exatas = []
    por_amostragem = []

    for execucao in execucoes:
        amostra = execucao['amostra_por_tipo']
        exata = (execucao['total_prescricoes'] == total_presc
                 and execucao['total_pareceres'] == total_par)

        if exata and not amostra:
            exatas.append(execucao)
            marca = ' <== BATE (arquivo inteiro)'
        elif amostra and (execucao['total_prescricoes'] == min(amostra, total_presc)
                          and execucao['total_pareceres'] == min(amostra, total_par)):
            por_amostragem.append(execucao)
            marca = ' (compativel so por amostragem)'
        else:
            marca = ''

        print(f"  id={execucao['id']:<3} exp={str(execucao['experimento_id']):<5} "
              f"{execucao['criado_em']:%d/%m/%Y %H:%M}  "
              f"presc={execucao['total_prescricoes']:<6} "
              f"par={execucao['total_pareceres']:<6} "
              f"amostra={str(execucao['amostra_por_tipo']):<6}"
              f"{marca}")

    print()
    if not exatas:
        print('  Nenhuma execucao processou estes arquivos por inteiro.')
        if por_amostragem:
            ids = ', '.join(f"id={e['id']}" for e in por_amostragem)
            print(f'  As execucoes {ids} usaram amostragem e por isso aceitam qualquer')
            print('  arquivo grande o bastante. Isso nao identifica nada.')
        return 1

    ids = ', '.join(f"id={e['id']}" for e in exatas)
    print(f'  Processados por inteiro em: {ids}')
    if por_amostragem:
        outros = ', '.join(f"id={e['id']}" for e in por_amostragem)
        print(f'  (as execucoes {outros} usaram amostragem e aceitariam qualquer arquivo')
        print('   grande o bastante, entao nao contam como identificacao)')
    print()
    print('  Contagem igual e evidencia forte, nao prova. Duas extracoes diferentes')
    print('  podem ter o mesmo tamanho. A prova vem do reprocessamento seguido de')
    print('  scripts/conferir_reprocessamento.py, que compara o corpus token a token.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
