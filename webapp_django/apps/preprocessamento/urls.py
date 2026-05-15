from django.urls import path
from . import views

app_name = "preprocessamento"

urlpatterns = [
    path("",               views.normalizacao, name="normalizacao"),
    path("segmentacao/",   views.segmentacao,  name="segmentacao"),
    path("tokenizacao/",   views.tokenizacao,  name="tokenizacao"),
    path("exportacao/",    views.exportacao,   name="exportacao"),
]
