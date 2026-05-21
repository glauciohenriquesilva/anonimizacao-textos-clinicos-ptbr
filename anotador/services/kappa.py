from anotador.models import Sentenca, AnotacaoToken
from ner.services.anotacao import calcular_kappa


# Início - A) Anotador Integrado - A.3) Controle de Qualidade - A.3.2) Calcular Cohen's Kappa
def extrair_labels_anotadores(sessao):
    # Extrai as labels de todos os anotadores para todas as sentenças da sessão.
    # Retorna um dict {anotador_id → lista plana de labels} para cálculo do Kappa.
    # As listas são alinhadas — mesma posição = mesmo token.

    sentencas = Sentenca.objects.filter(sessao=sessao).order_by('ordem')
    anotadores = AnotacaoToken.objects.filter(
        sentenca__sessao=sessao,
    ).values_list('anotador_id', flat=True).distinct()

    labels_por_anotador = {aid: [] for aid in anotadores}

    for sentenca in sentencas:
        n_tokens = len(sentenca.tokens)
        for anotador_id in anotadores:
            # Busca as anotações deste anotador para esta sentença
            anotacoes = AnotacaoToken.objects.filter(
                sentenca=sentenca,
                anotador_id=anotador_id,
            ).order_by('posicao')

            # Monta lista de labels alinhada com os tokens
            # Se um token não foi anotado, assume 'O'
            anotacoes_dict = {a.posicao: a.label for a in anotacoes}
            for pos in range(n_tokens):
                labels_por_anotador[anotador_id].append(
                    anotacoes_dict.get(pos, 'O')
                )

    return labels_por_anotador
# Fim - A) Anotador Integrado - A.3) Controle de Qualidade - A.3.2) Calcular Cohen's Kappa


# Início - A) Anotador Integrado - A.3) Controle de Qualidade - A.3.2) Calcular Cohen's Kappa
def calcular_kappa_sessao(sessao):
    # Calcula o Cohen's Kappa entre os dois primeiros anotadores da sessão.
    # Retorna o resultado do kappa e as labels usadas no cálculo.

    labels_por_anotador = extrair_labels_anotadores(sessao)
    anotadores = list(labels_por_anotador.keys())

    if len(anotadores) < 2:
        return None  # precisa de pelo menos 2 anotadores

    labels_a1 = labels_por_anotador[anotadores[0]]
    labels_a2 = labels_por_anotador[anotadores[1]]

    resultado = calcular_kappa(labels_a1, labels_a2)

    # Salva o Kappa no registro de anotação do experimento vinculado
    from anotador.models import SessaoAnotacao
    sessao_obj = SessaoAnotacao.objects.get(id=sessao.id)
    if sessao_obj.experimento:
        anot = getattr(sessao_obj.experimento, 'anotacao', None)
        if anot:
            anot.kappa               = resultado['kappa']
            anot.kappa_meta_atingida = resultado['meta_atingida']
            anot.concordancia_obs    = resultado['po']
            anot.concordancia_esp    = resultado['pe']
            anot.total_tokens_kappa  = resultado['total_tokens']
            anot.save()

    return resultado
# Fim - A) Anotador Integrado - A.3) Controle de Qualidade - A.3.2) Calcular Cohen's Kappa