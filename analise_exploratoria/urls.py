from django.urls import path
from . import views

app_name = 'analise_exploratoria'

urlpatterns = [
    # Análise Exploratória
    path('', views.index, name='index'),
    path('execucoes/', views.listar_execucoes, name='listar_execucoes'),
    path('execucoes/<int:id>/editar/', views.editar_execucao, name='editar_execucao'),
    path('execucoes/<int:id>/excluir/', views.excluir_execucao, name='excluir_execucao'),
    path('execucoes/<int:id>/exportar/csv/', views.exportar_csv, name='exportar_csv'),
    path('execucoes/<int:id>/exportar/json/', views.exportar_json, name='exportar_json'),

    # Experimentos
    path('experimentos/', views.listar_experimentos, name='listar_experimentos'),
    path('experimentos/novo/', views.novo_experimento, name='novo_experimento'),
    path('experimentos/<int:id>/', views.detalhe_experimento, name='detalhe_experimento'),
    path('experimentos/<int:id>/editar/', views.editar_experimento, name='editar_experimento'),
    path('experimentos/<int:id>/excluir/', views.excluir_experimento, name='excluir_experimento'),

    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
]