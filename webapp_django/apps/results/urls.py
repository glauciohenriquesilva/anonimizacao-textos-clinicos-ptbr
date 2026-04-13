from django.urls import path
from . import views

app_name = "results"

urlpatterns = [
    path("",            views.results_dashboard, name="dashboard"),
    path("comparar/",   views.compare_models,    name="compare"),
    path("exportar/",   views.export_results,    name="export"),
]
