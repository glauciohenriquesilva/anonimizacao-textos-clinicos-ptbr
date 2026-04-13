"""
Views do app Results — Comparativo de resultados entre modelos.
"""
import json
from django.shortcuts import render

from webapp_django.apps.experiments.models import Experiment, ExperimentResult


def results_dashboard(request):
    """
    Dashboard de resultados: tabela comparativa de F1 por modelo.
    """
    results = (
        ExperimentResult.objects
        .select_related("experiment")
        .filter(f1_overall__isnull=False)
        .order_by("-f1_overall")
    )
    return render(request, "results/dashboard.html", {"results": results})


def compare_models(request):
    """
    Comparação visual de modelos: gráfico de barras F1 × modelo.
    Os dados são passados como JSON para Chart.js no template.
    """
    results = (
        ExperimentResult.objects
        .select_related("experiment")
        .filter(f1_overall__isnull=False)
    )

    chart_data = {
        "labels": [r.experiment.get_model_name_display() for r in results],
        "f1":     [round(r.f1_overall, 4) for r in results],
        "delta_f1": [round(r.delta_f1, 4) if r.delta_f1 is not None else None for r in results],
        "phi_coverage": [round(r.phi_coverage, 4) if r.phi_coverage is not None else None for r in results],
    }

    return render(request, "results/compare.html", {
        "results": results,
        "chart_data_json": json.dumps(chart_data),
    })


def export_results(request):
    """
    Exporta resultados como CSV para a dissertação.
    """
    import csv
    from django.http import HttpResponse

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="resultados_experimentos.csv"'
    response.write("\ufeff")  # BOM UTF-8 para Excel

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
            exp.n_train,
            exp.n_test,
            r.precision_overall,
            r.recall_overall,
            r.f1_overall,
            r.delta_f1,
            r.phi_coverage,
            r.phi_precision_anon,
            r.levenshtein_ratio,
            r.cohen_kappa,
        ])

    return response
