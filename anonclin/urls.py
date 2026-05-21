from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', include('analise_exploratoria.urls')),
    path('preprocessamento/', include('preprocessamento.urls')),
    path('ner/', include('ner.urls')),
    path('anonimizacao/', include('anonimizacao.urls')),
    path('anotador/', include('anotador.urls')),
]