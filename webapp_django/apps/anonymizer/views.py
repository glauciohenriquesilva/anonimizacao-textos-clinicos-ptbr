"""
Views do app Anonymizer — Demonstração e execução da anonimização.
"""
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.http import JsonResponse

from src.anonymization.substitutor import MarkerSubstitutor


def anonymizer_home(request):
    """Página inicial do módulo de anonimização."""
    return render(request, "anonymizer/home.html")


def anonymize_demo(request):
    """
    Demo interativa: usuário digita um texto e vê a anonimização em tempo real.
    GET:  formulário
    POST: retorna texto anonimizado (JSON ou template)
    """
    if request.method == "GET":
        return render(request, "anonymizer/demo.html")

    if request.method == "POST":
        text = request.POST.get("text", "").strip()
        if not text:
            return JsonResponse({"error": "Texto vazio."}, status=400)

        # Demo simples: usa apenas padrões numéricos do normalizer (sem NER)
        # TODO: integrar modelo NER treinado quando disponível
        from src.preprocessing.normalizer import TextNormalizer
        normalizer = TextNormalizer(mask_phi=True)
        anonymized = normalizer.normalize(text)

        return render(request, "anonymizer/demo.html", {
            "original": text,
            "anonymized": anonymized,
            "note": "Demo usa apenas padrões numéricos (CPF, tel, CEP). "
                    "NER completo disponível após treinamento dos modelos.",
        })


def anonymize_batch(request):
    """
    Anonimização em lote: recebe documento do dataset e retorna texto anonimizado.
    Requer modelo NER treinado.
    """
    return render(request, "anonymizer/batch.html", {
        "note": "Anonimização em lote disponível após treinamento dos modelos NER."
    })
