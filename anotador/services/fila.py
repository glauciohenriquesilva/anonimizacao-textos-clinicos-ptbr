import json
from anotador.models import SessaoAnotacao, Sentenca, AnotacaoToken


# Início - A) Anotador Integrado - A.1) Gestão de Sessões - A.1.2) Carregar Corpus JSONL
def carregar_corpus_na_sessao(sessao, caminho_jsonl):
    # Lê o corpus.jsonl gerado pelo pré-processamento e popula a sessão
    # com as sentenças a serem anotadas.
    # Cada linha do JSONL vira um registro Sentenca no banco.

    with open(caminho_jsonl, encoding='utf-8') as f:
        ordem = 0
        for linha in f:
            registro = json.loads(linha)
            Sentenca.objects.create(
                sessao   = sessao,
                doc_id   = registro['doc_id'],
                doc_type = registro['doc_type'],
                ordem    = ordem,
                tokens   = registro['tokens'],
            )
            ordem += 1

    return ordem  # total de sentenças carregadas
# Fim - A) Anotador Integrado - A.1) Gestão de Sessões - A.1.2) Carregar Corpus JSONL


# Início - A) Anotador Integrado - A.2) Anotação - A.2.2) Fila de Sentenças Pendentes
def proxima_sentenca(sessao, anotador):
    # Retorna a próxima sentença da sessão que o anotador ainda não anotou.
    # Uma sentença é considerada anotada quando existe pelo menos um registro
    # AnotacaoToken para aquele anotador naquela sentença.

    sentencas_anotadas = AnotacaoToken.objects.filter(
        sentenca__sessao=sessao,
        anotador=anotador,
    ).values_list('sentenca_id', flat=True).distinct()

    proxima = Sentenca.objects.filter(
        sessao=sessao,
    ).exclude(
        id__in=sentencas_anotadas,
    ).order_by('ordem').first()

    return proxima
# Fim - A) Anotador Integrado - A.2) Anotação - A.2.2) Fila de Sentenças Pendentes


# Início - A) Anotador Integrado - A.1) Gestão de Sessões - A.1.3) Listar Sessões e Progresso
def progresso_anotador(sessao, anotador):
    # Retorna um dict com o progresso do anotador na sessão:
    # total de sentenças, quantas já foram anotadas e o percentual.

    total = Sentenca.objects.filter(sessao=sessao).count()

    anotadas = AnotacaoToken.objects.filter(
        sentenca__sessao=sessao,
        anotador=anotador,
    ).values('sentenca_id').distinct().count()

    return {
        'total':     total,
        'anotadas':  anotadas,
        'pendentes': total - anotadas,
        'pct':       round((anotadas / total * 100), 1) if total > 0 else 0,
    }
# Fim - A) Anotador Integrado - A.1) Gestão de Sessões - A.1.3) Listar Sessões e Progresso


# Início - A) Anotador Integrado - A.3) Controle de Qualidade - A.3.1) Verificar Conclusão
def todos_concluiram(sessao):
    # Verifica se todos os anotadores atribuídos à sessão já anotaram
    # todas as sentenças. Usado para liberar o cálculo do Kappa.

    total_sentencas = Sentenca.objects.filter(sessao=sessao).count()

    # Busca todos os anotadores que participaram da sessão
    anotadores = AnotacaoToken.objects.filter(
        sentenca__sessao=sessao,
    ).values_list('anotador_id', flat=True).distinct()

    for anotador_id in anotadores:
        anotadas = AnotacaoToken.objects.filter(
            sentenca__sessao=sessao,
            anotador_id=anotador_id,
        ).values('sentenca_id').distinct().count()

        if anotadas < total_sentencas:
            return False

    return len(anotadores) >= 2  # precisa de pelo menos 2 anotadores
# Fim - A) Anotador Integrado - A.3) Controle de Qualidade - A.3.1) Verificar Conclusão