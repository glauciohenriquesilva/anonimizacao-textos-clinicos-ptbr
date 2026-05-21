from django.urls import path
from . import views

app_name = 'ner'

urlpatterns = [
    path('anotacao/', views.anotacao, name='anotacao'),
    path('divisao/', views.divisao, name='divisao'),
    path('treinamento/', views.treinamento, name='treinamento'),
    path('avaliacao/', views.avaliacao, name='avaliacao'),
    path('baixar/<str:arquivo>/', views.baixar_arquivo, name='baixar_arquivo'),
]