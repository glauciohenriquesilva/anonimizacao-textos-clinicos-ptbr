from anotador.models import Sentenca, AnotacaoToken, AdjudicacaoToken


# Início - A) Anotador Integrado - A.3) Controle de Qualidade - A.3.3) Identificar Discordâncias
def identificar_discordancias(sessao):
    # Compara as anotações dos dois anotadores token a token.
    # Retorna lista de dicts com as sentenças e posições onde há discordância.

    sentencas = Sentenca.objects.filter(sessao=sessao).order_by('ordem')
    anotadores = list(
        AnotacaoToken.objects.filter(
            sentenca__sessao=sessao,
        ).values_list('anotador_id', flat=True).distinct()
    )

    if len(anotadores) < 2:
        return []

    discordancias = []
    for sentenca in sentencas:
        n_tokens = len(sentenca.tokens)
        anot1 = {a.posicao: a.label for a in AnotacaoToken.objects.filter(
            sentenca=sentenca, anotador_id=anotadores[0])}
        anot2 = {a.posicao: a.label for a in AnotacaoToken.objects.filter(
            sentenca=sentenca, anotador_id=anotadores[1])}

        posicoes_discordantes = []
        for pos in range(n_tokens):
            l1 = anot1.get(pos, 'O')
            l2 = anot2.get(pos, 'O')
            if l1 != l2:
                posicoes_discordantes.append({
                    'posicao':  pos,
                    'token':    sentenca.tokens[pos],
                    'label_a1': l1,
                    'label_a2': l2,
                })

        if posicoes_discordantes:
            discordancias.append({
                'sentenca': sentenca,
                'posicoes': posicoes_discordantes,
            })

    return discordancias
# Fim - A) Anotador Integrado - A.3) Controle de Qualidade - A.3.3) Identificar Discordâncias


# Início - A) Anotador Integrado - A.3) Controle de Qualidade - A.3.4) Adjudicação
def salvar_adjudicacao(sentenca, labels_adjudicadas):
    # Salva a label final adjudicada para cada token de uma sentença.
    # labels_adjudicadas: lista de labels na ordem dos tokens.
    # Substitui adjudicações anteriores se existirem.

    for pos, label in enumerate(labels_adjudicadas):
        AdjudicacaoToken.objects.update_or_create(
            sentenca=sentenca,
            posicao=pos,
            defaults={'label': label},
        )
# Fim - A) Anotador Integrado - A.3) Controle de Qualidade - A.3.4) Adjudicação


# Início - A) Anotador Integrado - A.4) Exportação - A.4.1) Gerar CoNLL Final
def exportar_conll_final(sessao, caminho_saida):
    # Gera o arquivo CoNLL final usando as labels adjudicadas.
    # Para sentenças sem discordância, usa a label do anotador 1.
    # Para sentenças com discordância, usa a adjudicação (prioridade máxima).
    # Persiste o caminho e totais em ExecucaoAnotacao para rastreabilidade.

    sentencas = Sentenca.objects.filter(sessao=sessao).order_by('ordem')
    anotadores = list(
        AnotacaoToken.objects.filter(
            sentenca__sessao=sessao,
        ).values_list('anotador_id', flat=True).distinct()
    )

    total_sentencas = 0
    total_tokens    = 0

    with open(caminho_saida, 'w', encoding='utf-8') as f:
        for sentenca in sentencas:
            n_tokens = len(sentenca.tokens)

            # Verifica se há adjudicação para esta sentença
            adjudicacoes = {
                a.posicao: a.label
                for a in AdjudicacaoToken.objects.filter(sentenca=sentenca)
            }

            # Usa anotador 1 como base se não houver adjudicação
            anot1 = {
                a.posicao: a.label
                for a in AnotacaoToken.objects.filter(
                    sentenca=sentenca,
                    anotador_id=anotadores[0] if anotadores else None,
                )
            }

            for pos in range(n_tokens):
                token = sentenca.tokens[pos]
                # Adjudicação tem prioridade sobre anotador 1
                label = adjudicacoes.get(pos, anot1.get(pos, 'O'))
                f.write(f'{token}\t{label}\n')
                total_tokens += 1

            f.write('\n')  # linha em branco entre sentenças (padrão CoNLL)
            total_sentencas += 1

    # Persiste o caminho do CoNLL e os totais no banco — rastreabilidade do experimento
    if sessao.experimento:
        anot = getattr(sessao.experimento, 'anotacao', None)
        if anot:
            anot.total_sentencas_anotadas = total_sentencas
            anot.caminho_conll_anotado    = caminho_saida
            anot.save()

    return {'total_sentencas': total_sentencas, 'total_tokens': total_tokens}
# Fim - A) Anotador Integrado - A.4) Exportação - A.4.1) Gerar CoNLL Final