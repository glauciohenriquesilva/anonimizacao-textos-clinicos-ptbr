import json, io, csv
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse
from .services.exploracao import (
    ler_prescricoes,
    ler_pareceres,
    contar_registros,
    contar_pacientes_unicos,
    periodo_coberto,
    contar_hospitais,
    calcular_distribuicao_tokens,
    calcular_distribuicao_caracteres,
    calcular_distribuicao_sentencas,
    calcular_proporcao_tipos,
    calcular_histograma_tokens,
)
from .models import ExecucaoAnalise, Experimento
import plotly.graph_objects as go
from plotly.subplots import make_subplots

def index(request):
    contexto = {}

    if request.method == 'POST':
        arquivo_prescricoes = request.FILES.get('arquivo_prescricoes')
        arquivo_pareceres   = request.FILES.get('arquivo_pareceres')
        # Usa experimento ativo da sessão
        exp_id      = request.session.get('experimento_ativo_id')
        experimento = Experimento.objects.filter(pk=exp_id).first() if exp_id else None

        df_prescricoes = ler_prescricoes(arquivo_prescricoes)
        df_pareceres = ler_pareceres(arquivo_pareceres)

        registros = contar_registros(df_prescricoes, df_pareceres)
        pacientes = contar_pacientes_unicos(df_prescricoes, df_pareceres)
        periodo = periodo_coberto(df_prescricoes, df_pareceres)
        hospitais = contar_hospitais(df_prescricoes, df_pareceres)
        tokens_presc = calcular_distribuicao_tokens(df_prescricoes, 'ds_evolucao')
        tokens_par = calcular_distribuicao_tokens(df_pareceres, 'ds_parecer')
        caracteres_presc = calcular_distribuicao_caracteres(df_prescricoes, 'ds_evolucao')
        caracteres_par = calcular_distribuicao_caracteres(df_pareceres, 'ds_parecer')
        sentencas_presc = calcular_distribuicao_sentencas(df_prescricoes, 'ds_evolucao')
        sentencas_par = calcular_distribuicao_sentencas(df_pareceres, 'ds_parecer')
        tipos_presc = calcular_proporcao_tipos(df_prescricoes, 'ds_evolucao')
        tipos_par = calcular_proporcao_tipos(df_pareceres, 'ds_parecer')
        histograma_presc = calcular_histograma_tokens(df_prescricoes, 'ds_evolucao')
        histograma_par   = calcular_histograma_tokens(df_pareceres, 'ds_parecer')

        # Salva no banco — update_or_create para suportar reexecução sem IntegrityError
        execucao, _ = ExecucaoAnalise.objects.update_or_create(
            experimento=experimento,
            defaults=dict(
                total_registros=registros['total'],
                total_prescricoes=registros['prescricoes'],
                total_pareceres=registros['pareceres'],
                pacientes_unicos=pacientes,
                periodo_inicio=periodo['inicio'],
                periodo_fim=periodo['fim'],
                total_hospitais=hospitais,
                tokens_presc_min=tokens_presc['min'],
                tokens_presc_media=tokens_presc['media'],
                tokens_presc_mediana=tokens_presc['mediana'],
                tokens_presc_max=tokens_presc['max'],
                tokens_presc_p25=tokens_presc['p25'],
                tokens_presc_p75=tokens_presc['p75'],
                tokens_par_min=tokens_par['min'],
                tokens_par_media=tokens_par['media'],
                tokens_par_mediana=tokens_par['mediana'],
                tokens_par_max=tokens_par['max'],
                tokens_par_p25=tokens_par['p25'],
                tokens_par_p75=tokens_par['p75'],
                presc_texto_livre=tipos_presc['texto_livre'],
                presc_template=tipos_presc['template_estruturado'],
                presc_pct_texto_livre=tipos_presc['pct_texto_livre'],
                presc_pct_template=tipos_presc['pct_template'],
                par_texto_livre=tipos_par['texto_livre'],
                par_template=tipos_par['template_estruturado'],
                par_pct_texto_livre=tipos_par['pct_texto_livre'],
                par_pct_template=tipos_par['pct_template'],
            ),
        )

        contexto['registros'] = registros
        contexto['pacientes_unicos'] = pacientes
        contexto['periodo'] = periodo
        contexto['hospitais'] = hospitais
        contexto['tokens_prescricoes'] = tokens_presc
        contexto['tokens_pareceres'] = tokens_par
        contexto['caracteres_prescricoes'] = caracteres_presc
        contexto['caracteres_pareceres'] = caracteres_par
        contexto['sentencas_prescricoes'] = sentencas_presc
        contexto['sentencas_pareceres'] = sentencas_par
        contexto['tipos_prescricoes'] = tipos_presc
        contexto['tipos_pareceres'] = tipos_par
        contexto['execucao_id'] = execucao.id
        contexto['histograma_prescricoes'] = histograma_presc
        contexto['histograma_pareceres'] = histograma_par        

    return render(request, 'analise_exploratoria/index.html', contexto)

def listar_execucoes(request):
    exp_id = request.session.get('experimento_ativo_id')
    if exp_id:
        execucoes = ExecucaoAnalise.objects.filter(experimento_id=exp_id)
    else:
        execucoes = ExecucaoAnalise.objects.all()
    return render(request, 'analise_exploratoria/execucoes_lista.html', {'execucoes': execucoes})

def ver_execucao_analise(request, id):
    execucao = get_object_or_404(ExecucaoAnalise, id=id)
    return render(request, 'analise_exploratoria/execucao_detalhe.html', {'execucao': execucao})

def editar_execucao(request, id):
    execucao = get_object_or_404(ExecucaoAnalise, id=id)

    if request.method == 'POST':
        execucao.obs = request.POST.get('obs', '')
        execucao.save()
        messages.success(request, 'Observação salva com sucesso.')
        return redirect('analise_exploratoria:listar_execucoes')

    return render(request, 'analise_exploratoria/execucao_editar.html', {'execucao': execucao})

def excluir_execucao(request, id):
    execucao = get_object_or_404(ExecucaoAnalise, id=id)

    if request.method == 'POST':
        execucao.delete()
        messages.success(request, 'Execução excluída com sucesso.')
        return redirect('analise_exploratoria:listar_execucoes')

    return render(request, 'analise_exploratoria/execucao_excluir.html', {'execucao': execucao})

# Início - 0) Análise Exploratória - 0.5) Geração de Saídas - 0.5.1) Tabela 1 da dissertação (CSV + Excel)
def exportar_csv(request, id):
    from .services.exploracao import gerar_tabela1
    e = get_object_or_404(ExecucaoAnalise, id=id)

    tokens_presc = {'min': e.tokens_presc_min, 'media': e.tokens_presc_media, 'mediana': e.tokens_presc_mediana, 'max': e.tokens_presc_max, 'p25': e.tokens_presc_p25, 'p75': e.tokens_presc_p75}
    tokens_par   = {'min': e.tokens_par_min,   'media': e.tokens_par_media,   'mediana': e.tokens_par_mediana,   'max': e.tokens_par_max,   'p25': e.tokens_par_p25,   'p75': e.tokens_par_p75}
    tipos_presc  = {'texto_livre': e.presc_texto_livre, 'template_estruturado': e.presc_template, 'pct_texto_livre': e.presc_pct_texto_livre, 'pct_template': e.presc_pct_template}
    tipos_par    = {'texto_livre': e.par_texto_livre,   'template_estruturado': e.par_template,   'pct_texto_livre': e.par_pct_texto_livre,   'pct_template': e.par_pct_template}

    df = gerar_tabela1(
        registros={'total': e.total_registros, 'prescricoes': e.total_prescricoes, 'pareceres': e.total_pareceres},
        pacientes=e.pacientes_unicos,
        periodo={'inicio': e.periodo_inicio, 'fim': e.periodo_fim},
        hospitais=e.total_hospitais,
        tokens_presc=tokens_presc, tokens_par=tokens_par,
        caracteres_presc=tokens_presc, caracteres_par=tokens_par,
        sentencas_presc=tokens_presc, sentencas_par=tokens_par,
        tipos_presc=tipos_presc, tipos_par=tipos_par,
    )

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="tabela1_execucao_{id}.csv"'
    response.write('\ufeff')  # BOM para Excel abrir corretamente com acentos
    df.to_csv(response, index=False, sep=';')
    return response
# Fim - 0) Análise Exploratória - 0.5) Geração de Saídas - 0.5.1) Tabela 1 da dissertação (CSV + Excel)

# Início - 0) Análise Exploratória - 0.5) Geração de Saídas - 0.5.4) Exportação JSON com stats completas
def exportar_json(request, id):
    e = get_object_or_404(ExecucaoAnalise, id=id)

    dados = {
        'execucao_id': e.id,
        'criado_em': e.criado_em.strftime('%d/%m/%Y %H:%M'),
        'estatisticas_descritivas': {
            'total_registros': e.total_registros,
            'total_prescricoes': e.total_prescricoes,
            'total_pareceres': e.total_pareceres,
            'pacientes_unicos': e.pacientes_unicos,
            'periodo_inicio': str(e.periodo_inicio),
            'periodo_fim': str(e.periodo_fim),
            'total_hospitais': e.total_hospitais,
        },
        'distribuicao_tokens': {
            'prescricoes': {'min': e.tokens_presc_min, 'media': e.tokens_presc_media, 'mediana': e.tokens_presc_mediana, 'max': e.tokens_presc_max, 'p25': e.tokens_presc_p25, 'p75': e.tokens_presc_p75},
            'pareceres':   {'min': e.tokens_par_min,   'media': e.tokens_par_media,   'mediana': e.tokens_par_mediana,   'max': e.tokens_par_max,   'p25': e.tokens_par_p25,   'p75': e.tokens_par_p75},
        },
        'tipo_de_texto': {
            'prescricoes': {'texto_livre': e.presc_texto_livre, 'template_estruturado': e.presc_template, 'pct_texto_livre': e.presc_pct_texto_livre, 'pct_template': e.presc_pct_template},
            'pareceres':   {'texto_livre': e.par_texto_livre,   'template_estruturado': e.par_template,   'pct_texto_livre': e.par_pct_texto_livre,   'pct_template': e.par_pct_template},
        },
        'obs': e.obs or '',
    }

    response = HttpResponse(json.dumps(dados, ensure_ascii=False, indent=2), content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename="analise_execucao_{id}.json"'
    return response
# Fim - 0) Análise Exploratória - 0.5) Geração de Saídas - 0.5.4) Exportação JSON com stats completas




# Início - CRUD Experimento
def listar_experimentos(request):
    experimentos = Experimento.objects.all()
    return render(request, 'analise_exploratoria/experimentos_lista.html', {'experimentos': experimentos})


def novo_experimento(request):
    if request.method == 'POST':
        nome      = request.POST.get('nome')
        descricao = request.POST.get('descricao', '')
        obs       = request.POST.get('obs', '')
        exp = Experimento.objects.create(nome=nome, descricao=descricao, obs=obs)
        # Ativa automaticamente o experimento recém-criado na sessão
        request.session['experimento_ativo_id'] = exp.pk
        messages.success(request, f'Experimento "{exp.nome}" criado e definido como ativo.')
        return redirect('analise_exploratoria:index')
    return render(request, 'analise_exploratoria/experimento_form.html', {'acao': 'Novo'})


def detalhe_experimento(request, id):
    exp = get_object_or_404(
        Experimento.objects.prefetch_related(
            'treinamentos__avaliacao',
            'anonimizacoes',
        ).select_related('analise', 'preprocessamento', 'anotacao', 'divisao'),
        id=id,
    )
    return render(request, 'analise_exploratoria/experimento_detalhe.html', {'exp': exp})


def editar_experimento(request, id):
    exp = get_object_or_404(Experimento, id=id)
    if request.method == 'POST':
        exp.nome      = request.POST.get('nome')
        exp.descricao = request.POST.get('descricao', '')
        exp.obs       = request.POST.get('obs', '')
        exp.save()
        messages.success(request, 'Experimento atualizado com sucesso.')
        return redirect('analise_exploratoria:listar_experimentos')
    return render(request, 'analise_exploratoria/experimento_form.html', {'acao': 'Editar', 'exp': exp})


def excluir_experimento(request, id):
    exp = get_object_or_404(Experimento, id=id)
    if request.method == 'POST':
        exp.delete()
        messages.success(request, 'Experimento excluído com sucesso.')
        return redirect('analise_exploratoria:listar_experimentos')
    return render(request, 'analise_exploratoria/experimento_excluir.html', {'exp': exp})
# Fim - CRUD Experimento


# Início - Experimento Ativo (sessão)
def set_experimento_ativo(request):
    """
    Salva o experimento selecionado na sessão Django.
    Redireciona de volta para a página que originou a chamada.
    """
    if request.method == 'POST':
        exp_id = request.POST.get('experimento_id', '').strip()
        if exp_id:
            request.session['experimento_ativo_id'] = int(exp_id)
        else:
            request.session.pop('experimento_ativo_id', None)
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER', '/')
    return redirect(next_url)
# Fim - Experimento Ativo (sessão)


# Início - Dashboard comparativo
def dashboard(request):
    experimentos = Experimento.objects.prefetch_related(
        'treinamentos__avaliacao', 'anotacao', 'divisao', 'anonimizacoes'
    ).all()

    linhas = []
    for exp in experimentos:
        for treinamento in exp.treinamentos.all():
            aval = getattr(treinamento, 'avaliacao', None)
            anon = exp.anonimizacoes.order_by('-criado_em').first()
            anot = getattr(exp, 'anotacao', None)
            div  = getattr(exp, 'divisao', None)
            linhas.append({
                'exp_id':        exp.id,
                'exp_nome':      exp.nome,
                'modelo':        treinamento.nome_modelo,
                'kappa':         anot.kappa if anot else None,
                'total_treino':  div.total_treino if div else None,
                'total_teste':   div.total_teste if div else None,
                'f1_ner':        aval.f1_entity_micro if aval else None,
                'coverage':      anon.coverage if anon else None,
                'precision_anon': anon.precision_anon if anon else None,
                'delta_f1':      anon.delta_f1 if anon else None,
            })

    # Gráfico Plotly — F1 NER por modelo e experimento
    grafico_html = ''
    if linhas:
        modelos   = [l['modelo'] for l in linhas]
        f1_values = [l['f1_ner'] or 0 for l in linhas]
        nomes     = [f"[{l['exp_id']}] {l['exp_nome']}" for l in linhas]

        fig = make_subplots(rows=1, cols=2,
            subplot_titles=('F1 NER por Modelo', 'ΔF1 por Modelo (Utilidade)'))

        fig.add_trace(go.Bar(
            x=modelos, y=f1_values, name='F1 NER',
            text=nomes, textposition='auto',
            marker_color='steelblue',
        ), row=1, col=1)

        delta_values = [l['delta_f1'] or 0 for l in linhas]
        cores = ['green' if v >= 0 else 'red' for v in delta_values]
        fig.add_trace(go.Bar(
            x=modelos, y=delta_values, name='ΔF1',
            marker_color=cores,
        ), row=1, col=2)

        fig.update_layout(height=400, showlegend=False)
        grafico_html = fig.to_html(full_html=False, include_plotlyjs='cdn')

    return render(request, 'analise_exploratoria/dashboard.html', {
        'linhas':       linhas,
        'grafico_html': grafico_html,
    })
# Fim - Dashboard comparativo