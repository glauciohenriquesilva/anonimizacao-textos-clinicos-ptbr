from django.urls import path
from . import views

app_name = 'analise_exploratoria'

urlpatterns = [
    path('', views.index, name='index'),
    path('execucoes/', views.listar_execucoes, name='listar_execucoes'),
    path('execucoes/<int:id>/editar/', views.editar_execucao, name='editar_execucao'),
    path('execucoes/<int:id>/excluir/', views.excluir_execucao, name='excluir_execucao'),
    path('execucoes/<int:id>/exportar/csv/',  views.exportar_csv,  name='exportar_csv'),
    path('execucoes/<int:id>/exportar/json/', views.exportar_json, name='exportar_json'),
]