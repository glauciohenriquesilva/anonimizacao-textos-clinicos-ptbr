from django.urls import path
from . import views

app_name = 'anonimizacao'

urlpatterns = [
    path('', views.index, name='index'),
    path('resultados/', views.resultados, name='resultados'),
    path('baixar/<str:arquivo>/', views.baixar_arquivo, name='baixar_arquivo'),
]