from django.urls import path
from . import views

app_name = 'preprocessamento'

urlpatterns = [
    path('', views.index, name='index'),
    path('baixar/<str:formato>/', views.baixar_arquivo, name='baixar_arquivo'),
    path('extracao-mv/', views.extracao_mv, name='extracao_mv'),
    path('extracao-mv/<int:execucao_id>/', views.extracao_mv_detalhe, name='extracao_mv_detalhe'),
    path('extracao-mv/<int:execucao_id>/status/', views.extracao_mv_status, name='extracao_mv_status'),
]