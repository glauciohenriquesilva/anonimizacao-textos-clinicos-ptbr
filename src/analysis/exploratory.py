"""
Análise exploratória do corpus clínico.

Etapa 0 do pipeline — tarefas 0.1 a 0.5:
  0.1  Leitura e validação dos CSVs
  0.2  Estatísticas descritivas
  0.3  Distribuição de tokens, caracteres e sentenças
  0.4  Classificação do tipo de texto (livre vs. template)
  0.5  Geração de saídas (Tabela 1, histograma, gráfico, JSON)
"""

import json
import re
from pathlib import Path

import matplotlib
matplotlib.use('Agg')   # backend não-interativo — obrigatório fora do main thread

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
import seaborn as sns

# ──────────────────────────────────────────────────────────────────────────────
# Schema esperado
# ──────────────────────────────────────────────────────────────────────────────

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

# ──────────────────────────────────────────────────────────────────────────────
# Padrões que indicam template estruturado
# ──────────────────────────────────────────────────────────────────────────────

_TEMPLATE_PATTERNS = [
    r"^#\s+\w",            # linhas iniciando com # (ex: # HDA:, # ORTOPEDIA)
    r"\(\s*[XxSs]\s*\)",   # checkboxes: ( X ) ( S )
    r"SINAIS VITAIS\s*:",
    r"\bPA\s*:",
    r"\bFC\s*:",
    r"\bSAT\s*:",
    r"\bTAX\s*:",
    r"\bFR\s*:",
]
_TEMPLATE_RE = re.compile("|".join(_TEMPLATE_PATTERNS), re.MULTILINE)

# Padrões para detecção de PHI no texto
_DATE_RE = re.compile(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b')
_TIME_RE = re.compile(r'\b\d{1,2}:\d{2}\b')

# ──────────────────────────────────────────────────────────────────────────────
# 0.1) Leitura e validação
# ──────────────────────────────────────────────────────────────────────────────

def load_csv(path: Path, expected_columns: list[str]) -> pd.DataFrame:
    """
    Lê um CSV clínico (sep=';', UTF-8 com BOM) e valida o schema.

    Parâmetros
    ----------
    path : caminho do arquivo CSV
    expected_columns : colunas que devem estar presentes

    Retorna
    -------
    DataFrame com dt_atendimento convertido para datetime.

    Lança
    -----
    ValueError se alguma coluna esperada estiver ausente.
    FileNotFoundError se o arquivo não existir.
    """
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

    df = pd.read_csv(
        path,
        sep=";",
        encoding="utf-8-sig",
        dtype=str,
        low_memory=False,
    )
    df.columns = [c.strip() for c in df.columns]

    missing = [c for c in expected_columns if c not in df.columns]
    if missing:
        raise ValueError(f"Colunas ausentes em '{path.name}': {missing}")

    df["dt_atendimento"] = pd.to_datetime(
        df["dt_atendimento"], format="%d/%m/%Y", errors="coerce"
    )

    # Garante que a coluna de texto não seja NaN
    text_col = "ds_evolucao" if "ds_evolucao" in df.columns else "ds_parecer"
    df[text_col] = df[text_col].fillna("")

    return df


# ──────────────────────────────────────────────────────────────────────────────
# 0.3) Helpers de métricas textuais
# ──────────────────────────────────────────────────────────────────────────────

def count_tokens(text: str) -> int:
    """Conta tokens por split simples em espaços."""
    return len(text.split()) if isinstance(text, str) else 0


def count_chars(text: str) -> int:
    """Conta caracteres totais do texto."""
    return len(text) if isinstance(text, str) else 0


def count_sentences(text: str) -> int:
    """
    Estima o número de sentenças contando linhas não-vazias.
    Adequado para textos clínicos com quebras de linha explícitas.
    """
    if not isinstance(text, str) or not text.strip():
        return 0
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return max(len(lines), 1)


# ──────────────────────────────────────────────────────────────────────────────
# 0.4) Classificação do tipo de texto
# ──────────────────────────────────────────────────────────────────────────────

def classify_text_type(text: str) -> str:
    """
    Classifica o texto como 'template', 'livre' ou 'vazio'.

    Critério: presença de marcadores estruturais típicos de formulários
    clínicos (cabeçalhos com #, checkboxes, campos de sinais vitais).
    """
    if not isinstance(text, str) or not text.strip():
        return "vazio"
    return "template" if _TEMPLATE_RE.search(text) else "livre"


# ──────────────────────────────────────────────────────────────────────────────
# Classe principal
# ──────────────────────────────────────────────────────────────────────────────

class ExploratoryAnalysis:
    """
    Orquestra a análise exploratória completa do corpus clínico.

    Exemplo de uso
    --------------
    >>> ea = ExploratoryAnalysis(
    ...     path_prescricoes="data/raw/prescricoes.csv",
    ...     path_pareceres="data/raw/pareceres.csv",
    ... )
    >>> stats = ea.run()
    """

    def __init__(
        self,
        path_prescricoes: str | Path,
        path_pareceres:   str | Path,
        output_dir:       str | Path = "outputs/exploratory_analysis",
    ):
        self.path_prescricoes = Path(path_prescricoes)
        self.path_pareceres   = Path(path_pareceres)
        self.output_dir       = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.df_presc:  pd.DataFrame | None = None
        self.df_par:    pd.DataFrame | None = None
        self._combined: pd.DataFrame | None = None
        self.stats: dict = {}

    # ── 0.1 ──────────────────────────────────────────────────────────────────

    def load(self) -> None:
        """0.1) Lê e valida os dois CSVs."""
        print("0.1) Carregando CSVs...")
        self.df_presc = load_csv(self.path_prescricoes, COLUMNS_PRESCRICOES)
        self.df_par   = load_csv(self.path_pareceres,   COLUMNS_PARECERES)
        print(f"     Prescrições : {len(self.df_presc):>10,} registros")
        print(f"     Pareceres   : {len(self.df_par):>10,} registros")

    # ── 0.2 ──────────────────────────────────────────────────────────────────

    def descriptive_stats(self) -> dict:
        """0.2) Estatísticas descritivas do corpus."""
        print("0.2) Calculando estatísticas descritivas...")

        self._combined = pd.concat(
            [
                self.df_presc.assign(doc_type="prescricao"),
                self.df_par.assign(doc_type="parecer"),
            ],
            ignore_index=True,
        )

        # 0.2.1 — contagem por tipo
        counts = self._combined["doc_type"].value_counts().to_dict()

        # 0.2.2 — pacientes únicos
        unique_patients = int(self._combined["cd_paciente"].nunique())

        # 0.2.3 — período coberto
        dt_min = self._combined["dt_atendimento"].min()
        dt_max = self._combined["dt_atendimento"].max()

        # 0.2.4 — top 10 especialidades
        top_esp = (
            self._combined["ds_especialid_atendimento"]
            .str.strip()
            .value_counts()
            .head(10)
            .to_dict()
        )

        # 0.2.5 — hospitais únicos
        n_hospitais = int(
            self._combined["ds_multi_empresa"]
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .nunique()
        )

        stats = {
            "total_registros":    len(self._combined),
            "total_prescricoes":  counts.get("prescricao", 0),
            "total_pareceres":    counts.get("parecer", 0),
            "pacientes_unicos":   unique_patients,
            "periodo_inicio":     dt_min.strftime("%d/%m/%Y") if pd.notna(dt_min) else "N/A",
            "periodo_fim":        dt_max.strftime("%d/%m/%Y") if pd.notna(dt_max) else "N/A",
            "top_especialidades": top_esp,
            "total_hospitais":    n_hospitais,
        }
        self.stats.update(stats)
        return stats

    # ── 0.3 ──────────────────────────────────────────────────────────────────

    def token_distribution(self) -> dict:
        """0.3) Distribuição de tokens, caracteres, sentenças e PHI por tipo de doc."""
        print("0.3) Calculando distribuição de tokens...")

        results = {}
        for doc_type, df, text_col in [
            ("prescricao", self.df_presc, "ds_evolucao"),
            ("parecer",    self.df_par,   "ds_parecer"),
        ]:
            tokens = df[text_col].apply(count_tokens)
            chars  = df[text_col].apply(count_chars)
            sents  = df[text_col].apply(count_sentences)

            def _summary(s: pd.Series) -> dict:
                return {
                    "min":    int(s.min()),
                    "p25":    round(float(s.quantile(0.25)), 1),
                    "median": round(float(s.median()), 1),
                    "mean":   round(float(s.mean()), 1),
                    "p75":    round(float(s.quantile(0.75)), 1),
                    "max":    int(s.max()),
                }

            results[doc_type] = {
                "tokens":    _summary(tokens),
                "chars":     _summary(chars),
                "sentences": _summary(sents),
                "unique_texts":      int(df[text_col].nunique()),
                "docs_with_newline": int(df[text_col].str.contains(r'\n', regex=False, na=False).sum()),
                "docs_with_date":    int(df[text_col].apply(lambda t: bool(_DATE_RE.search(t)) if isinstance(t, str) else False).sum()),
                "docs_with_time":    int(df[text_col].apply(lambda t: bool(_TIME_RE.search(t)) if isinstance(t, str) else False).sum()),
            }

            df["_n_tokens"]    = tokens
            df["_n_chars"]     = chars
            df["_n_sentences"] = sents

        # fora do for — processa ambos os tipos antes de retornar
        self.stats["token_distribution"] = results
        return results
    
    # ── 0.4 ──────────────────────────────────────────────────────────────────

    def classify_text_types(self) -> dict:
        """0.4) Classifica cada documento como texto livre, template ou vazio."""
        print("0.4) Classificando tipos de texto...")

        results = {}
        for doc_type, df, text_col in [
            ("prescricao", self.df_presc, "ds_evolucao"),
            ("parecer",    self.df_par,   "ds_parecer"),
        ]:
            df["_text_type"] = df[text_col].apply(classify_text_type)
            counts = df["_text_type"].value_counts()
            total  = len(df)
            results[doc_type] = {
                t: {"count": int(n), "pct": round(100 * n / total, 1)}
                for t, n in counts.items()
            }

        self.stats["text_types"] = results
        return results

    # ── 0.5 ──────────────────────────────────────────────────────────────────

    def generate_outputs(self) -> None:
        """0.5) Gera todos os arquivos de saída."""
        print("0.5) Gerando saídas...")
        self._save_tabela1()
        self._plot_token_histogram()
        self._plot_top_especialidades()
        self._save_json()
        print(f"     Tudo salvo em: {self.output_dir.resolve()}")

    def _save_tabela1(self) -> None:
        """0.5.1) Tabela 1 do anteprojeto — CSV + Excel."""
        td = self.stats.get("token_distribution", {})

        rows = []
        for doc_type, label, n in [
            ("prescricao", f"Prescrições (n={self.stats['total_prescricoes']})", self.stats["total_prescricoes"]),
            ("parecer",    f"Pareceres (n={self.stats['total_pareceres']})",     self.stats["total_pareceres"]),
        ]:
            t = td.get(doc_type, {})
            rows.append({
                "Característica":                      "—",   # preenchida abaixo
                label:                                 "—",
            })

        # Constrói no formato linha × coluna (cada linha é uma característica)
        presc = td.get("prescricao", {})
        par   = td.get("parecer",    {})
        col_p = f"Prescrições (n={self.stats['total_prescricoes']})"
        col_r = f"Pareceres (n={self.stats['total_pareceres']})"

        tabela = [
            ("Textos distintos (sem duplicatas)",  presc.get("unique_texts", "-"),       par.get("unique_texts", "-")),
            ("Mediana da quantidade de caracteres", presc["chars"]["median"],             par["chars"]["median"]),
            ("Média da quantidade de caracteres",   presc["chars"]["mean"],               par["chars"]["mean"]),
            ("Quantidade máxima de caracteres",     presc["chars"]["max"],                par["chars"]["max"]),
            ("Mediana da quantidade de palavras",   presc["tokens"]["median"],            par["tokens"]["median"]),
            ("Documentos com quebra de linha",      presc.get("docs_with_newline", "-"),  par.get("docs_with_newline", "-")),
            ("Ocorrência de datas no texto",        presc.get("docs_with_date", "-"),     par.get("docs_with_date", "-")),
            ("Ocorrência de hora no texto",         presc.get("docs_with_time", "-"),     par.get("docs_with_time", "-")),
        ]

        df_tab = pd.DataFrame(tabela, columns=["Característica", col_p, col_r])
        df_tab.to_csv(  self.output_dir / "tabela1.csv",  index=False, encoding="utf-8-sig")
        df_tab.to_excel(self.output_dir / "tabela1.xlsx", index=False)
        print("     tabela1.csv + tabela1.xlsx")
        
    def _plot_token_histogram(self) -> None:
        """0.5.2) Histograma de distribuição de tokens."""
        fig, axes = plt.subplots(1, 2, figsize=(12, 4))
        for ax, (df, label) in zip(
            axes,
            [(self.df_presc, "Prescrições"), (self.df_par, "Pareceres")],
        ):
            sns.histplot(df["_n_tokens"], bins=30, kde=True, ax=ax, color="#4C72B0")
            ax.set_title(f"Distribuição de Tokens — {label}")
            ax.set_xlabel("Número de tokens")
            ax.set_ylabel("Frequência")
            ax.xaxis.set_major_formatter(
                mticker.FuncFormatter(lambda x, _: f"{int(x):,}")
            )
        plt.tight_layout()
        fig.savefig(self.output_dir / "histograma_tokens.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        print("     histograma_tokens.png")

    def _plot_top_especialidades(self) -> None:
        """0.5.3) Gráfico de barras horizontais — top especialidades."""
        top = self.stats.get("top_especialidades", {})
        if not top:
            return

        labels = list(top.keys())
        values = list(top.values())

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.barh(labels[::-1], values[::-1], color="#55A868")
        ax.set_xlabel("Número de registros")
        ax.set_title("Top Especialidades Médicas")
        ax.xaxis.set_major_formatter(
            mticker.FuncFormatter(lambda x, _: f"{int(x):,}")
        )
        plt.tight_layout()
        fig.savefig(self.output_dir / "top_especialidades.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        print("     top_especialidades.png")

    def _save_json(self) -> None:
        """0.5.4) Exporta todas as estatísticas em JSON."""
        with open(self.output_dir / "stats.json", "w", encoding="utf-8") as f:
            json.dump(self.stats, f, ensure_ascii=False, indent=2, default=str)
        print("     stats.json")

    # ── Ponto de entrada ──────────────────────────────────────────────────────

    def run(self) -> dict:
        """Executa o pipeline completo da Etapa 0 e retorna as estatísticas."""
        self.load()
        self.descriptive_stats()
        self.token_distribution()
        self.classify_text_types()
        self.generate_outputs()
        print("\n✓ Etapa 0 concluída.")
        return self.stats


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Etapa 0 — Análise exploratória do corpus")
    parser.add_argument("--prescricoes", required=True, help="Caminho para prescricoes.csv")
    parser.add_argument("--pareceres",   required=True, help="Caminho para pareceres.csv")
    parser.add_argument("--output", default="outputs/exploratory_analysis")
    args = parser.parse_args()

    ea = ExploratoryAnalysis(
        path_prescricoes=args.prescricoes,
        path_pareceres=args.pareceres,
        output_dir=args.output,
    )
    stats = ea.run()
    print(json.dumps(stats, ensure_ascii=False, indent=2, default=str))