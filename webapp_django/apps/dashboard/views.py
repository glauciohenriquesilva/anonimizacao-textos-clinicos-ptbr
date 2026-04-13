"""
Views do Dashboard — Visão geral do projeto.
"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required


def index(request):
    """
    Página inicial: estatísticas gerais do dataset e status dos experimentos.
    """
    context = {}

    # Lazy import para evitar erros se banco não estiver configurado
    try:
        from webapp_django.apps.dataset.models import ClinicalDocument, AnnotatedSentence
        from webapp_django.apps.experiments.models import Experiment

        context.update({
            "n_docs_total":       ClinicalDocument.objects.count(),
            "n_docs_prescricoes": ClinicalDocument.objects.filter(doc_type="prescricao").count(),
            "n_docs_pareceres":   ClinicalDocument.objects.filter(doc_type="parecer").count(),
            "n_annotated":        AnnotatedSentence.objects.count(),
            "n_experiments":      Experiment.objects.count(),
            "n_exp_completed":    Experiment.objects.filter(status="completed").count(),
            "n_exp_running":      Experiment.objects.filter(status="running").count(),
        })

        # Últimos experimentos
        context["recent_experiments"] = (
            Experiment.objects.select_related("result")
            .order_by("-created_at")[:5]
        )

    except Exception:
        pass  # banco não configurado ainda

    return render(request, "dashboard/index.html", context)
