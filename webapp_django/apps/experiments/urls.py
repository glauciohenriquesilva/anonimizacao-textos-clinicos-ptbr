from django.urls import path
from . import views

app_name = "experiments"

urlpatterns = [
    path("",              views.experiment_list,   name="list"),
    path("novo/",         views.experiment_create, name="create"),
    path("<int:pk>/",     views.experiment_detail, name="detail"),
    path("<int:pk>/run/", views.experiment_run,    name="run"),
]
