"""
Views — Pré-processamento de Textos Clínicos (etapa 1 do pipeline)

Subseções:
    1.2  normalizacao — Unicode NFC, espaços, datas ISO, mascaramento PHI
    1.3  segmentacao  — texto livre vs. template, proteção de abreviações
    1.4  tokenizacao  — word-level (CRF) e subword (BERT)
    1.5  exportacao   — CoNLL e JSONL para anotação / treinamento
"""
from django.shortcuts import render


def normalizacao(request):
    """Normalização textual: Unicode, espaços, datas ISO 8601, CPF/tel/CEP."""
    context = {
        "section": "preprocessamento",
        "subsection": "normalizacao",
    }
    return render(request, "preprocessamento/normalizacao.html", context)


def segmentacao(request):
    """Segmentação em sentenças: detecção de tipo, proteção de abreviações médicas."""
    context = {
        "section": "preprocessamento",
        "subsection": "segmentacao",
    }
    return render(request, "preprocessamento/segmentacao.html", context)


def tokenizacao(request):
    """Tokenização: word-level para CRF, subword (AutoTokenizer) para BERT."""
    context = {
        "section": "preprocessamento",
        "subsection": "tokenizacao",
    }
    return render(request, "preprocessamento/tokenizacao.html", context)


def exportacao(request):
    """Exportação do corpus pré-processado: CoNLL-2003 e JSONL."""
    context = {
        "section": "preprocessamento",
        "subsection": "exportacao",
    }
    return render(request, "preprocessamento/exportacao.html", context)
