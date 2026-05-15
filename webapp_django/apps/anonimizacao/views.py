"""
Views — Anonimização / Desidentificação (etapa 3 do pipeline)

Subseções:
    3.1  substituicao — Substituição por marcadores [TIPO_N] (demo interativa)
    3.2  privacidade  — Dimensão L do TILD: Coverage e Precision_anon
    3.3  utilidade    — Dimensão I do TILD: ΔF1 downstream
"""
from django.shortcuts import render
from django.http import JsonResponse

from src.preprocessing.normalizer import TextNormalizer


def substituicao(request):
    """
    Demo interativa de anonimização por substituição.
    GET:  formulário de entrada.
    POST: retorna texto com PHI substituído por [MARCADORES].
    """
    if request.method == "GET":
        return render(request, "anonimizacao/substituicao.html", {
            "section": "anonimizacao",
            "subsection": "substituicao",
        })

    if request.method == "POST":
        text = request.POST.get("text", "").strip()
        if not text:
            return JsonResponse({"error": "Texto vazio."}, status=400)

        # Demo: usa normalizer com mascaramento numérico (PHI completo após NER treinado)
        normalizer = TextNormalizer(mask_phi=True)
        anonymized = normalizer.normalize(text)

        return render(request, "anonimizacao/substituicao.html", {
            "section": "anonimizacao",
            "subsection": "substituicao",
            "original": text,
            "anonymized": anonymized,
            "note": (
                "Demo usa apenas padrões numéricos (CPF, tel, CEP, e-mail). "
                "Anonimização completa com NER disponível após treinamento dos modelos."
            ),
        })


def privacidade(request):
    """Avaliação de privacidade — Dimensão L do TILD: Coverage e Precision_anon."""
    context = {
        "section": "anonimizacao",
        "subsection": "privacidade",
    }
    return render(request, "anonimizacao/privacidade.html", context)


def utilidade(request):
    """Avaliação de utilidade clínica — Dimensão I do TILD: ΔF1 downstream."""
    context = {
        "section": "anonimizacao",
        "subsection": "utilidade",
    }
    return render(request, "anonimizacao/utilidade.html", context)
