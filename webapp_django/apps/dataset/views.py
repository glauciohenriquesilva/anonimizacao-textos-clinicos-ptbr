"""
Views do app Dataset.
"""
import csv as csv_module
import io
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect

from .models import ClinicalDocument, ImportBatch


# ──────────────────────────────────────────────────────────────────────────────
# Listagem e detalhe
# ──────────────────────────────────────────────────────────────────────────────

def document_list(request):
    """Lista paginada de documentos com filtros."""
    docs = ClinicalDocument.objects.all()

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
        "documents": docs[:100],
        "total":     docs.count(),
        "doc_type":  doc_type,
        "text_type": text_type,
    }
    return render(request, "dataset/list.html", context)


def document_detail(request, pk: int):
    """Detalhe de um documento."""
    doc = get_object_or_404(ClinicalDocument, pk=pk)
    return render(request, "dataset/detail.html", {"doc": doc})


# ──────────────────────────────────────────────────────────────────────────────
# 1) Importar CSV → substitui arquivo em data/raw/
# ──────────────────────────────────────────────────────────────────────────────

def import_csv(request):
    """
    GET  → formulário de upload
    POST → valida e substitui prescricoes.csv ou pareceres.csv em data/raw/
    """
    if request.method == "GET":
        return render(request, "dataset/import.html")

    csv_file = request.FILES.get("csv_file")
    doc_type = request.POST.get("doc_type", "prescricao")

    if not csv_file:
        messages.error(request, "Nenhum arquivo enviado.")
        return redirect("dataset:import")

    filename     = "prescricoes.csv" if doc_type == "prescricao" else "pareceres.csv"
    dest_path    = Path(settings.DATA_RAW_PATH) / filename
    expected_col = "ds_evolucao"    if doc_type == "prescricao" else "ds_parecer"

    try:
        content = csv_file.read()
        decoded = content.decode("utf-8-sig")
        reader  = csv_module.DictReader(io.StringIO(decoded), delimiter=";")
        cols    = [c.strip() for c in (reader.fieldnames or [])]

        # Valida colunas mínimas
        required = ["cd_paciente", "dt_atendimento", expected_col]
        missing  = [c for c in required if c not in cols]
        if missing:
            messages.error(request, f"Colunas ausentes no arquivo: {missing}")
            return redirect("dataset:import")

        n_records = sum(1 for _ in reader)

    except Exception as e:
        messages.error(request, f"Erro ao ler arquivo: {e}")
        return redirect("dataset:import")

    # Substitui o arquivo em data/raw/
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "wb") as f:
        f.write(content)

    messages.success(
        request,
        f"✓ {filename} atualizado com {n_records} registros. "
        f"Execute 'Carregar Dataset para Pipeline' para atualizar o banco."
    )
    return redirect("dataset:list")


# ──────────────────────────────────────────────────────────────────────────────
# 2) Análise Exploratória → lê CSVs, sem tocar no banco
# ──────────────────────────────────────────────────────────────────────────────

def exploratory_view(request):
    """
    GET  → página com botão Executar
    POST → roda ExploratoryAnalysis e exibe resultados
    """
    import json
    import pandas as pd
    from src.analysis.exploratory import ExploratoryAnalysis

    context = {"executed": False}

    if request.method == "POST":
        presc_path = Path(settings.DATA_RAW_PATH) / "prescricoes.csv"
        par_path   = Path(settings.DATA_RAW_PATH) / "pareceres.csv"

        try:
            ea = ExploratoryAnalysis(
                path_prescricoes=presc_path,
                path_pareceres=par_path,
                output_dir=Path(settings.BASE_DIR) / "outputs" / "exploratory_analysis",
            )
            stats = ea.run()

            context.update({
                "executed":             True,
                "stats":                stats,
                "chart_especialidades": json.dumps({
                    "labels": list(stats["top_especialidades"].keys()),
                    "values": list(stats["top_especialidades"].values()),
                }),
                "chart_tokens_presc": json.dumps(_token_buckets(ea.df_presc, "ds_evolucao")),
                "chart_tokens_par":   json.dumps(_token_buckets(ea.df_par,   "ds_parecer")),
            })

        except FileNotFoundError as e:
            context["error"] = f"Arquivo não encontrado: {e}"
        except ValueError as e:
            context["error"] = f"Erro no schema do CSV: {e}"
        except Exception as e:
            context["error"] = f"Erro inesperado: {e}"

    return render(request, "dataset/exploratory.html", context)


def _token_buckets(df, text_col: str, n_bins: int = 15) -> dict:
    """Prepara histograma de tokens para o Chart.js."""
    import pandas as pd
    counts = df[text_col].apply(lambda t: len(t.split()) if isinstance(t, str) else 0)
    cuts   = pd.cut(counts, bins=n_bins)
    freq   = cuts.value_counts().sort_index()
    return {
        "labels": [f"{int(i.mid)}" for i in freq.index],
        "values": [int(v) for v in freq.tolist()],
    }


# ──────────────────────────────────────────────────────────────────────────────
# 3) Carregar Dataset para Pipeline → CSV → tb_texto_clinico
# ──────────────────────────────────────────────────────────────────────────────

def load_to_pipeline(request):
    """
    GET  → mostra status (registros nos CSVs vs banco)
    POST → lê os CSVs e popula tb_texto_clinico
    """
    import pandas as pd
    from src.analysis.exploratory import (
        classify_text_type, load_csv,
        COLUMNS_PRESCRICOES, COLUMNS_PARECERES,
    )

    presc_path = Path(settings.DATA_RAW_PATH) / "prescricoes.csv"
    par_path   = Path(settings.DATA_RAW_PATH) / "pareceres.csv"

    TEXT_TYPE_MAP = {
        "livre":    "texto_livre",
        "template": "template_estruturado",
        "vazio":    "",
    }

    if request.method == "GET":
        context = {
            "presc_exists":    presc_path.exists(),
            "par_exists":      par_path.exists(),
            "db_total":        ClinicalDocument.objects.count(),
            "db_presc":        ClinicalDocument.objects.filter(doc_type="prescricao").count(),
            "db_par":          ClinicalDocument.objects.filter(doc_type="parecer").count(),
            "csv_presc_count": _csv_row_count(presc_path),
            "csv_par_count":   _csv_row_count(par_path),
        }
        return render(request, "dataset/load_pipeline.html", context)

    # POST → carrega para o banco
    clear_existing = request.POST.get("clear_existing") == "on"
    if clear_existing:
        deleted, _ = ClinicalDocument.objects.all().delete()
    else:
        deleted = 0

    imported_ok = 0
    skipped     = 0
    errors      = []

    for doc_type, path, text_col, expected_cols in [
        ("prescricao", presc_path, "ds_evolucao", COLUMNS_PRESCRICOES),
        ("parecer",    par_path,   "ds_parecer",  COLUMNS_PARECERES),
    ]:
        if not path.exists():
            errors.append(f"{path.name} não encontrado em data/raw/")
            continue

        try:
            df = load_csv(path, expected_cols)
        except Exception as e:
            errors.append(f"Erro ao ler {path.name}: {e}")
            continue

        docs_to_create = []
        for _, row in df.iterrows():
            text = str(row.get(text_col, "")).strip()
            if not text:
                skipped += 1
                continue

            text_type = TEXT_TYPE_MAP.get(classify_text_type(text), "")
            doc_date  = row["dt_atendimento"].date() if pd.notna(row.get("dt_atendimento")) else None

            docs_to_create.append(ClinicalDocument(
                cd_paciente=str(row.get("cd_paciente", "")),
                doc_type=doc_type,
                raw_text=text,
                text_type=text_type,
                doc_date=doc_date,
                hospital=str(row.get("ds_multi_empresa", "")),
                specialty=str(row.get("ds_especialid_atendimento", "")),
                token_count=len(text.split()),
                char_count=len(text),
                sentence_count=len([ln for ln in text.splitlines() if ln.strip()]),
            ))

        # bulk_create para performance
        ClinicalDocument.objects.bulk_create(docs_to_create, batch_size=500)
        imported_ok += len(docs_to_create)

    for err in errors:
        messages.error(request, err)

    if imported_ok:
        msg = f"✓ {imported_ok} documentos carregados para o pipeline."
        if deleted:
            msg += f" ({deleted} registros anteriores removidos.)"
        if skipped:
            msg += f" {skipped} ignorados (texto vazio)."
        messages.success(request, msg)

    return redirect("dataset:list")


def _csv_row_count(path: Path) -> int:
    """Conta registros de um CSV (exclui o header). Retorna 0 se não existir."""
    if not path.exists():
        return 0
    with open(path, encoding="utf-8-sig") as f:
        return sum(1 for _ in csv_module.reader(f, delimiter=";")) - 1