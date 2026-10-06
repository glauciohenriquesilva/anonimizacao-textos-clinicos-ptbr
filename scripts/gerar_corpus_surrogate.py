#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gera as N versões do corpus com surrogates, mais os braços de contraprova.

    python scripts/gerar_corpus_surrogate.py --sessao 5 --versoes 10 \
        --phi outputs/preprocessamento/Experimento_002_corpus_phi.jsonl \
        --saida outputs/surrogates

O que sai
=========
Para cada semente de 1 a N, um arquivo `corpus_v01.jsonl`, `corpus_v02.jsonl` e assim
por diante, todos com a mesma estrutura e a mesma quantidade de sentenças do corpus
original, mudando apenas os valores das entidades sensíveis.

Junto saem os dois braços de contraprova pedidos pelo orientador:

    corpus_placeholder.jsonl   entidades viram PESSOA_1, PESSOA_2 e assim por diante
    corpus_celebridade.jsonl   entidades viram nomes muito conhecidos

Eles existem para testar se a natureza do valor substituto altera o desempenho. A
expectativa é que ambos sejam mais fáceis para o modelo do que os surrogates
verossímeis, e é esse contraste que sustenta a conclusão: se qualquer substituição
desse o mesmo resultado, não haveria o que demonstrar sobre verossimilhança.

E um `relatorio.json` com os números de cada versão, para conferência.

O registro no banco
===================
Ao final, a geração é registrada nas tabelas `tb_anonclin_geracao_surrogate` e
`tb_anonclin_versao_surrogate`: semente e modo de cada versão, contagens, hash de cada
arquivo gerado, hash do mapa de PHI usado e o commit do repositório no momento da
execução. É o que permite, meses depois, saber qual código e qual entrada produziram cada
arquivo, e conferir que o arquivo em disco ainda é aquele.

O registro guarda só metadado. Nenhum valor de PHI e nenhum surrogate entram no banco.
Para um teste rápido, sem sujar o banco, existe `--sem-registro`.

O que NÃO sai daqui
===================
O corpus original com os valores reais. Este script só lê o banco e o mapa de PHI, e
grava corpora já substituídos. O mapa de PHI, que é o material sensível, permanece onde
está e não é copiado para a pasta de saída.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'anonclin.settings')

import django  # noqa: E402
django.setup()

from anonimizacao.services.aplicar_surrogates import (  # noqa: E402
    gerar_corpus,
    conferir_alinhamento,
    _coletar_substituicoes,
)
from anonimizacao.services.leitor_gold import (  # noqa: E402
    carregar_gold,
    descrever_relatorio,
)
from anonimizacao.services.registro_surrogates import (  # noqa: E402
    registrar_geracao,
    descrever_geracao,
)
from anonimizacao.services.surrogates import (  # noqa: E402
    GeradorSurrogates,
    deslocar_data_livre,
)


def escrever_corpus(sentencas, caminho):
    """
    Grava o corpus em JSONL, uma sentença por linha.

    Só vão os campos que o corpus publicado precisa ter. O `hash_paciente` fica de fora
    de propósito: ele é a chave de consistência usada durante a geração, mas publicá-lo
    permitiria agrupar todas as sentenças de uma mesma pessoa, que é justamente o tipo
    de ligação que a substituição procura dificultar.
    """
    with open(caminho, 'w', encoding='utf-8') as arquivo:
        for sentenca in sentencas:
            registro = {
                'doc_id':   sentenca['doc_id'],
                'doc_type': sentenca['doc_type'],
                'tokens':   sentenca['tokens'],
                'labels':   sentenca['labels'],
            }
            arquivo.write(json.dumps(registro, ensure_ascii=False) + '\n')


def tem_data_nao_deslocavel(sentenca):
    """
    Diz se a sentença tem alguma data que o gerador não consegue deslocar.

    São dois casos, e nos dois o gerador devolveria a data como está, isto é, real:

      - data anotada à mão em formato não reconhecido, quase sempre erro de digitação
        ou data colada em outra palavra ('12 / 03hoje', '12 / 202');
      - data do mapa de PHI que tem cara de ISO mas não existe no calendário, como mês
        13 ou dia 31 de um mês de 30. A expressão regular capturou o que estava
        escrito, e o que estava escrito era um erro de quem digitou o prontuário.
    """
    from datetime import date

    descartavel = {'sobreposicao': 0, 'posicao_invalida': 0, 'token_inesperado': 0}
    for sub in _coletar_substituicoes(sentenca['tokens'], sentenca['labels'],
                                     sentenca.get('phi'), descartavel):
        if sub['tipo'] != 'DATA':
            continue
        valor = (sub['original'] or '').strip()
        iso = re.fullmatch(r'(\d{4})-(\d{2})-(\d{2})', valor)
        if iso:
            try:
                date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
            except ValueError:
                return True
            continue
        if deslocar_data_livre(valor, 1) is None:
            return True
    return False


def gerar_uma_versao(gold, rotulo, seed, modo, diretorio, problemas_globais):
    """Gera, confere e grava uma versão do corpus. Devolve o resumo dela."""
    gerador = GeradorSurrogates(seed=seed, modo=modo)
    corpus, relatorio = gerar_corpus(gold, gerador)

    problemas = conferir_alinhamento(corpus)
    if problemas:
        # Guarda uma amostra no relatorio, mas o resumo devolvido carrega o total.
        # Truncar sem dizer que truncou faz o problema parecer menor do que e.
        problemas_globais.extend(f'{rotulo}: {p}' for p in problemas[:20])

    caminho = os.path.join(diretorio, f'corpus_{rotulo}.jsonl')
    escrever_corpus(corpus, caminho)

    resumo = {
        'rotulo':                 rotulo,
        'seed':                   seed,
        'modo':                   modo,
        'arquivo':                os.path.basename(caminho),
        'sentencas':              relatorio['sentencas'],
        'entidades_distintas':    relatorio['gerador']['entidades_distintas'],
        'pacientes_com_shift':    relatorio['gerador']['pacientes_com_shift'],
        'colisoes_evitadas':      relatorio['gerador']['colisoes_evitadas'],
        'colisoes_nao_resolvidas': relatorio['gerador']['colisoes_nao_resolvidas'],
        'placeholders_restantes': relatorio['placeholders_restantes'],
        'tipos_nao_suportados':   relatorio['gerador']['tipos_nao_suportados'],
        'avisos':                 relatorio['avisos'],
        'problemas_alinhamento':  len(problemas),
    }
    return resumo


def main():
    parser = argparse.ArgumentParser(
        description='Gera N versões do corpus com surrogates verossímeis.'
    )
    parser.add_argument('--sessao', type=int, required=True,
                        help='ID da sessão de anotação que contém o gold standard.')
    parser.add_argument('--versoes', type=int, default=10,
                        help='Quantas versões verossímeis gerar (default 10).')
    parser.add_argument('--anotador', type=int, default=None,
                        help='ID do anotador a usar como base. Só é necessário quando '
                             'a sessão tem mais de um.')
    parser.add_argument('--phi', default=None,
                        help='Caminho do arquivo *_phi.jsonl com os valores originais '
                             'do PHI tratado por regex. Sem ele, datas e telefones '
                             'ficam como placeholder no corpus gerado.')
    parser.add_argument('--saida', default='outputs/surrogates',
                        help='Diretório onde gravar os corpora (default outputs/surrogates).')
    parser.add_argument('--so-casadas', action='store_true',
                        help='Usa apenas as sentencas que casaram com o corpus '
                             'reprocessado, isto e, as que tem sentenca_idx e '
                             'hash_paciente. As demais ficam de fora de todos os bracos.')
    parser.add_argument('--sem-contraprova', action='store_true',
                        help='Não gera os braços placeholder e celebridade.')
    parser.add_argument('--experimento', type=int, default=None,
                        help='ID do experimento ao qual associar esta geração.')
    parser.add_argument('--obs', default=None,
                        help='Anotação livre a guardar junto do registro, por exemplo o '
                             'motivo desta rodada.')
    parser.add_argument('--sem-registro', action='store_true',
                        help='Gera os arquivos sem registrar a rodada no banco. Use só '
                             'para teste: sem registro, a geração não é rastreável.')
    args = parser.parse_args()

    print(f'Lendo o gold standard da sessao {args.sessao}...')
    gold, contagem = carregar_gold(args.sessao, args.anotador, args.phi)
    print(descrever_relatorio(contagem))

    if not gold:
        sys.exit('Nenhuma sentenca anotada foi encontrada. Nada a gerar.')

    os.makedirs(args.saida, exist_ok=True)

    if args.so_casadas:
        # Uma sentença sem casamento não tem mapa de PHI nem paciente. Nela as datas
        # continuariam como marcador dentro do braço com surrogates, e o braço passaria
        # a misturar dois tratamentos. Por decisão de desenho, essas sentenças saem dos
        # três braços, para que todos sejam comparados sobre exatamente o mesmo conjunto.
        total_antes = len(gold)
        gold = [s for s in gold
                if s['sentenca_idx'] is not None and s['hash_paciente']]
        contagem['sentencas_descartadas_sem_casamento'] = total_antes - len(gold)
        contagem['sentencas_usadas'] = len(gold)
        print(f'  filtro --so-casadas: {len(gold)} sentencas usadas, '
              f"{contagem['sentencas_descartadas_sem_casamento']} descartadas")

        # Segunda peneira, pelo mesmo motivo da primeira: uma data que o gerador não
        # sabe deslocar ficaria real no braço com surrogates. São poucas sentenças, e
        # tirá-las de todos os braços custa menos do que deixar data real no corpus.
        total_antes = len(gold)
        gold = [s for s in gold if not tem_data_nao_deslocavel(s)]
        contagem['sentencas_descartadas_data_nao_deslocavel'] = total_antes - len(gold)
        contagem['sentencas_usadas'] = len(gold)
        print(f'  datas nao deslocaveis: mais '
              f"{contagem['sentencas_descartadas_data_nao_deslocavel']} sentencas "
              f'descartadas, restam {len(gold)}')
        if not gold:
            sys.exit('Nenhuma sentenca casada. Rode conferir_reprocessamento.py '
                     'com --aplicar antes.')

        # A lista de identificadores é o que permite montar o braço real e o conjunto
        # de teste com as mesmas sentenças. Só números, nenhum texto.
        with open(os.path.join(args.saida, 'sentencas_usadas.json'), 'w',
                  encoding='utf-8') as arquivo:
            json.dump(sorted(s['sentenca_pk'] for s in gold), arquivo)

    problemas = []
    resumos = []

    print()
    print(f'Gerando {args.versoes} versoes verossimeis...')
    for seed in range(1, args.versoes + 1):
        rotulo = f'v{seed:02d}'
        resumo = gerar_uma_versao(gold, rotulo, seed, GeradorSurrogates.MODO_VEROSSIMIL,
                                  args.saida, problemas)
        resumos.append(resumo)
        print(f"  {rotulo}: {resumo['sentencas']} sentencas, "
              f"{resumo['entidades_distintas']} entidades, "
              f"{resumo['placeholders_restantes']} placeholders restantes, "
              f"{resumo['avisos'].get('datas_nao_deslocadas', 0)} datas nao deslocadas")

    if not args.sem_contraprova:
        print()
        print('Gerando os bracos de contraprova...')
        for rotulo, modo in (
            ('placeholder', GeradorSurrogates.MODO_PLACEHOLDER),
            ('celebridade', GeradorSurrogates.MODO_CELEBRIDADE),
        ):
            resumo = gerar_uma_versao(gold, rotulo, 1, modo, args.saida, problemas)
            resumos.append(resumo)
            print(f"  {rotulo}: {resumo['sentencas']} sentencas")

    # O registro vem antes de gravar o relatorio.json para que o id da geração possa
    # entrar nele. É esse id que liga o arquivo solto na pasta à linha no banco.
    geracao = None
    if not args.sem_registro:
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        geracao = registrar_geracao(
            sessao_id=args.sessao,
            resumos=resumos,
            contagem=contagem,
            caminho_saida=args.saida,
            caminho_phi=args.phi,
            experimento_id=args.experimento,
            obs=args.obs,
            raiz_repositorio=raiz,
        )
        print()
        print('REGISTRO')
        print('--------')
        print(descrever_geracao(geracao))

    relatorio = {
        'sessao':          args.sessao,
        'geracao_id':      geracao.id if geracao else None,
        'leitura':         contagem,
        'versoes':         resumos,
        'problemas_alinhamento': problemas,
    }
    caminho_relatorio = os.path.join(args.saida, 'relatorio.json')
    with open(caminho_relatorio, 'w', encoding='utf-8') as arquivo:
        json.dump(relatorio, arquivo, ensure_ascii=False, indent=2)

    print()
    print(f'Corpora gravados em {args.saida}')
    print(f'Relatorio em {caminho_relatorio}')
    if args.sem_registro:
        print('Rodada NAO registrada no banco (--sem-registro).')

    # Sinaliza o que precisa de atenção antes de usar estes corpora num experimento
    alertas = []
    total_placeholders = sum(r['placeholders_restantes'] for r in resumos)
    if total_placeholders:
        alertas.append(
            f'{total_placeholders} placeholders sobraram no total. Se o mapa de PHI nao '
            f'foi informado, isso e esperado; se foi, corpus e mapa podem estar '
            f'desalinhados.'
        )
    total_problemas = sum(r['problemas_alinhamento'] for r in resumos)
    if total_problemas:
        alertas.append(
            f'{total_problemas} problemas de alinhamento BIO no total '
            f'({len(problemas)} registrados no relatorio, uma amostra por versao). '
            f'Se o mesmo numero aparece em todas as versoes, o problema esta no gold '
            f'standard e nao na substituicao: rode scripts/conferir_gold.py.'
        )
    nao_resolvidas = sum(r['colisoes_nao_resolvidas'] for r in resumos)
    if nao_resolvidas:
        alertas.append(
            f'{nao_resolvidas} valores nao puderam ser diferenciados do original. '
            f'Os catalogos de surrogates estao pequenos demais para este corpus.'
        )
    tipos = sorted({t for r in resumos for t in r['tipos_nao_suportados']})
    if tipos:
        alertas.append(
            f'Tipos de entidade sem tratamento no gerador: {tipos}. '
            f'Eles permaneceram no corpus com o valor real.'
        )

    if geracao is not None and not geracao.reproduzivel:
        alertas.append(
            'A geracao ficou registrada como nao reproduzivel: faltou o commit, ou havia '
            'alteracao nao commitada, ou o mapa de PHI nao pode ser identificado. Antes '
            'de levar estes numeros para o texto, commite o codigo e gere de novo.'
        )
    if args.sem_registro:
        alertas.append(
            'Rodada gerada sem registro. Os arquivos existem, mas nao ha como saber '
            'depois qual codigo e qual entrada os produziram.'
        )

    if alertas:
        print()
        print('ATENCAO')
        for alerta in alertas:
            print(f'  - {alerta}')
        return 1

    print()
    print('Nenhum problema encontrado.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
