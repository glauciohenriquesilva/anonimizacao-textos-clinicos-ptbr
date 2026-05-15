"""
Views — NER: Reconhecimento de Entidades Nomeadas (etapa 2 do pipeline)

Subseções:
    2.1  anotacao    — Gold Standard (etapa manual via Doccano)
    2.2  divisao     — Divisão Treino/Dev/Teste (Iterative Stratification)
    2.3  treinamento — Treinamento dos 5 modelos (CRF local + BERT no Colab)
    2.4  avaliacao   — Avaliação NER — Dimensão T do TILD (seqeval)
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages

from .models import Experiment, ExperimentResult
from src.ner.models import MODEL_REGISTRY


def anotacao(request):
    """Anotação Gold Standard — configuração do Doccano e kappa inter-anotadores."""
    context = {
        "section": "ner",
        "subsection": "anotacao",
    }
    return render(request, "ner/anotacao.html", context)


def divisao(request):
    """Divisão Treino/Dev/Teste via Iterative Stratification (70/15/15)."""
    context = {
        "section": "ner",
        "subsection": "divisao",
    }
    return render(request, "ner/divisao.html", context)


def treinamento(request):
    """Lista experimentos de treinamento NER (CRF local + BERT via Colab)."""
    experiments = Experiment.objects.select_related("result").order_by("-created_at")
    context = {
        "section": "ner",
        "subsection": "treinamento",
        "experiments": experiments,
        "model_choices": Experiment.MODEL_CHOICES,
    }
    return render(request, "ner/treinamento.html", context)


def avaliacao(request):
    """Avaliação NER: P/R/F1 entity-level (seqeval), Dimensão T do TILD."""
    results = (
        ExperimentResult.objects
        .select_related("experiment")
        .filter(f1_overall__isnull=False)
        .order_by("-f1_overall")
    )
    context = {
        "section": "ner",
        "subsection": "avaliacao",
        "results": results,
    }
    return render(request, "ner/avaliacao.html", context)


# ── CRUD de Experimentos ───────────────────────────────────────────────────────

def experimento_criar(request):
    """Formulário de criação de novo experimento NER."""
    if request.method == "GET":
        return render(request, "ner/experimento_form.html", {
            "section": "ner",
            "subsection": "treinamento",
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
        return redirect("ner:experimento_detalhe", pk=exp.pk)


def experimento_detalhe(request, pk: int):
    """Detalhe de um experimento: configuração e resultados."""
    exp = get_object_or_404(Experiment.objects.select_related("result"), pk=pk)
    model_config = MODEL_REGISTRY.get(exp.model_name)
    return render(request, "ner/experimento_detalhe.html", {
        "section": "ner",
        "subsection": "treinamento",
        "experiment": exp,
        "model_config": model_config,
    })


def experimento_rodar(request, pk: int):
    """Inicia experimento CRF localmente. BERT: usar notebooks Colab."""
    exp = get_object_or_404(Experiment, pk=pk)

    if exp.model_name != "crf":
        messages.warning(
            request,
            f"O modelo {exp.get_model_name_display()} requer GPU. "
            "Execute o notebook Colab correspondente e importe os resultados."
        )
        return redirect("ner:experimento_detalhe", pk=pk)

    if exp.status not in ("pending", "failed"):
        messages.error(request, "Este experimento já foi executado.")
        return redirect("ner:experimento_detalhe", pk=pk)

    messages.info(request, "Execução de CRF via interface ainda não implementada. "
                           "Use: python src/ner/trainer.py --model crf ...")
    return redirect("ner:experimento_detalhe", pk=pk)
