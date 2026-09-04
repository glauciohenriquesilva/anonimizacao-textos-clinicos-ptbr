#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Demonstração do gerador de surrogates, feita para inspeção humana.

    python scripts/demo_surrogates.py

Não usa Django, não lê banco, não toca em dado real. Todos os valores de entrada são
inventados. Serve para você olhar a saída e julgar o que só quem conhece o domínio pode
julgar: **isto passaria por um prontuário do ES?**

Opções:
    --seed N        semente da geração (default 1)
    --n N           quantos nomes gerar na primeira seção (default 20)
    --modo MODO     verossimil (default) | placeholder | celebridade
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anonimizacao.services.surrogates import GeradorSurrogates  # noqa: E402


# Entradas fictícias, com as formas que aparecem em texto clínico
NOMES_ENTRADA = [
    'MARIA DA SILVA', 'JOAO SANTOS', 'ANA PAULA DOS SANTOS', 'J. OLIVEIRA',
    'Carlos Eduardo Lima', 'ANTONIA', 'JOSE CARLOS DE SOUZA', 'francisca alves',
    'PEDRO HENRIQUE', 'LUCIA', 'RAIMUNDO NONATO DA COSTA', 'M. FERREIRA',
    'TEREZINHA DE JESUS', 'MANOEL', 'ROSA MARIA', 'FRANCISCO DAS CHAGAS',
    'ANA', 'LUIZ ANTONIO', 'VERA LUCIA DOS REIS', 'SEBASTIAO',
]

INSTITUICOES = [
    'HOSPITAL SANTA CASA', 'UPA DE CARAPINA', 'UBS JARDIM CAMBURI',
    'HOSPITAL ESTADUAL CENTRAL', 'MATERNIDADE SAO JOSE', 'CLINICA SAO MARCOS',
    'PRONTO ATENDIMENTO DE VILA VELHA', 'CENTRO DE SAUDE DA SERRA',
]

ENDERECOS = [
    'RUA DAS PALMEIRAS', 'AVENIDA VITORIA, 1200', 'TRAVESSA SAO PEDRO',
    'RODOVIA DO CONTORNO', 'RUA PROJETADA A', 'ALAMEDA DOS PINHEIROS, 45',
]

ESTRUTURADOS = [
    ('CPF', '123.456.789-00'), ('CPF', '12345678901'),
    ('CEP', '29160-021'), ('CEP', '29160021'),
    ('TELEFONE', '(27) 99706-2830'), ('TELEFONE', '33366997'),
    ('TELEFONE', '27999998888'), ('TELEFONE', '9999-9999'),
    ('EMAIL', 'paciente@provedor.com.br'),
    ('DOCUMENTO', '1.234.567-8'), ('DOCUMENTO', '123456789012345'),
]

# Um "paciente" com várias datas, para mostrar a preservação de intervalos
DATAS_PACIENTE = ['2025-01-10', '2025-01-17', '2025-02-09', '2025-03-11']


def secao(titulo):
    print()
    print(titulo)
    print('-' * len(titulo))


def main():
    parser = argparse.ArgumentParser(description='Demonstração do gerador de surrogates.')
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--n', type=int, default=20)
    parser.add_argument('--modo', default='verossimil',
                        choices=['verossimil', 'placeholder', 'celebridade'])
    args = parser.parse_args()

    g = GeradorSurrogates(seed=args.seed, modo=args.modo)

    print(f'Gerador de surrogates | seed={args.seed} | modo={args.modo}')
    print('Todas as entradas abaixo sao ficticias.')

    secao('1. NOMES: a forma do original e preservada?')
    print('   (numero de partes, abreviacao, particula, caixa e genero)')
    print()
    for original in NOMES_ENTRADA[:args.n]:
        # chave = identidade do paciente; aqui usamos o proprio nome como chave ficticia
        print(f'   {original:<28} -> {g.nome_pessoa(original, chave=original)}')

    secao('2. MESMA PESSOA vs HOMONIMO')
    print()
    print(f"   paciente A, 'MARIA DA SILVA'  -> {g.nome_pessoa('MARIA DA SILVA', chave='A')}")
    print(f"   paciente A, 'M. SILVA'        -> {g.nome_pessoa('M. SILVA', chave='A')}   (mesma pessoa)")
    print(f"   paciente B, 'MARIA DA SILVA'  -> {g.nome_pessoa('MARIA DA SILVA', chave='B')}   (outra pessoa)")

    secao('3. DATAS: o intervalo entre atendimentos e preservado?')
    print()
    from datetime import date
    anterior_o = anterior_n = None
    for d in DATAS_PACIENTE:
        nova = g.data(d, chave='A')
        if anterior_o:
            di_o = (date.fromisoformat(d) - anterior_o).days
            di_n = (date.fromisoformat(nova) - anterior_n).days
            marca = 'OK' if di_o == di_n else '!! DIFERE'
            print(f'   {d} -> {nova}   (+{di_o}d no original, +{di_n}d no surrogate)  {marca}')
        else:
            print(f'   {d} -> {nova}')
        anterior_o, anterior_n = date.fromisoformat(d), date.fromisoformat(nova)
    print()
    print(f"   outro paciente: 2025-01-10 -> {g.data('2025-01-10', chave='B')}  (deslocamento proprio)")

    secao('4. INSTITUICOES: a morfologia bate com a rede do ES?')
    print()
    for original in INSTITUICOES:
        print(f'   {original:<36} -> {g.instituicao(original, chave=original)}')

    secao('5. ENDERECOS: o tipo de logradouro e mantido?')
    print()
    for original in ENDERECOS:
        print(f'   {original:<30} -> {g.endereco(original, chave=original)}')

    secao('6. IDENTIFICADORES: formato e quantidade de digitos')
    print()
    for tipo, valor in ESTRUTURADOS:
        saida = g.gerar(tipo, valor, chave='A')
        d_in = len(re.sub(r'\D', '', valor))
        d_out = len(re.sub(r'\D', '', saida))
        marca = 'OK' if d_in == d_out else '!! DIFERE'
        print(f'   {tipo:<10} {valor:<26} -> {saida:<26} ({d_in}d -> {d_out}d) {marca}')

    secao('7. ESTATISTICAS')
    print()
    for chave, valor in g.estatisticas().items():
        print(f'   {chave:<22} {valor}')

    print()
    print('=' * 72)
    print('O QUE OLHAR (julgamento de dominio, que so voce pode fazer):')
    print()
    print('  * Os nomes da secao 1 passariam por nomes reais de pacientes do ES?')
    print('  * As instituicoes da secao 4 seguem a nomenclatura da rede estadual?')
    print('  * Algum surrogate "denuncia" que e sintetico?')
    print()
    print('Rode com --seed 2, --seed 3 para ver outras versoes do mesmo corpus,')
    print('e com --modo placeholder ou --modo celebridade para ver a contraprova.')
    print('=' * 72)


if __name__ == '__main__':
    main()
