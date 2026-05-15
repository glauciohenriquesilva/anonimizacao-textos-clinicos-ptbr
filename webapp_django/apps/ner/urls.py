from django.urls import path
from . import views

app_name = "ner"

urlpatterns = [
    path("",              views.anotacao,    name="anotacao"),
    path("divisao/",      views.divisao,     name="divisao"),
    path("treinamento/",  views.treinamento, name="treinamento"),
    path("avaliacao/",    views.avaliacao,   name="avaliacao"),

    # Rotas de experimentos (CRUD + execução)
    path("treinamento/novo/",         views.experimento_criar,  name="experimento_criar"),
    path("treinamento/<int:pk>/",     views.experimento_detalhe, name="experimento_detalhe"),
    path("treinamento/<int:pk>/run/", views.experimento_rodar,   name="experimento_rodar"),
]
