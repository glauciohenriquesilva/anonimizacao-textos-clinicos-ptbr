from django.urls import path
from . import views

app_name = "resultados"

urlpatterns = [
    path("",          views.index,    name="index"),
    path("comparar/", views.comparar, name="comparar"),
    path("exportar/", views.exportar, name="exportar"),
]
