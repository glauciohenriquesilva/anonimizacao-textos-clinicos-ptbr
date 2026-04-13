"""
Views do app Experiments — Criação e acompanhamento de experimentos NER.
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone

from .models import Experiment, ExperimentResult
from src.ner.models import MODEL_REGISTRY


def experiment_list(request):
    """Lista todos os experimentos com status e F1."""
    experiments = Experiment.objects.select_related("result").order_by("-created_at")
    return render(request, "experiments/list.html", {
        "experiments": experiments,
        "model_choices": Experiment.MODEL_CHOICES,
    })


def experiment_detail(request, pk: int):
    """Detalhe de um experimento: configuração e resultados."""
    exp = get_object_or_404(Experiment.objects.select_related("result"), pk=pk)
    model_config = MODEL_REGISTRY.get(exp.model_name)
    return render(request, "experiments/detail.html", {
        "experiment": exp,
        "model_config": model_config,
    })


def experiment_create(request):
    """Formulário de criação de novo experimento."""
    if request.method == "GET":
        return render(request, "experiments/create.html", {
            "model_choices": Experiment.MODEL_CHOICES,
            "split_choices": Experiment.SPLIT_STRATEGY_CHOICES,
        })

    if request.method == "POST":
        exp = Experiment.objects.create(
            name           = request.POST.get("name", "Experimento"),
            description    = request.POST.get("description", ""),
            model_name     = request.POST.get("model_name", "crf"),
            split_strategy = request.POST.get("split_strategy", "iterative_stratified"),
            train_ratio    = float(request.POST.get("train_ratio", 0.70)),
            dev_ratio      = float(request.POST.get("dev_ratio", 0.15)),
            test_ratio     = float(request.POST.get("test_ratio", 0.15)),
            max_length     = int(request.POST.get("max_length", 512)),
            batch_size     = int(request.POST.get("batch_size", 16)),
            learning_rate  = float(request.POST.get("learning_rate", 2e-5)),
            num_epochs     = int(request.POST.get("num_epochs", 10)),
            random_seed    = int(request.POST.get("random_seed", 42)),
            only_phi_labels = "only_phi" in request.POST,
        )
        messages.success(request, f"Experimento '{exp.name}' criado.")
        return redirect("experiments:detail", pk=exp.pk)


def experiment_run(request, pk: int):
    """
    Inicia o experimento (apenas CRF pode rodar localmente).
    Modelos BERT são executados nos notebooks Colab.
    """
    exp = get_object_or_404(Experiment, pk=pk)

    if exp.model_name != "crf":
        messages.warning(
            request,
            f"O modelo {exp.get_model_name_display()} requer GPU. "
            "Execute o notebook Colab correspondente e importe os resultados."
        )
        return redirect("experiments:detail", pk=pk)

    if exp.status not in ("pending", "failed"):
        messages.error(request, "Este experimento já foi executado.")
        return redirect("experiments:detail", pk=pk)

    # TODO: implementar execução assíncrona (Celery ou background thread)
    messages.info(request, "Execução de CRF ainda não implementada via interface. "
                           "Use: python src/ner/trainer.py --model crf ...")
    return redirect("experiments:detail", pk=pk)
