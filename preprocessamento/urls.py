from django.urls import path
from . import views

app_name = 'preprocessamento'

urlpatterns = [
    path('', views.index, name='index'),
    path('baixar/<str:formato>/', views.baixar_arquivo, name='baixar_arquivo'),
]