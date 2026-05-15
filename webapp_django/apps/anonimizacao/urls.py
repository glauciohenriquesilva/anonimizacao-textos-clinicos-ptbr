from django.urls import path
from . import views

app_name = "anonimizacao"

urlpatterns = [
    path("",             views.substituicao, name="substituicao"),
    path("privacidade/", views.privacidade,  name="privacidade"),
    path("utilidade/",   views.utilidade,    name="utilidade"),
]
