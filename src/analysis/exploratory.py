"""
0) Análise Exploratória — exploratory.py
=========================================
Etapa 0 do pipeline de anonimização de textos clínicos em português brasileiro.

Blocos implementados (espelho do diagrama):
  0.1)  Leitura do DataSet
  0.2)  Estatísticas Descritivas
  0.3)  Distribuição de Tokens
  0.4)  Classificação do Tipo de Texto
  0.5)  Geração de Saídas

Uso via CLI:
  python src/analysis/exploratory.py \\
      --prescricoes data/raw/prescricoes.csv \\
      --pareceres   data/raw/pareceres.csv   \\
      --output      outputs/exploratory_analysis

Uso via notebook / Django:
  from src.analysis.exploratory import load_csv, analyze_document_type
  from src.analysis.exploratory import gerar_tabela1, gerar_graficos
  from src.analysis.exploratory import save_stats_json, load_stats_json
"""

import json
import re
import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")   # backend não-interativo — obrigatório fora do main thread
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
import seaborn as sns


# ══════════════════════════════════════════════════════════════════════════════
# Schema esperado — colunas obrigatórias por tipo de documento
# ══════════════════════════════════════════════════════════════════════════════

COMMON_COLUMNS = [
    "cd_paciente",
    "nm_convenio",
    "dt_atendimento",
    "tp_atendimento",
    "ds_ori_ate",
    "ds_servico",
    "ds_mot_alt",
    "ds_cid",
    "ds_tipo_internacao",
    "ds_loc_proced",
    "ds_multi_empresa",
    "ds_especialid_atendimento",
    "ds_tip_mar",
]

COLUMNS_PRESCRICOES = COMMON_COLUMNS + ["ds_evolucao"]
COLUMNS_PARECERES   = COMMON_COLUMNS + ["ds_parecer"]

# Mapeia doc_type → coluna de texto clínico
_TEXT_COLUMN = {"prescricoes": "ds_evolucao", "pareceres": "ds_parecer"}

# Mapeia doc_type → lista de colunas esperadas
_EXPECTED = {
    "prescricoes": COLUMNS_PRESCRICOES,
    "pareceres":   COLUMNS_PARECERES,
}


# ══════════════════════════════════════════════════════════════════════════════
# Padrões de detecção (usados em 0.4 e na detecção de PHI em 0.3)
# ══════════════════════════════════════════════════════════════════════════════

# Padrões que indicam template estruturado (formulários de UTI/enfermagem)
_TEMPLATE_PATTERNS = [
    r"^#\s+\w",            # cabeçalhos com # (ex: # HDA:, # ORTOPEDIA)
    r"\(\s*[XxSs]\s*\)",   # checkboxes: ( X ) ( S )
    r"\[\s*[XxSs]\s*\]",   # checkboxes: [ X ] [ S ]
    r"SINAIS VITAIS\s*:",
    r"\bPA\s*:",
    r"\bFC\s*:",
    r"\bSAT\s*:",
    r"\bTAX\s*:",
    r"\bFR\s*:",
]
_TEMPLATE_RE = re.compile("|".join(_TEMPLATE_PATTERNS), re.MULTILINE)

# Padrões para detecção de PHI no texto (datas e horas)
_DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
_TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\b")


# ══════════════════════════════════════════════════════════════════════════════
# 0.1) Leitura do DataSet
# ══════════════════════════════════════════════════════════════════════════════

# Início - 0) Análise Exploratória - 0.1) Leitura do DataSet
# - 0.1.1) Leitura CSV prescrições (sep=";", UTF-8)
# - 0.1.2) Leitura CSV pareceres (sep=";", UTF-8)
# - 0.1.3) Validação de schema (colunas esperadas presentes)
def load_csv(path, doc_type, nrows=None):
    """
    Lê um CSV clínico (sep=';', UTF-8 com BOM) e valida o schema.

    Cobre os blocos:
      0.1.1 — Leitura CSV prescrições (quando doc_type='prescricoes')
      0.1.2 — Leitura CSV pareceres   (quando doc_type='pareceres')
      0.1.3 — Validação de schema (colunas esperadas presentes)

    Parâmetros
    ----------
    path     : str | Path — caminho do arquivo CSV
    doc_type : str — 'prescricoes' ou 'pareceres'
    nrows    : int | None — limitar leitura a N linhas (útil para testes)

    Retorna
    -------
    pd.DataFrame com colunas em minúsculas; texto alvo sem NaN.

    Lança
    -----
    FileNotFoundError se o arquivo não existir.
    ValueError se colunas esperadas estiverem ausentes.
    ValueError se doc_type não for reconhecido.
    """
    if doc_type not in _EXPECTED:
        raise ValueError(
            f"doc_type deve ser 'prescricoes' ou 'pareceres'. Recebido: {doc_type!r}"
        )

    p = Path(path)

    # 0.1.3 — validação prévia: arquivo existe?
    if not p.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {p}")

    # 0.1.1 / 0.1.2 — leitura do CSV (sep=";", UTF-8 com BOM)
    df = pd.read_csv(
        p,
        sep=";",
        encoding="utf-8-sig",   # UTF-8 com BOM (padrão MV)
        dtype=str,               # tudo como string para preservar formatação original
        low_memory=False,
        nrows=nrows,
    )

    # Normaliza nomes de colunas: remove espaços, converte para minúsculas
    df.columns = [c.strip().lower() for c in df.columns]

    # 0.1.3 — validação de schema: colunas esperadas presentes?
    expected = _EXPECTED[doc_type]
    missing  = [c for c in expected if c not in df.columns]
    if missing:
        raise ValueError(
            f"Colunas ausentes em '{p.name}' (doc_type='{doc_type}'): {missing}"
        )

    # Preenche a coluna de texto alvo: NaN → string vazia
    text_col = _TEXT_COLUMN[doc_type]
    df[text_col] = df[text_col].fillna("")

    print(f"✓ {len(df):,} registros carregados de '{p.name}' [{doc_type}]")
    return df
# Fim - 0) Análise Exploratória - 0.1) Leitura do DataSet
# - 0.1.1) Leitura CSV prescrições (sep=";", UTF-8)
# - 0.1.2) Leitura CSV pareceres (sep=";", UTF-8)
# - 0.1.3) Validação de schema (colunas esperadas presentes)


# ══════════════════════════════════════════════════════════════════════════════
# 0.3) Distribuição de Tokens — funções auxiliares
# (definidas aqui pois são reutilizadas em analyze_document_type)
# ══════════════════════════════════════════════════════════════════════════════

# Início - 0) Análise Exploratória - 0.3) Distribuição de Tokens - 0.3.1) Tokenização simples (split por espaço)
def count_tokens(text: str) -> int:
    """
    Conta tokens por split simples em espaços (whitespace).

    Escolha deliberada: tokenização leve sem dependência de spaCy/NLTK,
    suficiente para análise exploratória. A tokenização completa é feita
    na Etapa 1 (Pré-processamento).
    """
    return len(text.split()) if isinstance(text, str) else 0
# Fim - 0) Análise Exploratória - 0.3) Distribuição de Tokens - 0.3.1) Tokenização simples (split por espaço)


# Início - 0) Análise Exploratória - 0.3) Distribuição de Tokens - 0.3.3) Distribuição de caracteres por doc
def count_chars(text: str) -> int:
    """Conta o total de caracteres do texto (incluindo espaços e pontuação)."""
    return len(text) if isinstance(text, str) else 0
# Fim - 0) Análise Exploratória - 0.3) Distribuição de Tokens - 0.3.3) Distribuição de caracteres por doc


# Início - 0) Análise Exploratória - 0.3) Distribuição de Tokens - 0.3.4) Distribuição de sentenças por doc
def count_sentences(text: str) -> int:
    """
    Estima o número de sentenças contando linhas não-vazias.

    Adequado para textos clínicos do MV onde cada linha tende a ser
    uma entrada ou sentença clínica distinta. Documentos com texto
    corrido (sem quebras) retornam 1.
    """
    if not isinstance(text, str) or not text.strip():
        return 0
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return max(len(lines), 1)
# Fim - 0) Análise Exploratória - 0.3) Distribuição de Tokens - 0.3.4) Distribuição de sentenças por doc


# ══════════════════════════════════════════════════════════════════════════════
# 0.4) Classificação do Tipo de Texto — função auxiliar
# ══════════════════════════════════════════════════════════════════════════════

# Início - 0) Análise Exploratória - 0.4) Classificação do Tipo de Texto - 0.4.1) Detecção texto livre vs. template estruturado (marcadores: "( X )", "SINAIS VITAIS:...")
def classify_text_type(text: str) -> str:
    """
    Classifica o texto como 'template', 'livre' ou 'vazio'.

    Critério: presença de qualquer marcador estrutural definido em
    _TEMPLATE_PATTERNS (cabeçalhos com #, checkboxes ( X )/[ X ],
    campos de sinais vitais PA:, FC:, SAT:, TAX:, FR:).

    Retornos possíveis
    ------------------
    'template' — marcador estrutural detectado
    'livre'    — texto narrativo sem marcadores
    'vazio'    — texto ausente ou apenas espaços
    """
    if not isinstance(text, str) or not text.strip():
        return "vazio"
    return "template" if _TEMPLATE_RE.search(text) else "livre"
# Fim - 0) Análise Exploratória - 0.4) Classificação do Tipo de Texto - 0.4.1) Detecção texto livre vs. template estruturado (marcadores: "( X )", "SINAIS VITAIS:...")


# ══════════════════════════════════════════════════════════════════════════════
# 0.2 + 0.3 + 0.4 — Análise por tipo de documento
# Orquestra todos os blocos das seções 0.2, 0.3 e 0.4 para um único
# tipo de documento (prescricoes ou pareceres).
# ══════════════════════════════════════════════════════════════════════════════

def analyze_document_type(df: pd.DataFrame, doc_type: str) -> dict:
    """
    Calcula todas as estatísticas exploratórias para um tipo de documento.

    Parâmetros
    ----------
    df       : DataFrame retornado por load_csv()
    doc_type : 'prescricoes' ou 'pareceres'

    Retorna
    -------
    dict com estrutura compatível com save_stats_json() e com o
    contexto esperado pelas views Django (views.py).
    """
    if doc_type not in _TEXT_COLUMN:
        raise ValueError(
            f"doc_type deve ser 'prescricoes' ou 'pareceres'. Recebido: {doc_type!r}"
        )

    text_col = _TEXT_COLUMN[doc_type]
    result: dict = {"doc_type": doc_type}

    # ──────────────────────────────────────────────────────────────────────────
    # Início - 0) Análise Exploratória - 0.2) Estatísticas Descritivas - 0.2.1) Contagem total de registros por tipo
    result["n_total"] = int(len(df))
    # Fim - 0) Análise Exploratória - 0.2) Estatísticas Descritivas - 0.2.1) Contagem total de registros por tipo

    # ──────────────────────────────────────────────────────────────────────────
    # Início - 0) Análise Exploratória - 0.2) Estatísticas Descritivas - 0.2.2) Pacientes únicos (cd_paciente)
    result["n_pacientes_unicos"] = (
        int(df["cd_paciente"].nunique()) if "cd_paciente" in df.columns else None
    )
    # Fim - 0) Análise Exploratória - 0.2) Estatísticas Descritivas - 0.2.2) Pacientes únicos (cd_paciente)

    # ──────────────────────────────────────────────────────────────────────────
    # Início - 0) Análise Exploratória - 0.2) Estatísticas Descritivas - 0.2.3) Período coberto (dt_atendimento min/max)
    result["periodo"] = {"min": None, "max": None}
    if "dt_atendimento" in df.columns:
        # Tenta interpretar datas no formato brasileiro dd/mm/yyyy.
        # Datas em outros formatos (ex: m/dd/yyyy) ficam como NaT.
        datas = pd.to_datetime(
            df["dt_atendimento"], format="%d/%m/%Y", errors="coerce"
        )
        if datas.notna().any():
            result["periodo"]["min"] = datas.min().strftime("%d/%m/%Y")
            result["periodo"]["max"] = datas.max().strftime("%d/%m/%Y")
    # Fim - 0) Análise Exploratória - 0.2) Estatísticas Descritivas - 0.2.3) Período coberto (dt_atendimento min/max)

    # ──────────────────────────────────────────────────────────────────────────
    # Início - 0) Análise Exploratória - 0.2) Estatísticas Descritivas - 0.2.4) Top especialidades médicas
    result["top_especialidades"] = []
    if "ds_especialid_atendimento" in df.columns:
        top = (
            df["ds_especialid_atendimento"]
            .str.strip()
            .replace("", pd.NA)        # descarta células vazias
            .dropna()
            .value_counts()
            .head(10)
            .reset_index()
        )
        top.columns = ["especialidade", "total"]
        total_geral = top["total"].sum()
        top["pct"] = (top["total"] / total_geral * 100).round(1)
        result["top_especialidades"] = top.to_dict(orient="records")
    # Fim - 0) Análise Exploratória - 0.2) Estatísticas Descritivas - 0.2.4) Top especialidades médicas

    # ──────────────────────────────────────────────────────────────────────────
    # Início - 0) Análise Exploratória - 0.2) Estatísticas Descritivas - 0.2.5) Contagem de hospitais
    result["n_hospitais"] = (
        int(
            df["cd_multi_empresa"]
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .nunique()
        )
        if "cd_multi_empresa" in df.columns
        else None
    )
    # Fim - 0) Análise Exploratória - 0.2) Estatísticas Descritivas - 0.2.5) Contagem de hospitais

    # ──────────────────────────────────────────────────────────────────────────
    # Blocos 0.3 e 0.4 dependem da coluna de texto — verificação prévia
    if text_col not in df.columns:
        result["token_stats"] = None
        result["text_types"]  = None
        result["n_vazios"]    = None
        result["pct_vazios"]  = None
        return result

    texts = df[text_col].fillna("")

    # ──────────────────────────────────────────────────────────────────────────
    # Início - 0) Análise Exploratória - 0.3) Distribuição de Tokens
    # - 0.3.1) Tokenização simples (split por espaço)
    # - 0.3.2) Cálculo min / mediana / média / máx / p25 / p75
    # - 0.3.3) Distribuição de caracteres por doc
    # - 0.3.4) Distribuição de sentenças por doc
    token_counts = texts.apply(count_tokens)    # 0.3.1
    char_counts  = texts.apply(count_chars)     # 0.3.3
    sent_counts  = texts.apply(count_sentences) # 0.3.4

    def _stats(serie: pd.Series) -> dict:
        """Computa as 6 estatísticas do bloco 0.3.2 para uma série numérica."""
        return {
            "min":    int(serie.min()),
            "p25":    round(float(serie.quantile(0.25)), 1),
            "median": round(float(serie.median()), 1),
            "mean":   round(float(serie.mean()), 1),
            "p75":    round(float(serie.quantile(0.75)), 1),
            "max":    int(serie.max()),
            "total":  int(serie.sum()),
        }

    result["token_stats"] = {
        "tokens":    _stats(token_counts),   # 0.3.1 + 0.3.2
        "chars":     _stats(char_counts),    # 0.3.3 + 0.3.2
        "sentences": _stats(sent_counts),    # 0.3.4 + 0.3.2
        "n_docs":    int(len(texts)),
        # Ocorrência de PHI estruturado no texto (usado na Tabela 1)
        "docs_with_newline": int(texts.str.contains(r"\n", regex=False).sum()),
        "docs_with_date":    int(texts.apply(lambda t: bool(_DATE_RE.search(t))).sum()),
        "docs_with_time":    int(texts.apply(lambda t: bool(_TIME_RE.search(t))).sum()),
    }
    # Fim - 0) Análise Exploratória - 0.3) Distribuição de Tokens
    # - 0.3.1) Tokenização simples (split por espaço)
    # - 0.3.2) Cálculo min / mediana / média / máx / p25 / p75
    # - 0.3.3) Distribuição de caracteres por doc
    # - 0.3.4) Distribuição de sentenças por doc

    # ──────────────────────────────────────────────────────────────────────────
    # Início - 0) Análise Exploratória - 0.4) Classificação do Tipo de Texto - 0.4.2) Cálculo da proporção texto livre / template por tipo de doc
    tipos       = texts.apply(classify_text_type)   # aplica 0.4.1 em cada documento
    counts_tipo = tipos.value_counts()
    n_total     = int(len(tipos))
    result["text_types"] = {
        tipo: {
            "count": int(n),
            "pct":   round(100 * n / n_total, 1),
        }
        for tipo, n in counts_tipo.items()
    }
    # Fim - 0) Análise Exploratória - 0.4) Classificação do Tipo de Texto - 0.4.2) Cálculo da proporção texto livre / template por tipo de doc

    # Documentos com texto vazio (dado complementar ao text_types)
    n_vazios = int((texts == "").sum())
    result["n_vazios"]   = n_vazios
    result["pct_vazios"] = round(n_vazios / len(df) * 100, 2) if len(df) else 0.0

    return result


# ══════════════════════════════════════════════════════════════════════════════
# 0.5) Geração de Saídas
# ══════════════════════════════════════════════════════════════════════════════

# Início - 0) Análise Exploratória - 0.5) Geração de Saídas - 0.5.1) Tabela 1 da dissertação (CSV + Excel)
def gerar_tabela1(stats: dict, output_dir) -> pd.DataFrame:
    """
    Gera a Tabela 1 da dissertação (capítulo de Metodologia).

    Parâmetros
    ----------
    stats      : dict {doc_type: resultado de analyze_document_type()}
    output_dir : str | Path — diretório de saída

    Retorna
    -------
    pd.DataFrame com uma linha por tipo de documento.
    Salva tabela1.csv (sep=';', UTF-8 BOM) + tabela1.xlsx.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for doc_type, s in stats.items():
        tok  = (s.get("token_stats") or {}).get("tokens")    or {}
        chr_ = (s.get("token_stats") or {}).get("chars")     or {}
        snt  = (s.get("token_stats") or {}).get("sentences") or {}
        ts   = s.get("token_stats") or {}
        tt   = s.get("text_types")  or {}
        per  = s.get("periodo")     or {}

        livre    = tt.get("livre",    {})
        template = tt.get("template", {})

        rows.append({
            "Tipo de Documento":              doc_type.capitalize(),
            "Total de Registros":             s.get("n_total"),
            "Pacientes Únicos":               s.get("n_pacientes_unicos"),
            "Período (início)":               per.get("min"),
            "Período (fim)":                  per.get("max"),
            "Hospitais / Unidades":           s.get("n_hospitais"),
            "Docs Vazios":                    s.get("n_vazios"),
            "% Vazios":                       s.get("pct_vazios"),
            "Nº de Documentos":               ts.get("n_docs"),
            "Tokens — Mínimo":                tok.get("min"),
            "Tokens — p25":                   tok.get("p25"),
            "Tokens — Mediana":               tok.get("median"),
            "Tokens — Média":                 tok.get("mean"),
            "Tokens — p75":                   tok.get("p75"),
            "Tokens — Máximo":                tok.get("max"),
            "Chars — Mediana":                chr_.get("median"),
            "Chars — Média":                  chr_.get("mean"),
            "Chars — Máximo":                 chr_.get("max"),
            "Sentenças — Mediana":            snt.get("median"),
            "Docs com quebra de linha":       ts.get("docs_with_newline"),
            "Docs com data no texto":         ts.get("docs_with_date"),
            "Docs com hora no texto":         ts.get("docs_with_time"),
            "% Texto Livre":                  livre.get("pct"),
            "% Template Estruturado":         template.get("pct"),
        })

    tabela1 = pd.DataFrame(rows)
    tabela1.to_csv(output_dir / "tabela1.csv", index=False, encoding="utf-8-sig", sep=";")
    try:
        tabela1.to_excel(output_dir / "tabela1.xlsx", index=False)
    except Exception as exc:
        print(f"  Aviso: não foi possível gerar tabela1.xlsx — {exc}")
    print(f"✓ Tabela 1 salva em '{output_dir}'")
    return tabela1
# Fim - 0) Análise Exploratória - 0.5) Geração de Saídas - 0.5.1) Tabela 1 da dissertação (CSV + Excel)


# Início - 0) Análise Exploratória - 0.5) Geração de Saídas - 0.5.2) Histograma de distribuição de tokens - 0.5.3) Gráfico top especialidades
def gerar_graficos(stats: dict, dfs: dict, output_dir) -> None:
    """
    Gera as figuras da análise exploratória.

    0.5.2 — Figura 1: histograma de distribuição de tokens por tipo de doc.
    0.5.3 — Figura 2: gráfico de barras horizontais das top especialidades.

    Parâmetros
    ----------
    stats      : dict {doc_type: resultado de analyze_document_type()}
    dfs        : dict {doc_type: DataFrame retornado por load_csv()}
    output_dir : str | Path — diretório de saída
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Figura 1 — Histograma de tokens (0.5.2) ────────────────────────────
    text_cols = [
        (dt, _TEXT_COLUMN[dt])
        for dt in dfs
        if _TEXT_COLUMN.get(dt) and _TEXT_COLUMN[dt] in dfs[dt].columns
    ]
    if text_cols:
        fig, axes = plt.subplots(1, len(text_cols), figsize=(7 * len(text_cols), 5))
        if len(text_cols) == 1:
            axes = [axes]
        for ax, (doc_type, col) in zip(axes, text_cols):
            counts = dfs[doc_type][col].fillna("").apply(count_tokens)
            p99    = counts.quantile(0.99)           # corta outliers extremos
            sns.histplot(
                counts[counts <= p99], bins=50, kde=True,
                ax=ax, color="#4C72B0",
            )
            ax.set_title(
                f"{doc_type.capitalize()}\n"
                f"(n={len(counts):,} · mediana={int(counts.median())} tokens)",
                fontsize=11,
            )
            ax.set_xlabel("Nº de tokens por documento")
            ax.set_ylabel("Frequência")
            ax.xaxis.set_major_formatter(
                mticker.FuncFormatter(lambda x, _: f"{int(x):,}")
            )
        fig.suptitle(
            "Distribuição de Tokens por Documento",
            fontsize=13, fontweight="bold",
        )
        fig.tight_layout()
        fig.savefig(
            output_dir / "figura1_distribuicao_tokens.png",
            dpi=150, bbox_inches="tight",
        )
        plt.close(fig)
        print("✓ Figura 1 salva: figura1_distribuicao_tokens.png")

    # ── Figura 2 — Top especialidades (0.5.3) ─────────────────────────────
    for doc_type, s in stats.items():
        top = s.get("top_especialidades", [])
        if not top:
            continue
        labels  = [r["especialidade"] for r in top]
        valores = [r["total"]         for r in top]
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.barh(labels[::-1], valores[::-1], color="#55A868", alpha=0.85)
        ax.set_xlabel("Número de Registros")
        ax.set_title(
            f"Top Especialidades — {doc_type.capitalize()}",
            fontsize=12, fontweight="bold",
        )
        ax.xaxis.set_major_formatter(
            mticker.FuncFormatter(lambda x, _: f"{int(x):,}")
        )
        # Rótulo com valor em cada barra
        for bar, val in zip(ax.patches, valores[::-1]):
            ax.text(
                bar.get_width() + max(valores) * 0.01,
                bar.get_y() + bar.get_height() / 2,
                f"{val:,}", va="center", fontsize=8,
            )
        fig.tight_layout()
        out = output_dir / f"figura2_top_especialidades_{doc_type}.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"✓ Figura 2 salva: {out.name}")
# Fim - 0) Análise Exploratória - 0.5) Geração de Saídas - 0.5.2) Histograma de distribuição de tokens - 0.5.3) Gráfico top especialidades


# Início - 0) Análise Exploratória - 0.5) Geração de Saídas - 0.5.4) Exportação JSON com stats completas
def save_stats_json(stats: dict, output_dir) -> Path:
    """
    Persiste o dict de stats em JSON para consumo pela view Django.

    Estrutura salva:
    {
      "generated_at": "2026-05-15T10:00:00",
      "doc_types": {
        "prescricoes": { ...resultado de analyze_document_type()... },
        "pareceres":   { ...resultado de analyze_document_type()... }
      }
    }

    Lido por load_stats_json() sem reprocessar o dataset (10M+ registros).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "generated_at": datetime.datetime.now().isoformat(),
        "doc_types":    stats,
    }
    json_path = output_dir / "stats.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    print(f"✓ stats.json salvo: {json_path}")
    return json_path


def load_stats_json(output_dir) -> dict | None:
    """
    Lê o stats.json gerado por save_stats_json().
    Retorna None se o arquivo não existir (análise ainda não executada).
    """
    json_path = Path(output_dir) / "stats.json"
    if not json_path.exists():
        return None
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)
# Fim - 0) Análise Exploratória - 0.5) Geração de Saídas - 0.5.4) Exportação JSON com stats completas


# ══════════════════════════════════════════════════════════════════════════════
# CLI — ponto de entrada via terminal / notebook
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Etapa 0 — Análise exploratória do corpus clínico",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplo:\n"
            "  python src/analysis/exploratory.py \\\n"
            "      --prescricoes data/raw/prescricoes.csv \\\n"
            "      --pareceres   data/raw/pareceres.csv\n\n"
            "Saídas geradas em --output:\n"
            "  stats.json                             (lido pelas views Django)\n"
            "  tabela1.csv + tabela1.xlsx             (0.5.1)\n"
            "  figura1_distribuicao_tokens.png        (0.5.2)\n"
            "  figura2_top_especialidades_*.png       (0.5.3)"
        ),
    )
    parser.add_argument(
        "--prescricoes", required=True,
        help="Caminho para o CSV de prescrições",
    )
    parser.add_argument(
        "--pareceres", required=True,
        help="Caminho para o CSV de pareceres",
    )
    parser.add_argument(
        "--output", default="outputs/exploratory_analysis",
        help="Diretório de saída (default: outputs/exploratory_analysis)",
    )
    parser.add_argument(
        "--nrows", type=int, default=None,
        help="Limitar a N linhas por CSV (útil para testes rápidos)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("0) Análise Exploratória do Corpus Clínico")
    print("=" * 60)

    # 0.1 — Leitura dos CSVs
    print("\n[0.1] Carregando CSVs...")
    df_presc = load_csv(args.prescricoes, "prescricoes", nrows=args.nrows)
    df_par   = load_csv(args.pareceres,   "pareceres",   nrows=args.nrows)

    # 0.2 + 0.3 + 0.4 — Análise por tipo de documento
    print("\n[0.2 → 0.4] Calculando estatísticas...")
    stats_presc = analyze_document_type(df_presc, "prescricoes")
    stats_par   = analyze_document_type(df_par,   "pareceres")
    stats_all   = {"prescricoes": stats_presc, "pareceres": stats_par}

    # 0.5 — Geração de saídas
    print("\n[0.5] Gerando saídas...")
    gerar_tabela1(stats_all, args.output)
    gerar_graficos(stats_all, {"prescricoes": df_presc, "pareceres": df_par}, args.output)
    save_stats_json(stats_all, args.output)

    print(f"\n✓ Etapa 0 concluída. Saídas em: {args.output}")
