from django.urls import path
from . import views

app_name = 'anotador'

urlpatterns = [
    # Gestão de sessões
    path('', views.listar_sessoes, name='listar_sessoes'),
    path('nova/', views.nova_sessao, name='nova_sessao'),
    path('<int:sessao_id>/', views.resumo_sessao, name='resumo_sessao'),

    # Anotação
    path('<int:sessao_id>/anotar/', views.anotar, name='anotar'),
    path('<int:sessao_id>/anotar/<int:sentenca_id>/', views.anotar, name='anotar_sentenca'),
    path('<int:sessao_id>/salvar/', views.salvar_anotacao, name='salvar_anotacao'),
    path('<int:sessao_id>/excluir/', views.excluir_sessao, name='excluir_sessao'),

    # Adjudicação
    path('<int:sessao_id>/revisar/', views.revisar, name='revisar'),
    path('<int:sessao_id>/adjudicar/', views.salvar_adjudicacao, name='salvar_adjudicacao'),

    # Exportação
    path('<int:sessao_id>/exportar/', views.exportar, name='exportar'),
    path('<int:sessao_id>/kappa/', views.kappa, name='kappa'),
]