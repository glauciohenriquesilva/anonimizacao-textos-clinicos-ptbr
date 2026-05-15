"""
Métricas de Avaliação — Framework TILD
=========================================
Implementa as métricas do framework TILD (Schiezaro et al., 2026):

    T — Técnica: Precision / Recall / F1 (seqeval, entity-level)
    I — Informacional: ΔF1 = F1_anonimizado − F1_original (downstream NER)
    L — Legal: Coverage / Precision_anon (taxa de PHI anonimizado)
    D — (implícita) Documentação e rastreabilidade

Métricas complementares (Pissarra et al., 2024):
    ALID  — Anonimização com perda de informação mínima
    LR    — Levenshtein Ratio
    LRDI  — LR com inserções/deleções
    LRQI  — LR quantificado por instâncias

Métricas de concordância inter-anotadores:
    Cohen's Kappa (κ) — meta: κ ≥ 0.80
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ─── Estrutura de resultados ──────────────────────────────────────────────────

@dataclass
class NERMetricResult:
    """Resultado de avaliação NER (dimensão T do framework TILD)."""
    precision: float
    recall: float
    f1: float
    support: int = 0
    per_entity: dict[str, dict] = None   # F1 por tipo de entidade

    def __str__(self) -> str:
        return (
            f"P={self.precision:.4f}  R={self.recall:.4f}  "
            f"F1={self.f1:.4f}  support={self.support}"
        )


@dataclass
class AnonymizationMetricResult:
    """Resultado de avaliação de anonimização (dimensões I + L do TILD)."""
    # Dimensão T (NER na saída anonimizada)
    ner_on_anonymized: Optional[NERMetricResult] = None

    # Dimensão I — Informacional (utilidade clínica preservada)
    f1_original: float = 0.0            # F1 do downstream task no texto original
    f1_anonymized: float = 0.0          # F1 do downstream task no texto anonimizado
    delta_f1: float = 0.0               # ΔF1 = F1_anon − F1_orig (quanto perdeu)

    # Dimensão L — Legal (cobertura de PHI)
    phi_coverage: float = 0.0           # % de PHI anonimizado
    phi_precision_anon: float = 0.0     # % de tokens anonimizados que eram PHI

    # Levenshtein (Pissarra et al. 2024)
    alid: Optional[float] = None
    lr: Optional[float] = None

    def __str__(self) -> str:
        return (
            f"ΔF1={self.delta_f1:+.4f} | "
            f"Coverage={self.phi_coverage:.2%} | "
            f"Prec_anon={self.phi_precision_anon:.2%}"
        )


# ─── Métricas NER (seqeval) ───────────────────────────────────────────────────

class NERMetrics:
    """Calcula métricas NER entity-level usando seqeval."""

    # Início - 2) NER - 2.4) Avaliação - 2.4.2) Cálculo de Precision, Recall e F1 (seqeval / entity-level)
    # Início - 2) NER - 2.4) Avaliação - 2.4.3) Relatório de F1 por tipo de entidade
    @staticmethod
    def compute_seqeval(
        y_true: list[list[str]],
        y_pred: list[list[str]],
        per_entity: bool = True,
    ) -> dict:
        """
        Calcula P/R/F1 usando seqeval (entity-level, schema BIO).

        Args:
            y_true: Rótulos reais (lista de listas de strings BIO).
            y_pred: Rótulos preditos (lista de listas de strings BIO).
            per_entity: Se True, inclui F1 por tipo de entidade.

        Returns:
            Dicionário com overall_precision, overall_recall, overall_f1,
            e (opcionalmente) per_entity_f1.
        """
        try:
            from seqeval.metrics import (
                precision_score, recall_score, f1_score, classification_report
            )
        except ImportError:
            raise RuntimeError("seqeval não instalado. Execute: pip install seqeval")

        result = {
            "overall_precision": precision_score(y_true, y_pred),
            "overall_recall":    recall_score(y_true, y_pred),
            "overall_f1":        f1_score(y_true, y_pred),
        }

        if per_entity:
            report = classification_report(y_true, y_pred, output_dict=True)
            result["per_entity"] = {
                k: v for k, v in report.items()
                if k not in ("micro avg", "macro avg", "weighted avg")
            }

        return result
    # Fim - 2) NER - 2.4) Avaliação - 2.4.2) Cálculo de Precision, Recall e F1 (seqeval / entity-level)
    # Fim - 2) NER - 2.4) Avaliação - 2.4.3) Relatório de F1 por tipo de entidade

    # Início - 2) NER - 2.1) Anotação Gold Standard - 2.1.5) Concordância inter-anotadores (Cohen's Kappa)
    @staticmethod
    def compute_cohen_kappa(
        annot1: list[str], annot2: list[str]
    ) -> float:
        """
        Calcula Cohen's Kappa entre dois anotadores.

        Args:
            annot1: Rótulos do anotador 1.
            annot2: Rótulos do anotador 2.

        Returns:
            Kappa (float). Meta: κ ≥ 0.80.
        """
        try:
            from sklearn.metrics import cohen_kappa_score
        except ImportError:
            raise RuntimeError("scikit-learn não instalado.")
        return float(cohen_kappa_score(annot1, annot2))
    # Fim - 2) NER - 2.1) Anotação Gold Standard - 2.1.5) Concordância inter-anotadores (Cohen's Kappa)


# ─── Métricas de anonimização ─────────────────────────────────────────────────

class AnonymizationMetrics:
    """
    Calcula métricas do framework TILD para avaliação da anonimização.
    """

    # Início - 3) Anonimização - 3.2) Avaliação - 3.2.1) Cobertura de PHI anonimizado (Coverage)
    # Início - 3) Anonimização - 3.2) Avaliação - 3.2.2) Precisão da anonimização (Precision_anon)
    @staticmethod
    def compute_phi_coverage(
        phi_spans_original: list[tuple],
        phi_spans_anonymized: list[tuple],
    ) -> tuple[float, float]:
        """
        Calcula Coverage (recall de PHI anonimizado) e Precision_anon.

        Args:
            phi_spans_original: Spans de PHI no texto original [(tipo, texto, start, end)].
            phi_spans_anonymized: Spans modificados após anonimização.

        Returns:
            (coverage, precision_anon)
        """
        if not phi_spans_original:
            return 1.0, 1.0

        original_set = {(s[0], s[1]) for s in phi_spans_original}
        anonymized_set = {(s[0], s[1]) for s in phi_spans_anonymized}

        # Coverage: quantos PHI originais foram substituídos
        covered = len(original_set - anonymized_set)
        coverage = covered / len(original_set)

        # Precision_anon: dos spans modificados, quantos eram PHI reais
        if not anonymized_set:
            precision = 1.0
        else:
            true_phi_modified = len(original_set - anonymized_set)
            precision = true_phi_modified / len(anonymized_set) if anonymized_set else 1.0

        return coverage, precision
    # Fim - 3) Anonimização - 3.2) Avaliação - 3.2.1) Cobertura de PHI anonimizado (Coverage)
    # Fim - 3) Anonimização - 3.2) Avaliação - 3.2.2) Precisão da anonimização (Precision_anon)

    # Início - 3) Anonimização - 3.2) Avaliação - 3.2.3) ΔF1 — Preservação de utilidade clínica
    @staticmethod
    def compute_delta_f1(
        f1_original: float, f1_anonymized: float
    ) -> float:
        """
        Calcula ΔF1 = F1_anonimizado − F1_original.

        Valores próximos de 0 indicam preservação da utilidade clínica.
        Valores muito negativos indicam perda de informação clínica.

        Referência: Schiezaro et al. (2026) — métrica central do TILD.
        """
        return f1_anonymized - f1_original
    # Fim - 3) Anonimização - 3.2) Avaliação - 3.2.3) ΔF1 — Preservação de utilidade clínica

    # Início - 3) Anonimização - 3.3) Relatório - 3.3.3) Levenshtein Ratio (LR)
    @staticmethod
    def compute_levenshtein_ratio(original: str, anonymized: str) -> float:
        """
        Calcula razão de Levenshtein (LR) entre texto original e anonimizado.

        Referência: Pissarra et al. (2024) — ALID, LR, LRDI, LRQI.

        Returns:
            LR ∈ [0, 1] onde 1 = textos idênticos, 0 = completamente diferentes.
        """
        try:
            from Levenshtein import ratio  # python-Levenshtein
        except ImportError:
            # Fallback simples (lento para textos grandes)
            return _levenshtein_ratio_simple(original, anonymized)
        return ratio(original, anonymized)
    # Fim - 3) Anonimização - 3.3) Relatório - 3.3.3) Levenshtein Ratio (LR)

    def compute_all(
        self,
        y_true: list[list[str]],
        y_pred: list[list[str]],
        f1_original: float,
        f1_anonymized: float,
        phi_spans_original: list[tuple],
        phi_spans_anonymized: list[tuple],
        original_text: Optional[str] = None,
        anonymized_text: Optional[str] = None,
    ) -> AnonymizationMetricResult:
        """Calcula todas as métricas TILD de uma vez."""
        ner_result_dict = NERMetrics.compute_seqeval(y_true, y_pred)
        ner_result = NERMetricResult(
            precision=ner_result_dict["overall_precision"],
            recall=ner_result_dict["overall_recall"],
            f1=ner_result_dict["overall_f1"],
            per_entity=ner_result_dict.get("per_entity"),
        )

        coverage, prec_anon = self.compute_phi_coverage(phi_spans_original, phi_spans_anonymized)
        delta_f1 = self.compute_delta_f1(f1_original, f1_anonymized)

        lr = None
        if original_text and anonymized_text:
            lr = self.compute_levenshtein_ratio(original_text, anonymized_text)

        return AnonymizationMetricResult(
            ner_on_anonymized=ner_result,
            f1_original=f1_original,
            f1_anonymized=f1_anonymized,
            delta_f1=delta_f1,
            phi_coverage=coverage,
            phi_precision_anon=prec_anon,
            lr=lr,
        )


# ─── Utilitário fallback ──────────────────────────────────────────────────────

def _levenshtein_ratio_simple(s1: str, s2: str) -> float:
    """Levenshtein ratio simples (sem dependências externas, lento)."""
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    len1, len2 = len(s1), len(s2)
    dp = list(range(len2 + 1))

    for i in range(1, len1 + 1):
        prev = i
        for j in range(1, len2 + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            curr = min(dp[j] + 1, prev + 1, dp[j - 1] + cost)
            dp[j - 1] = prev
            prev = curr
        dp[len2] = prev

    distance = dp[len2]
    return 1.0 - distance / max(len1, len2)
