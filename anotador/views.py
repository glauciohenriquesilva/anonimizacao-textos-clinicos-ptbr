import os
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, FileResponse, Http404
from django.views.decorators.http import require_POST

from .models import SessaoAnotacao, Sentenca, AnotacaoToken, AdjudicacaoToken
from .services.fila import (
    carregar_corpus_na_sessao,
    proxima_sentenca,
    progresso_anotador,
    todos_concluiram,
)
from .services.kappa import calcular_kappa_sessao
from .services.exportador import (
    identificar_discordancias,
    salvar_adjudicacao,
    exportar_conll_final,
)
from analise_exploratoria.models import Experimento

OUTPUTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs', 'anotador')


# Início - A) Anotador Integrado - A.1) Gestão de Sessões - A.1.3) Listar Sessões e Progresso
@login_required
def listar_sessoes(request):
    sessoes = SessaoAnotacao.objects.all()
    # Adiciona progresso do usuário atual em cada sessão
    for sessao in sessoes:
        sessao.progresso = progresso_anotador(sessao, request.user)
    return render(request, 'anotador/sessoes_lista.html', {'sessoes': sessoes})
# Fim - A) Anotador Integrado - A.1) Gestão de Sessões - A.1.3) Listar Sessões e Progresso


# Início - A) Anotador Integrado - A.1) Gestão de Sessões - A.1.1) Criar Sessão de Anotação
@login_required
def nova_sessao(request):
    if request.method == 'POST':
        nome           = request.POST.get('nome')
        descricao      = request.POST.get('descricao', '')
        experimento_id = request.POST.get('experimento_id')
        caminho_jsonl  = request.POST.get('caminho_jsonl')

        experimento = None
        if experimento_id:
            experimento = Experimento.objects.filter(id=experimento_id).first()

        sessao = SessaoAnotacao.objects.create(
            nome=nome,
            descricao=descricao,
            experimento=experimento,
        )

        # Carrega o corpus JSONL na sessão criando os registros Sentenca no banco
        total = carregar_corpus_na_sessao(sessao, caminho_jsonl)
        messages.success(request, f'Sessão criada com {total} sentenças.')
        return redirect('anotador:resumo_sessao', sessao_id=sessao.id)

    experimentos = Experimento.objects.all()
    return render(request, 'anotador/sessao_form.html', {'experimentos': experimentos})
# Fim - A) Anotador Integrado - A.1) Gestão de Sessões - A.1.1) Criar Sessão de Anotação


# Início - A) Anotador Integrado - A.1) Gestão de Sessões - A.1.3) Listar Sessões e Progresso
@login_required
def resumo_sessao(request, sessao_id):
    sessao     = get_object_or_404(SessaoAnotacao, id=sessao_id)
    progresso  = progresso_anotador(sessao, request.user)
    concluiram = todos_concluiram(sessao)
    return render(request, 'anotador/resumo.html', {
        'sessao':     sessao,
        'progresso':  progresso,
        'concluiram': concluiram,
    })
# Fim - A) Anotador Integrado - A.1) Gestão de Sessões - A.1.3) Listar Sessões e Progresso


# Início - A) Anotador Integrado - A.2) Anotação - A.2.3) Interface de Anotação
@login_required
def anotar(request, sessao_id):
    sessao   = get_object_or_404(SessaoAnotacao, id=sessao_id)
    sentenca = proxima_sentenca(sessao, request.user)

    if not sentenca:
        messages.success(request, 'Você concluiu todas as sentenças desta sessão.')
        return redirect('anotador:resumo_sessao', sessao_id=sessao_id)

    progresso = progresso_anotador(sessao, request.user)

    # Labels disponíveis para anotação (extraídas das choices do modelo)
    labels = [l[0] for l in AnotacaoToken.LABELS]

    return render(request, 'anotador/anotar.html', {
        'sessao':    sessao,
        'sentenca':  sentenca,
        'progresso': progresso,
        'labels':    labels,
    })
# Fim - A) Anotador Integrado - A.2) Anotação - A.2.3) Interface de Anotação


# Início - A) Anotador Integrado - A.2) Anotação - A.2.4) Salvar Anotação
@login_required
@require_POST
def salvar_anotacao(request, sessao_id):
    import json
    sessao   = get_object_or_404(SessaoAnotacao, id=sessao_id)
    dados    = json.loads(request.body)
    sentenca = get_object_or_404(Sentenca, id=dados['sentenca_id'], sessao=sessao)
    labels   = dados['labels']  # lista de labels alinhada com os tokens

    # Salva ou atualiza cada label por posição via AJAX — sem reload de página
    for pos, label in enumerate(labels):
        AnotacaoToken.objects.update_or_create(
            sentenca=sentenca,
            anotador=request.user,
            posicao=pos,
            defaults={'label': label},
        )

    return JsonResponse({'status': 'ok'})
# Fim - A) Anotador Integrado - A.2) Anotação - A.2.4) Salvar Anotação


# Início - A) Anotador Integrado - A.3) Controle de Qualidade - A.3.3) Identificar Discordâncias
@login_required
def revisar(request, sessao_id):
    sessao        = get_object_or_404(SessaoAnotacao, id=sessao_id)
    discordancias = identificar_discordancias(sessao)
    return render(request, 'anotador/revisar.html', {
        'sessao':        sessao,
        'discordancias': discordancias,
    })
# Fim - A) Anotador Integrado - A.3) Controle de Qualidade - A.3.3) Identificar Discordâncias


# Início - A) Anotador Integrado - A.3) Controle de Qualidade - A.3.4) Adjudicação
@login_required
@require_POST
def salvar_adjudicacao(request, sessao_id):
    import json
    sessao   = get_object_or_404(SessaoAnotacao, id=sessao_id)
    dados    = json.loads(request.body)
    sentenca = get_object_or_404(Sentenca, id=dados['sentenca_id'], sessao=sessao)
    salvar_adjudicacao(sentenca, dados['labels'])
    return JsonResponse({'status': 'ok'})
# Fim - A) Anotador Integrado - A.3) Controle de Qualidade - A.3.4) Adjudicação


# Início - A) Anotador Integrado - A.3) Controle de Qualidade - A.3.2) Calcular Cohen's Kappa
@login_required
def kappa(request, sessao_id):
    sessao    = get_object_or_404(SessaoAnotacao, id=sessao_id)
    resultado = calcular_kappa_sessao(sessao)
    return render(request, 'anotador/kappa.html', {
        'sessao':    sessao,
        'resultado': resultado,
    })
# Fim - A) Anotador Integrado - A.3) Controle de Qualidade - A.3.2) Calcular Cohen's Kappa


# Início - A) Anotador Integrado - A.4) Exportação - A.4.1) Gerar CoNLL Final
@login_required
def exportar(request, sessao_id):
    sessao = get_object_or_404(SessaoAnotacao, id=sessao_id)
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    caminho = os.path.join(OUTPUTS_DIR, f'corpus_anotado_sessao_{sessao_id}.conll')
    resultado = exportar_conll_final(sessao, caminho)
    return FileResponse(
        open(caminho, 'rb'),
        as_attachment=True,
        filename=f'corpus_anotado_sessao_{sessao_id}.conll',
    )
# Fim - A) Anotador Integrado - A.4) Exportação - A.4.1) Gerar CoNLL Final