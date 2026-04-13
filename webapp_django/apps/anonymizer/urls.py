from django.urls import path
from . import views

app_name = "anonymizer"

urlpatterns = [
    path("",             views.anonymizer_home,    name="home"),
    path("demo/",        views.anonymize_demo,     name="demo"),
    path("batch/",       views.anonymize_batch,    name="batch"),
]
