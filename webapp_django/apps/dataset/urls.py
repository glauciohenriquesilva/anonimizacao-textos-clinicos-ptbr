from django.urls import path
from . import views

app_name = "dataset"

urlpatterns = [
    path("",             views.document_list,   name="list"),
    path("importar/",    views.import_csv,       name="import"),
    path("<int:pk>/",    views.document_detail,  name="detail"),
    path("explorar/",    views.exploratory_view, name="exploratory"),
]
