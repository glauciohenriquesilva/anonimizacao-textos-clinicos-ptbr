from django.shortcuts import render
from .services.exploracao import (
    ler_prescricoes,
    ler_pareceres,
    contar_registros,
    contar_pacientes_unicos,
    periodo_coberto,
    top_especialidades,
    contar_hospitais,
)

def index(request):
    contexto = {}

    if request.method == 'POST':
        arquivo_prescricoes = request.FILES.get('arquivo_prescricoes')
        arquivo_pareceres = request.FILES.get('arquivo_pareceres')

        df_prescricoes = ler_prescricoes(arquivo_prescricoes)
        df_pareceres = ler_pareceres(arquivo_pareceres)

        contexto['registros'] = contar_registros(df_prescricoes, df_pareceres)
        contexto['pacientes_unicos'] = contar_pacientes_unicos(df_prescricoes, df_pareceres)
        contexto['periodo'] = periodo_coberto(df_prescricoes, df_pareceres)
        contexto['especialidades'] = top_especialidades(df_prescricoes, df_pareceres)
        contexto['hospitais'] = contar_hospitais(df_prescricoes, df_pareceres)

    return render(request, 'analise_exploratoria/index.html', contexto)