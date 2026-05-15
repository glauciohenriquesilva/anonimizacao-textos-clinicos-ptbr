"""
Substituição de Entidades PHI — Anonimização
===============================================
Etapa final do pipeline: substitui entidades identificadas pelo NER
por marcadores padronizados (marker substitution).

Decisão de projeto: usar substituição por marcadores (ex.: [PESSOA_1])
em vez de surrogates (substituição por valores sintéticos),
pois o objetivo é anonimização para pesquisa, não re-identificação simulada.
Ver docs/07_decisoes/decisoes_anonimizacao.md.

Mapeamento de marcadores:
    PESSOA       → [PESSOA_N]
    DOCUMENTO    → [DOCUMENTO_N]
    ENDEREÇO     → [ENDEREÇO_N]
    CONTATO      → [CONTATO_N]
    DATA         → [DATA_N]
    HORA         → [HORA_N]
    INSTITUIÇÃO  → [INSTITUIÇÃO_N]
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AnonymizationRecord:
    """Registro de uma substituição PHI realizada."""
    entity_type: str
    original_text: str
    marker: str
    start: int
    end: int


@dataclass
class AnonymizationResult:
    """Resultado completo da anonimização de um documento."""
    original_text: str
    anonymized_text: str
    replacements: list[AnonymizationRecord] = field(default_factory=list)
    n_phi_found: int = 0

    @property
    def phi_types_found(self) -> set[str]:
        return {r.entity_type for r in self.replacements}

    def summary(self) -> str:
        lines = [
            f"PHI encontrado: {self.n_phi_found}",
            f"Tipos: {', '.join(sorted(self.phi_types_found))}",
        ]
        for r in self.replacements:
            lines.append(f"  [{r.entity_type}] '{r.original_text}' → '{r.marker}'")
        return "\n".join(lines)


class MarkerSubstitutor:
    """
    Substitui entidades PHI por marcadores padronizados.

    Modo de operação:
      - Recebe texto original + lista de spans PHI (saída do NER)
      - Substitui cada span por [TIPO_N] onde N é um contador por tipo
      - Preserva entidades de utilidade clínica (MEDICAMENTO, DOSE, etc.)

    Uso:
        substitutor = MarkerSubstitutor()
        result = substitutor.anonymize(texto, spans_phi)
        print(result.anonymized_text)
    """

    # Início - 3) Anonimização - 3.1) Substituição por Marcadores - 3.1.1) Filtragem de entidades PHI
    # Tipos PHI que devem ser anonimizados
    PHI_TYPES = {
        "PESSOA", "DOCUMENTO", "ENDEREÇO", "CONTATO",
        "DATA", "HORA", "INSTITUIÇÃO",
    }
    # Fim - 3) Anonimização - 3.1) Substituição por Marcadores - 3.1.1) Filtragem de entidades PHI

    def __init__(
        self,
        consistent_mapping: bool = True,
        preserve_dates_format: bool = False,
    ):
        """
        Args:
            consistent_mapping: Se True, o mesmo texto original sempre recebe
                                 o mesmo marcador no documento (ex.: "João Silva"
                                 sempre → [PESSOA_1]).
            preserve_dates_format: Se True, substitui data por [DATA_DD/MM/AAAA]
                                   em vez de [DATA_N] (para estudos de utilidade).
        """
        self.consistent_mapping = consistent_mapping
        self.preserve_dates_format = preserve_dates_format
        self._reset_counters()

    def _reset_counters(self) -> None:
        self._counters: dict[str, int] = defaultdict(int)
        self._text_to_marker: dict[str, str] = {}

    # Início - 3) Anonimização - 3.1) Substituição por Marcadores - 3.1.2) Geração de marcadores por tipo de entidade
    def _get_marker(self, entity_type: str, original_text: str) -> str:
        """Retorna o marcador para uma entidade, criando se não existir."""
        if self.consistent_mapping and original_text in self._text_to_marker:
            return self._text_to_marker[original_text]

        self._counters[entity_type] += 1
        n = self._counters[entity_type]

        if entity_type == "DATA" and self.preserve_dates_format:
            # Substitui por placeholder de formato genérico
            marker = "[DATA_DD/MM/AAAA]"
        else:
            marker = f"[{entity_type}_{n}]"

        if self.consistent_mapping:
            self._text_to_marker[original_text] = marker

        return marker
    # Fim - 3) Anonimização - 3.1) Substituição por Marcadores - 3.1.2) Geração de marcadores por tipo de entidade

    # Início - 3) Anonimização - 3.1) Substituição por Marcadores - 3.1.3) Substituição de spans PHI no texto
    def anonymize(
        self,
        text: str,
        phi_spans: list[tuple],
        doc_id: Optional[str] = None,
        reset_counters: bool = True,
    ) -> AnonymizationResult:
        """
        Anonimiza um documento substituindo spans PHI por marcadores.

        Args:
            text: Texto original.
            phi_spans: Lista de (entity_type, text, start_char, end_char).
                       Pode ser gerada por bio_to_spans() de labels.py.
            doc_id: Identificador do documento (para logging).
            reset_counters: Se True, reseta contadores por documento.

        Returns:
            AnonymizationResult com texto anonimizado e registro de substituições.
        """
        if reset_counters:
            self._reset_counters()

        if not phi_spans:
            return AnonymizationResult(
                original_text=text,
                anonymized_text=text,
                n_phi_found=0,
            )

        # Filtrar apenas entidades PHI (ignorar utilidade clínica)
        phi_spans_filtered = [
            s for s in phi_spans if s[0] in self.PHI_TYPES
        ]

        # Ordenar por posição de início (reverso para substituição de trás para frente)
        phi_spans_sorted = sorted(phi_spans_filtered, key=lambda s: s[2], reverse=True)

        anonymized = text
        replacements: list[AnonymizationRecord] = []

        for span in phi_spans_sorted:
            entity_type, original_span_text, start, end = span[0], span[1], span[2], span[3]

            # Encontrar posição exata no texto atual (pode ter shifted)
            # Nota: para textos longos, usar substituição baseada em offsets
            marker = self._get_marker(entity_type, original_span_text)

            # Substituição por offset (mais precisa)
            # Ajuste: end+1 para incluir o último char
            text_slice = anonymized[start:end + 1] if end < len(anonymized) else original_span_text

            record = AnonymizationRecord(
                entity_type=entity_type,
                original_text=text_slice,
                marker=marker,
                start=start,
                end=end,
            )
            replacements.append(record)

            # Substituição
            anonymized = anonymized[:start] + marker + anonymized[end + 1:]

        return AnonymizationResult(
            original_text=text,
            anonymized_text=anonymized,
            replacements=list(reversed(replacements)),  # ordem original
            n_phi_found=len(replacements),
        )
    # Fim - 3) Anonimização - 3.1) Substituição por Marcadores - 3.1.3) Substituição de spans PHI no texto

    def anonymize_batch(
        self,
        texts: list[str],
        phi_spans_list: list[list[tuple]],
    ) -> list[AnonymizationResult]:
        """Anonimiza lote de documentos."""
        return [
            self.anonymize(text, spans)
            for text, spans in zip(texts, phi_spans_list)
        ]


# ─── Função de conveniência ───────────────────────────────────────────────────

def anonymize_document(
    text: str,
    phi_spans: list[tuple],
    consistent_mapping: bool = True,
) -> str:
    """
    Função de conveniência para anonimização simples.

    Returns:
        Texto anonimizado.
    """
    substitutor = MarkerSubstitutor(consistent_mapping=consistent_mapping)
    result = substitutor.anonymize(text, phi_spans)
    return result.anonymized_text
