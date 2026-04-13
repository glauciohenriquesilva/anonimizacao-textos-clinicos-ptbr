"""
Roteamento URL principal do projeto.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path("admin/", admin.site.urls),
    path("",              include("webapp_django.apps.dashboard.urls")),
    path("dataset/",      include("webapp_django.apps.dataset.urls")),
    path("experimentos/", include("webapp_django.apps.experiments.urls")),
    path("anonimizar/",   include("webapp_django.apps.anonymizer.urls")),
    path("resultados/",   include("webapp_django.apps.results.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
