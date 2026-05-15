"""
Segmentação de textos clínicos
================================
Etapa 2 do pré-processamento: divide o texto em sentenças clínicas.

Desafio específico do domínio:
  - Abreviações médicas causam falsos positivos em delimitadores de sentenças
    (ex.: "p.c.", "v.o.", "mg.", "ml.")
  - Templates estruturados (UTI) devem ser segmentados por linha/campo
  - Notas narrativas livres seguem segmentação por pontuação + quebras de linha

Decisão: usar spaCy pt_core_news_sm como base e sobrescrever regras para
abreviações médicas. Ver docs/07_decisoes/decisoes_preprocessamento.md.
"""

from __future__ import annotations

import re
from typing import Optional

# Início - 1) Pré-processamento - 1.3) Segmentação - 1.3.2) Proteção de abreviações médicas
# Abreviações que NÃO devem terminar sentenças (causariam falsos positivos)
MEDICAL_ABBREV_NO_SPLIT = {
    # Vias de administração
    "v.o", "v.o.", "e.v", "e.v.", "i.v", "i.v.", "s.c", "s.c.", "i.m", "i.m.",
    "s.l", "s.l.",
    # Unidades
    "mg", "ml", "mcg", "mEq", "g", "kg", "l",
    # Abreviações comuns
    "Dr", "Dr.", "Dra", "Dra.", "Enf", "Enf.",
    "Sr", "Sr.", "Sra", "Sra.",
    "p.c", "p.c.",      # per os / posição corporal
    # Numérico
    "n.o", "n.º",
}

# Regex para ponto seguido de maiúscula que *não* é separador de sentença
# quando precedido de abreviação conhecida
_RE_ABBREV_POINT = re.compile(
    r"(?<!\w)(" + "|".join(re.escape(a) for a in MEDICAL_ABBREV_NO_SPLIT) + r")\."
)
# Fim - 1) Pré-processamento - 1.3) Segmentação - 1.3.2) Proteção de abreviações médicas

# Delimitadores de sentença: "." "!" "?" seguidos de espaço+maiúscula, ou "\n\n"
_RE_SENT_DELIM = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÀÂÊÔÃÕÇ])")

# Separador de campo em templates (ex.: "SISTEMA NEUROLÓGICO: ...")
_RE_TEMPLATE_FIELD = re.compile(
    r"^([A-ZÁÉÍÓÚÀÂÊÔÃÕÇ\s/]+):(.+)$", re.MULTILINE
)


class ClinicalSegmenter:
    """
    Segmenta textos clínicos em sentenças, com tratamento diferenciado
    para texto livre e templates estruturados.

    Uso:
        segmenter = ClinicalSegmenter()
        sentences = segmenter.segment(texto_normalizado, text_type="texto_livre")

    Nota:
        Se spaCy estiver disponível e o modelo pt_core_news_sm instalado,
        use spacy_segment() para segmentação mais precisa.
    """

    def __init__(self, use_spacy: bool = False):
        self.use_spacy = use_spacy
        self._nlp = None
        if use_spacy:
            self._nlp = self._load_spacy()

    @staticmethod
    def _load_spacy():
        """Carrega modelo spaCy pt_core_news_sm."""
        try:
            import spacy
            nlp = spacy.load("pt_core_news_sm")
            return nlp
        except (ImportError, OSError) as e:
            raise RuntimeError(
                "spaCy não encontrado ou modelo pt_core_news_sm não instalado.\n"
                "Execute: python -m spacy download pt_core_news_sm\n"
                f"Erro: {e}"
            )

    # Início - 1) Pré-processamento - 1.3) Segmentação - 1.3.3) Segmentação de texto livre clínico
    # Início - 1) Pré-processamento - 1.3) Segmentação - 1.3.5) Filtragem de segmentos curtos (mínimo 2 tokens)
    def segment_free_text(self, text: str) -> list[str]:
        """
        Segmenta texto clínico narrativo livre.

        Estratégia:
          1. Protege abreviações conhecidas (substitui '.' temporariamente)
          2. Divide por delimitadores de sentença
          3. Divide por quebra dupla de linha
          4. Restaura abreviações
          5. Filtra sentenças vazias / muito curtas
        """
        # Proteger abreviações
        protected = _RE_ABBREV_POINT.sub(
            lambda m: m.group(0).replace(".", "§PONTO§"), text
        )

        # Dividir por pontuação de fim de sentença + maiúscula
        segments = _RE_SENT_DELIM.split(protected)

        # Dividir por dupla quebra de linha
        final_segments = []
        for seg in segments:
            subsegments = re.split(r"\n\n+", seg)
            final_segments.extend(subsegments)

        # Restaurar e limpar
        cleaned = []
        for seg in final_segments:
            seg = seg.replace("§PONTO§", ".").strip()
            if seg and len(seg.split()) >= 2:  # mínimo 2 tokens
                cleaned.append(seg)

        return cleaned
    # Fim - 1) Pré-processamento - 1.3) Segmentação - 1.3.3) Segmentação de texto livre clínico
    # Fim - 1) Pré-processamento - 1.3) Segmentação - 1.3.5) Filtragem de segmentos curtos (mínimo 2 tokens)

    # Início - 1) Pré-processamento - 1.3) Segmentação - 1.3.4) Segmentação de template estruturado
    # Início - 1) Pré-processamento - 1.3) Segmentação - 1.3.5) Filtragem de segmentos curtos (mínimo 2 tokens)
    def segment_template(self, text: str) -> list[str]:
        """
        Segmenta templates estruturados (formulários UTI/enfermagem).

        Estratégia: uma sentença por linha não vazia; agrupa campo+valor.
        """
        lines = text.split("\n")
        segments = []
        current = []

        for line in lines:
            line = line.strip()
            if not line:
                if current:
                    segments.append(" ".join(current))
                    current = []
            else:
                current.append(line)

        if current:
            segments.append(" ".join(current))

        return [s for s in segments if len(s.split()) >= 2]
    # Fim - 1) Pré-processamento - 1.3) Segmentação - 1.3.4) Segmentação de template estruturado
    # Fim - 1) Pré-processamento - 1.3) Segmentação - 1.3.5) Filtragem de segmentos curtos (mínimo 2 tokens)

    def segment(self, text: str, text_type: str = "texto_livre") -> list[str]:
        """
        Segmenta o texto conforme o tipo detectado.

        Args:
            text: Texto normalizado.
            text_type: 'texto_livre' ou 'template_estruturado'.

        Returns:
            Lista de sentenças/segmentos.
        """
        if not text or not text.strip():
            return []

        if self.use_spacy and self._nlp is not None:
            return self.spacy_segment(text)

        if text_type == "template_estruturado":
            return self.segment_template(text)
        return self.segment_free_text(text)

    def spacy_segment(self, text: str) -> list[str]:
        """Segmenta usando pipeline spaCy (mais preciso, mais lento)."""
        doc = self._nlp(text)
        return [sent.text.strip() for sent in doc.sents if sent.text.strip()]

    def segment_batch(
        self, texts: list[str], text_types: Optional[list[str]] = None
    ) -> list[list[str]]:
        """Aplica segment() a uma lista de textos."""
        if text_types is None:
            text_types = ["texto_livre"] * len(texts)
        return [
            self.segment(t, tt) for t, tt in zip(texts, text_types)
        ]
