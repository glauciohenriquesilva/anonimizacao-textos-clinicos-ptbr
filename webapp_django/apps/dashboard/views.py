"""
Views do Dashboard — Visão geral do projeto.
"""
from django.shortcuts import render


def index(request):
    pipeline_steps = [
        {"number": "0", "label": "Análise Exploratória",  "url_name": "analise_exploratoria:estatisticas"},
        {"number": "1", "label": "Pré-processamento",      "url_name": "preprocessamento:normalizacao"},
        {"number": "2", "label": "NER",                    "url_name": "ner:anotacao"},
        {"number": "3", "label": "Anonimização",           "url_name": "anonimizacao:substituicao"},
    ]

    # Contagens do banco (importação condicional — DB pode não estar acessível)
    n_experiments = 0
    n_exp_completed = 0
    n_exp_running = 0
    recent_experiments = []
    try:
        from webapp_django.apps.ner.models import Experiment
        n_experiments = Experiment.objects.count()
        n_exp_completed = Experiment.objects.filter(status="completed").count()
        n_exp_running = Experiment.objects.filter(status="running").count()
        recent_experiments = (
            Experiment.objects
            .select_related("result")
            .order_by("-created_at")[:5]
        )
    except Exception:
        pass

    context = {
        "pipeline_steps": pipeline_steps,
        "n_experiments": n_experiments,
        "n_exp_completed": n_exp_completed,
        "n_exp_running": n_exp_running,
        "recent_experiments": recent_experiments,
    }
    return render(request, "dashboard/index.html", context)
