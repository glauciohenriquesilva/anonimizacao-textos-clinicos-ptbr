"""
Análise Exploratória do Dataset de Textos Clínicos
====================================================
Gera a "Tabela 1 – Caracterização exploratória das amostras iniciais
de textos clínicos" conforme definido no anteprojeto.

Uso:
    python src/analysis/exploratory.py \
        --prescricoes data/raw/prescricoes.csv \
        --pareceres data/raw/pareceres.csv \
        --output outputs/exploratory_analysis/

Referência: Schiezaro et al. (2026); Silva & Pazin-Filho (2025)
"""

import argparse
import csv
import json
import os
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns


# ─── Constantes ────────────────────────────────────────────────────────────────

TEXT_COLUMN = {
    "prescricoes": "ds_evolucao",
    "pareceres": "ds_parecer",
}

DATE_COLUMN = {
    "prescricoes": "dt_pre_med",
    "pareceres": "dt_parecer",
}

# Padrões de template estruturado (formulários de UTI/enfermagem)
TEMPLATE_MARKERS = [
    "( X )", "(  X  )", "( X)", "(X )",  # checkboxes
    "SISTEMA NEUROLÓGICO", "SISTEMA CARDIOVASCULAR",
    "SINAIS VITAIS:", "SISTEMA RESPIRATÓRIO",
    "DIAGNÓSTICOS DE ENFERMAGEM",
]


# ─── Funções auxiliares ─────────────────────────────────────────────────────────

def load_csv(filepath: str) -> pd.DataFrame:
    """
    Carrega CSV com separador ';' e tratamento de encoding.
    Os campos de texto podem conter quebras de linha e ponto-e-vírgula internos.
    """
    return pd.read_csv(
        filepath,
        sep=";",
        quoting=csv.QUOTE_MINIMAL,
        encoding="utf-8",
        dtype=str,
        on_bad_lines="warn",
    )


def count_tokens_simple(text: str) -> int:
    """Conta tokens por espaço em branco (estimativa rápida sem tokenizador NLP)."""
    if not isinstance(text, str):
        return 0
    return len(text.split())


def count_sentences_simple(text: str) -> int:
    """Estima número de sentenças por pontuação final."""
    if not isinstance(text, str):
        return 0
    return max(1, text.count(".") + text.count("!") + text.count("?"))


def is_template(text: str) -> bool:
    """Detecta se o texto é um template estruturado com checkboxes/formulário."""
    if not isinstance(text, str):
        return False
    count = sum(1 for marker in TEMPLATE_MARKERS if marker in text.upper())
    return count >= 2


def classify_text_type(text: str) -> str:
    """Classifica o texto como 'template_estruturado' ou 'texto_livre'."""
    return "template_estruturado" if is_template(text) else "texto_livre"


# ─── Análise por tipo de documento ─────────────────────────────────────────────

def analyze_document_type(df: pd.DataFrame, doc_type: str) -> dict:
    """
    Retorna estatísticas descritivas de um DataFrame de documentos clínicos.

    Args:
        df: DataFrame carregado do CSV
        doc_type: 'prescricoes' ou 'pareceres'

    Returns:
        Dicionário com estatísticas para a Tabela 1
    """
    text_col = TEXT_COLUMN[doc_type]
    date_col = DATE_COLUMN[doc_type]

    # Filtrar registros com texto
    mask = df[text_col].notna() & (df[text_col].str.strip() != "")
    df_valid = df[mask].copy()

    # Contagens básicas
    total_records = len(df_valid)
    unique_patients = df_valid["cd_paciente"].nunique() if "cd_paciente" in df_valid.columns else None
    unique_hospitals = df_valid["ds_multi_empresa"].nunique() if "ds_multi_empresa" in df_valid.columns else None

    # Comprimento dos textos
    df_valid["_tokens"] = df_valid[text_col].apply(count_tokens_simple)
    df_valid["_chars"] = df_valid[text_col].str.len()
    df_valid["_sentences"] = df_valid[text_col].apply(count_sentences_simple)

    # Tipo de texto (template vs. livre)
    df_valid["_text_type"] = df_valid[text_col].apply(classify_text_type)
    type_counts = df_valid["_text_type"].value_counts().to_dict()

    # Especialidades
    top_specialties = {}
    if "ds_especialid_atendimento" in df_valid.columns:
        top_specialties = (
            df_valid["ds_especialid_atendimento"]
            .value_counts()
            .head(5)
            .to_dict()
        )

    # Período de cobertura
    periodo = {}
    if date_col in df_valid.columns:
        try:
            dates = pd.to_datetime(df_valid[date_col], dayfirst=True, errors="coerce")
            periodo = {
                "inicio": dates.min().strftime("%d/%m/%Y") if dates.notna().any() else "N/A",
                "fim": dates.max().strftime("%d/%m/%Y") if dates.notna().any() else "N/A",
            }
        except Exception:
            periodo = {"inicio": "N/A", "fim": "N/A"}

    return {
        "tipo_documento": doc_type,
        "total_registros": total_records,
        "pacientes_unicos": unique_patients,
        "hospitais_unicos": unique_hospitals,
        "periodo": periodo,
        "tokens": {
            "minimo": int(df_valid["_tokens"].min()),
            "mediana": int(df_valid["_tokens"].median()),
            "media": round(df_valid["_tokens"].mean(), 1),
            "maximo": int(df_valid["_tokens"].max()),
            "p25": int(df_valid["_tokens"].quantile(0.25)),
            "p75": int(df_valid["_tokens"].quantile(0.75)),
        },
        "caracteres": {
            "minimo": int(df_valid["_chars"].min()),
            "mediana": int(df_valid["_chars"].median()),
            "media": round(df_valid["_chars"].mean(), 1),
            "maximo": int(df_valid["_chars"].max()),
        },
        "sentencas": {
            "mediana": int(df_valid["_sentences"].median()),
            "media": round(df_valid["_sentences"].mean(), 1),
        },
        "tipo_texto": {
            "texto_livre": type_counts.get("texto_livre", 0),
            "template_estruturado": type_counts.get("template_estruturado", 0),
            "pct_template": round(
                type_counts.get("template_estruturado", 0) / total_records * 100, 1
            ) if total_records > 0 else 0,
        },
        "top5_especialidades": top_specialties,
        "registros_sem_texto": len(df) - total_records,
    }


def gerar_tabela1(stats_dict: dict, output_dir: Path) -> pd.DataFrame:
    """
    Gera a Tabela 1 do anteprojeto em formato DataFrame e exporta para CSV/Excel.
    """
    rows = []
    for doc_type, s in stats_dict.items():
        rows.append({
            "Tipo de Documento": "Prescrições" if doc_type == "prescricoes" else "Pareceres",
            "Total de Registros": f"{s['total_registros']:,}",
            "Pacientes Únicos": f"{s['pacientes_unicos']:,}" if s["pacientes_unicos"] else "N/D",
            "Hospitais": f"{s['hospitais_unicos']}" if s["hospitais_unicos"] else "N/D",
            "Período (início)": s["periodo"].get("inicio", "N/D"),
            "Período (fim)": s["periodo"].get("fim", "N/D"),
            "Tokens — Mediana (IQR)": f"{s['tokens']['mediana']} ({s['tokens']['p25']}–{s['tokens']['p75']})",
            "Tokens — Mínimo": s["tokens"]["minimo"],
            "Tokens — Máximo": s["tokens"]["maximo"],
            "Caracteres — Mediana": s["caracteres"]["mediana"],
            "Sentenças — Mediana": s["sentencas"]["mediana"],
            "Texto livre (n)": s["tipo_texto"]["texto_livre"],
            "Template estruturado (n)": s["tipo_texto"]["template_estruturado"],
            "% Template": f"{s['tipo_texto']['pct_template']}%",
            "Registros sem texto": s["registros_sem_texto"],
        })

    df_tabela1 = pd.DataFrame(rows).T
    df_tabela1.columns = df_tabela1.iloc[0]
    df_tabela1 = df_tabela1.iloc[1:]

    # Salvar
    output_dir.mkdir(parents=True, exist_ok=True)
    df_tabela1.to_csv(output_dir / "tabela1_caracterizacao.csv", encoding="utf-8")
    df_tabela1.to_excel(output_dir / "tabela1_caracterizacao.xlsx")

    print("\n" + "=" * 60)
    print("TABELA 1 — Caracterização Exploratória das Amostras")
    print("=" * 60)
    print(df_tabela1.to_string())

    return df_tabela1


def gerar_graficos(stats_dict: dict, dfs: dict, output_dir: Path):
    """Gera gráficos de distribuição para análise exploratória."""
    output_dir.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid", palette="muted")

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("Caracterização Exploratória do Dataset Clínico", fontsize=14, fontweight="bold")

    colors = {"prescricoes": "#2196F3", "pareceres": "#FF9800"}
    labels = {"prescricoes": "Prescrições", "pareceres": "Pareceres"}

    for idx, (doc_type, df) in enumerate(dfs.items()):
        text_col = TEXT_COLUMN[doc_type]
        df_valid = df[df[text_col].notna() & (df[text_col].str.strip() != "")].copy()
        df_valid["_tokens"] = df_valid[text_col].apply(count_tokens_simple)
        color = colors[doc_type]

        # Gráfico 1: distribuição de tokens (histograma)
        ax = axes[0][idx]
        tokens_clip = df_valid["_tokens"].clip(upper=df_valid["_tokens"].quantile(0.95))
        ax.hist(tokens_clip, bins=50, color=color, edgecolor="white", alpha=0.8)
        med = df_valid["_tokens"].median()
        ax.axvline(med, color="red", linestyle="--", linewidth=1.5, label=f"Mediana: {int(med)}")
        ax.set_title(f"{labels[doc_type]} — Distribuição de Tokens")
        ax.set_xlabel("Número de tokens (até P95)")
        ax.set_ylabel("Frequência")
        ax.legend()

        # Gráfico 2: top especialidades
        ax = axes[1][idx]
        if "ds_especialid_atendimento" in df_valid.columns:
            top = df_valid["ds_especialid_atendimento"].value_counts().head(8)
            top.plot(kind="barh", ax=ax, color=color, edgecolor="white")
            ax.set_title(f"{labels[doc_type]} — Top Especialidades")
            ax.set_xlabel("Número de registros")
            ax.set_ylabel("")

    plt.tight_layout()
    plt.savefig(output_dir / "figura1_distribuicao_tokens.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"✓ Gráfico salvo em {output_dir / 'figura1_distribuicao_tokens.png'}")


# ─── Entrypoint CLI ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Análise exploratória do dataset de textos clínicos"
    )
    parser.add_argument("--prescricoes", type=str, required=True, help="Caminho para prescricoes.csv")
    parser.add_argument("--pareceres", type=str, required=True, help="Caminho para pareceres.csv")
    parser.add_argument("--output", type=str, default="outputs/exploratory_analysis/", help="Diretório de saída")
    args = parser.parse_args()

    output_dir = Path(args.output)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = output_dir / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    print("Carregando dados...")
    dfs = {}
    stats = {}

    for doc_type, filepath in [("prescricoes", args.prescricoes), ("pareceres", args.pareceres)]:
        if not os.path.exists(filepath):
            print(f"⚠️  Arquivo não encontrado: {filepath}")
            continue
        print(f"  → Carregando {filepath}...")
        df = load_csv(filepath)
        dfs[doc_type] = df
        print(f"     {len(df):,} registros carregados")
        stats[doc_type] = analyze_document_type(df, doc_type)

    if not stats:
        print("Nenhum dado carregado. Verifique os caminhos.")
        return

    # Gerar Tabela 1
    gerar_tabela1(stats, run_dir)

    # Gerar gráficos
    if len(dfs) > 0:
        gerar_graficos(stats, dfs, run_dir)

    # Salvar estatísticas brutas em JSON
    with open(run_dir / "stats_completas.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Análise concluída. Resultados em: {run_dir}")


if __name__ == "__main__":
    main()
