"""
Roteamento URL principal do projeto — TextCleanMed
====================================================
Estrutura espelhada no menu lateral da aplicação:

    /                        → dashboard
    /dataset/                → DataSet
    /analise-exploratoria/   → Análise Exploratória (submenus)
    /preprocessamento/       → Pré-processamento (submenus)
    /ner/                    → NER (submenus + experimentos)
    /anonimizacao/           → Anonimização (submenus + demo)
    /resultados/             → Resultados (tabela TILD + gráficos)
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path("admin/", admin.site.urls),

    # Dashboard
    path("", include("webapp_django.apps.dashboard.urls")),

    # DataSet
    path("dataset/", include("webapp_django.apps.dataset.urls")),

    # 0) Análise Exploratória
    path("analise-exploratoria/", include("webapp_django.apps.analise_exploratoria.urls")),

    # 1) Pré-processamento
    path("preprocessamento/", include("webapp_django.apps.preprocessamento.urls")),

    # 2) NER
    path("ner/", include("webapp_django.apps.ner.urls")),

    # 3) Anonimização
    path("anonimizacao/", include("webapp_django.apps.anonimizacao.urls")),

    # Resultados
    path("resultados/", include("webapp_django.apps.resultados.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
