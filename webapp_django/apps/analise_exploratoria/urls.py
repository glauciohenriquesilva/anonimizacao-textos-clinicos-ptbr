from django.urls import path
from . import views

app_name = "analise_exploratoria"

urlpatterns = [
    path("",                   views.estatisticas,  name="estatisticas"),
    path("distribuicao/",      views.distribuicao,  name="distribuicao"),
    path("classificacao/",     views.classificacao, name="classificacao"),
    path("saidas/",            views.saidas,        name="saidas"),
]
