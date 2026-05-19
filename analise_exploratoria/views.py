import json, io, csv
from django.shortcuts import render
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse
from .services.exploracao import (
    ler_prescricoes,
    ler_pareceres,
    contar_registros,
    contar_pacientes_unicos,
    periodo_coberto,
    top_especialidades,
    contar_hospitais,
    calcular_distribuicao_tokens,
    calcular_distribuicao_caracteres,
    calcular_distribuicao_sentencas,
    calcular_proporcao_tipos,
    calcular_histograma_tokens,
)
from .models import ExecucaoAnalise

def index(request):
    contexto = {}

    if request.method == 'POST':
        arquivo_prescricoes = request.FILES.get('arquivo_prescricoes')
        arquivo_pareceres = request.FILES.get('arquivo_pareceres')

        df_prescricoes = ler_prescricoes(arquivo_prescricoes)
        df_pareceres = ler_pareceres(arquivo_pareceres)

        registros = contar_registros(df_prescricoes, df_pareceres)
        pacientes = contar_pacientes_unicos(df_prescricoes, df_pareceres)
        periodo = periodo_coberto(df_prescricoes, df_pareceres)
        especialidades = top_especialidades(df_prescricoes, df_pareceres)

        # Prepara dados para Chart.js (0.5.3)
        especialidades_labels = especialidades.index.tolist()
        especialidades_valores = [int(v) for v in especialidades.values]        

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

        # Salva no banco
        execucao = ExecucaoAnalise.objects.create(
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
            especialidades_json=dict(zip(especialidades_labels, especialidades_valores)),
        )

        contexto['registros'] = registros
        contexto['pacientes_unicos'] = pacientes
        contexto['periodo'] = periodo
        contexto['especialidades'] = especialidades
        contexto['especialidades_labels'] = especialidades_labels
        contexto['especialidades_valores'] = especialidades_valores        
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
    execucoes = ExecucaoAnalise.objects.all()
    return render(request, 'analise_exploratoria/execucoes_lista.html', {'execucoes': execucoes})

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
            'top_especialidades': e.especialidades_json,
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