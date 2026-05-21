import os
from django.shortcuts import render
from django.http import FileResponse, Http404
from .services.anonimizacao import (
    gerar_tabela_tild,
    exportar_tabela_tild_csv,
    gerar_graficos_tild,
)
from .models import ExecucaoAnonimizacao

OUTPUTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs', 'anonimizacao')


# Início - 3) Anonimização - Interface Django - Executar
def index(request):
    contexto = {}

    if request.method == 'POST':
        os.makedirs(OUTPUTS_DIR, exist_ok=True)
        contexto['em_desenvolvimento'] = True

    return render(request, 'anonimizacao/index.html', contexto)
# Fim - 3) Anonimização - Interface Django - Executar


# Início - 3) Anonimização - Interface Django - Resultados TILD
def resultados(request):
    contexto = {}

    if request.method == 'POST':
        os.makedirs(OUTPUTS_DIR, exist_ok=True)

        # Coleta métricas de todas as execuções de anonimização registradas
        execucoes = ExecucaoAnonimizacao.objects.all().order_by('-criado_em')

        resultados_modelos = {}
        for e in execucoes:
            if e.experimento and e.experimento.treinamentos.exists():
                treinamento = e.experimento.treinamentos.order_by('-criado_em').first()
                avaliacao   = getattr(treinamento, 'avaliacao', None)
                resultados_modelos[treinamento.nome_modelo] = {
                    'f1_ner':          avaliacao.f1_entity_micro if avaliacao else None,
                    'coverage':        e.coverage,
                    'precision_anon':  e.precision_anon,
                    'levenshtein':     e.levenshtein_ratio,
                    'f1_original':     e.f1_downstream_original,
                    'f1_anonimizado':  e.f1_downstream_anonimizado,
                    'delta_f1':        e.delta_f1,
                }

        if resultados_modelos:
            df_tild = gerar_tabela_tild(resultados_modelos)

            # Exporta CSV
            caminho_csv = os.path.join(OUTPUTS_DIR, 'tabela_tild.csv')
            exportar_tabela_tild_csv(df_tild, caminho_csv)

            # Gera gráficos
            gerar_graficos_tild(df_tild, OUTPUTS_DIR)

            contexto['tabela']      = df_tild.to_dict(orient='records')
            contexto['tem_dados']   = True

    return render(request, 'anonimizacao/resultados.html', contexto)
# Fim - 3) Anonimização - Interface Django - Resultados TILD


def baixar_arquivo(request, arquivo):
    permitidos = ['tabela_tild.csv', 'grafico_f1_ner.png', 'grafico_delta_f1.png']
    if arquivo not in permitidos:
        raise Http404
    caminho = os.path.join(OUTPUTS_DIR, arquivo)
    if not os.path.exists(caminho):
        raise Http404
    return FileResponse(open(caminho, 'rb'), as_attachment=True, filename=arquivo)