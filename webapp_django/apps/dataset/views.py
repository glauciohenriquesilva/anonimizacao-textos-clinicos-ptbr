"""
Views do app Dataset — Importação e visualização de documentos clínicos.
"""
import csv as csv_module
import io
import json
import os

from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.conf import settings

from .models import ClinicalDocument, ImportBatch


def document_list(request):
    """Lista paginada de documentos importados com filtros."""
    docs = ClinicalDocument.objects.all()

    # Filtros GET
    doc_type  = request.GET.get("doc_type")
    text_type = request.GET.get("text_type")
    search    = request.GET.get("q")

    if doc_type:
        docs = docs.filter(doc_type=doc_type)
    if text_type:
        docs = docs.filter(text_type=text_type)
    if search:
        docs = docs.filter(raw_text__icontains=search)

    context = {
        "documents": docs[:100],   # TODO: paginação
        "total": docs.count(),
        "doc_type": doc_type,
        "text_type": text_type,
    }
    return render(request, "dataset/list.html", context)


def document_detail(request, pk: int):
    """Detalhe de um documento com texto bruto e processado lado a lado."""
    doc = get_object_or_404(ClinicalDocument, pk=pk)
    return render(request, "dataset/detail.html", {"doc": doc})


def import_csv(request):
    """
    Upload e importação de CSV de prescrições ou pareceres.
    GET: formulário de upload
    POST: processa e importa o CSV
    """
    if request.method == "GET":
        return render(request, "dataset/import.html")

    if request.method == "POST":
        csv_file   = request.FILES.get("csv_file")
        doc_type   = request.POST.get("doc_type", "prescricao")

        if not csv_file:
            messages.error(request, "Nenhum arquivo enviado.")
            return redirect("dataset:import")

        # Determinar colunas conforme tipo de documento
        text_col = "ds_evolucao" if doc_type == "prescricao" else "ds_parecer"
        date_col = "dt_pre_med"  if doc_type == "prescricao" else "dt_parecer"

        try:
            decoded = csv_file.read().decode("utf-8")
            reader  = csv_module.DictReader(io.StringIO(decoded), delimiter=";")
            rows    = list(reader)
        except Exception as e:
            messages.error(request, f"Erro ao ler CSV: {e}")
            return redirect("dataset:import")

        imported_ok = 0
        for row in rows:
            text = row.get(text_col, "").strip()
            if not text:
                continue

            doc, created = ClinicalDocument.objects.get_or_create(
                cd_atendimento=row.get("cd_atendimento", ""),
                doc_type=doc_type,
                defaults={
                    "cd_paciente": row.get("cd_paciente", ""),
                    "raw_text":    text,
                    "hospital":    row.get("ds_multi_empresa", ""),
                    "specialty":   row.get("ds_especialid_atendimento", ""),
                    "token_count": len(text.split()),
                    "char_count":  len(text),
                },
            )
            if created:
                imported_ok += 1

        # Registrar lote
        ImportBatch.objects.create(
            filename=csv_file.name,
            doc_type=doc_type,
            total_records=len(rows),
            imported_ok=imported_ok,
        )

        messages.success(
            request,
            f"✓ {imported_ok} documentos importados de {len(rows)} registros."
        )
        return redirect("dataset:list")


def exploratory_view(request):
    """
    Executa a análise exploratória e exibe a Tabela 1 do anteprojeto.
    Roda o script src/analysis/exploratory.py e exibe o resultado.
    """
    context = {"ran": False}

    raw_path = settings.DATA_RAW_PATH
    presc_path = os.path.join(raw_path, "prescricoes.csv")
    pareceres_path = os.path.join(raw_path, "pareceres.csv")

    if os.path.exists(presc_path) or os.path.exists(pareceres_path):
        try:
            import pandas as pd
            from src.analysis.exploratory import load_csv, analyze_document_type

            stats = {}
            for doc_type, fpath in [("prescricoes", presc_path), ("pareceres", pareceres_path)]:
                if os.path.exists(fpath):
                    df = load_csv(fpath)
                    stats[doc_type] = analyze_document_type(df, doc_type)

            context.update({"ran": True, "stats": stats})

        except Exception as e:
            context["error"] = str(e)

    return render(request, "dataset/exploratory.html", context)
