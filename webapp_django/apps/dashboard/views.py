"""
Views do Dashboard — Visão geral do projeto.
"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required


def index(request):
    pipeline_steps = [
        {"number": "0", "label": "Análise Exploratória"},
        {"number": "1", "label": "Pré-processamento"},
        {"number": "2", "label": "NER"},
        {"number": "3", "label": "Anonimização"},
    ]
    context = {
        "pipeline_steps": pipeline_steps,
        # ... resto das stats
    }
    return render(request, "dashboard/index.html", context)
