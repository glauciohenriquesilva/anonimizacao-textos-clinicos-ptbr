# -*- coding: utf-8 -*-
# Auditoria (SOMENTE LEITURA) para o Task #25 -- regeneracao do corpus do Exp 002.
#
# Para cada sentenca ja anotada: rejunta os tokens atuais em texto, roda o pipeline
# de normalizacao atualizado (Padroes 1-12 de corrigir_erros_digitacao + normalizador
# de data de 5 passadas + mascaramento de telefone/CEP/CPF/email), retokeniza, e
# compara com os tokens atuais.
#
# Nao escreve nada no banco -- só mede o tamanho do problema antes de desenhar o
# script de remapeamento (Fase 2).

from collections import Counter
from anotador.models import Sentenca
from preprocessamento.services.preprocessamento import (
    corrigir_erros_digitacao,
    normalizar_datas_no_texto,
    mascarar_datas_horas,
    mascarar_horas,
    mascarar_cpf,
    mascarar_telefone,
    mascarar_cep,
    mascarar_email,
    tokenizar_word_level,
)

def reprocessar(tokens_atuais):
    # Rejunta os tokens com espaco simples -- aproximacao razoavel do texto original,
    # pois toda a contaminacao relevante (Padroes 1-12) fica DENTRO de um unico token
    # (sem espaco), entao rejuntar com espaco entre tokens preserva o padrao a corrigir.
    texto = ' '.join(tokens_atuais)
    texto = corrigir_erros_digitacao(texto)
    texto = normalizar_datas_no_texto(texto)
    texto = mascarar_datas_horas(texto)
    texto = mascarar_horas(texto)
    texto = mascarar_cpf(texto)
    texto = mascarar_telefone(texto)
    texto = mascarar_cep(texto)
    texto = mascarar_email(texto)
    return tokenizar_word_level(texto)


total = 0
identicas = 0
diferentes = 0
diff_tamanho = Counter()  # delta de quantidade de tokens (novo - antigo)
exemplos_diff = []

for s in Sentenca.objects.all().iterator(chunk_size=500):
    total += 1
    tokens_atuais = s.tokens
    tokens_novos = reprocessar(tokens_atuais)

    if tokens_novos == tokens_atuais:
        identicas += 1
    else:
        diferentes += 1
        delta = len(tokens_novos) - len(tokens_atuais)
        diff_tamanho[delta] += 1
        if len(exemplos_diff) < 30:
            exemplos_diff.append((s.id, s.ordem, tokens_atuais, tokens_novos))

print(f'Total de sentencas: {total}')
print(f'Identicas (sem mudanca): {identicas}')
print(f'Diferentes (precisam remapeamento): {diferentes}')
print()
print('Distribuicao do delta de quantidade de tokens (novo - antigo):')
for delta, qtd in sorted(diff_tamanho.items()):
    print(f'  delta={delta:+d}: {qtd} sentencas')
print()
print('=== Amostra de ate 30 sentencas com diferenca ===')
for sid, ordem, antigos, novos in exemplos_diff:
    print(f'--- id={sid} ordem={ordem} ---')
    print(f'  ANTES ({len(antigos)} tok): {antigos}')
    print(f'  DEPOIS ({len(novos)} tok): {novos}')
    print()
