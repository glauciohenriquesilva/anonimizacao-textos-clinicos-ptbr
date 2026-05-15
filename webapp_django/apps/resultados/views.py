"""
Views — Resultados (consolidação final do pipeline)

Subseções:
    index    — Tabela TILD comparativa dos 5 modelos
    comparar — Gráficos F1 × modelo e ΔF1 × modelo
    exportar — Download CSV para dissertação
"""
import json
import csv
from django.shortcuts import render
from django.http import HttpResponse

from webapp_django.apps.ner.models import Experiment, ExperimentResult


def index(request):
    """Tabela TILD comparativa: P/R/F1, ΔF1, Coverage, Prec_anon por modelo."""
    results = (
        ExperimentResult.objects
        .select_related("experiment")
        .filter(f1_overall__isnull=False)
        .order_by("-f1_overall")
    )
    context = {
        "section": "resultados",
        "results": results,
    }
    return render(request, "resultados/index.html", context)


def comparar(request):
    """Gráficos comparativos de F1 e ΔF1 por modelo (Chart.js)."""
    results = (
        ExperimentResult.objects
        .select_related("experiment")
        .filter(f1_overall__isnull=False)
    )

    chart_data = {
        "labels":       [r.experiment.get_model_name_display() for r in results],
        "f1":           [round(r.f1_overall, 4) for r in results],
        "delta_f1":     [round(r.delta_f1, 4) if r.delta_f1 is not None else None for r in results],
        "phi_coverage": [round(r.phi_coverage, 4) if r.phi_coverage is not None else None for r in results],
    }

    context = {
        "section": "resultados",
        "results": results,
        "chart_data_json": json.dumps(chart_data),
    }
    return render(request, "resultados/comparar.html", context)


def exportar(request):
    """Exporta resultados como CSV (BOM UTF-8) para abrir no Excel."""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="resultados_tild.csv"'
    response.write("﻿")  # BOM UTF-8

    writer = csv.writer(response)
    writer.writerow([
        "Modelo", "Split", "N_Treino", "N_Teste",
        "Precision", "Recall", "F1",
        "ΔF1", "PHI_Coverage", "PHI_Prec_Anon",
        "Levenshtein_Ratio", "Cohen_Kappa",
    ])

    results = (
        ExperimentResult.objects
        .select_related("experiment")
        .filter(f1_overall__isnull=False)
        .order_by("experiment__model_name")
    )

    for r in results:
        exp = r.experiment
        writer.writerow([
            exp.get_model_name_display(),
            exp.get_split_strategy_display(),
            exp.n_train, exp.n_test,
            r.precision_overall, r.recall_overall, r.f1_overall,
            r.delta_f1, r.phi_coverage, r.phi_precision_anon,
            r.levenshtein_ratio, r.cohen_kappa,
        ])

    return response
