"""
Tokenização de sentenças clínicas
====================================
Etapa 3 do pré-processamento: produz tokens alinhados com o esquema BIO/IOB2
para entrada nos modelos NER.

Suporta dois modos:
  - word: tokenização por espaço/pontuação para CRF
  - subword: tokenização WordPiece via HuggingFace para BERT/mmBERT/ModernBERT

Decisão: BIO (IOB2) como esquema de anotação.
Ver docs/07_decisoes/decisoes_preprocessamento.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Union


# ─── Estruturas de dados ──────────────────────────────────────────────────────

# Início - 1) Pré-processamento - 1.4) Tokenização - 1.4.2) Extração de features por token (metadados clínicos)
@dataclass
class Token:
    """Representa um token com metadados clínicos."""
    text: str
    start: int                          # offset no texto original
    end: int
    is_abbreviation: bool = False
    is_numeric: bool = False
    is_date: bool = False
    label: str = "O"                    # BIO label (definido na anotação)

    def __repr__(self) -> str:
        return f"Token({self.text!r}, {self.label})"
# Fim - 1) Pré-processamento - 1.4) Tokenização - 1.4.2) Extração de features por token (metadados clínicos)


@dataclass
class TokenizedSentence:
    """Sentença tokenizada com tokens e metadados."""
    original_text: str
    tokens: list[Token] = field(default_factory=list)
    doc_type: str = ""                  # 'prescricoes' ou 'pareceres'
    doc_id: Optional[str] = None

    @property
    def texts(self) -> list[str]:
        return [t.text for t in self.tokens]

    @property
    def labels(self) -> list[str]:
        return [t.label for t in self.tokens]

    # Início - 1) Pré-processamento - 1.5) Exportação - 1.5.1) Exportação no formato CoNLL-2003
    def to_conll(self) -> str:
        """Exporta no formato CoNLL-2003 (token \\t label por linha)."""
        lines = [f"{t.text}\t{t.label}" for t in self.tokens]
        return "\n".join(lines)
    # Fim - 1) Pré-processamento - 1.5) Exportação - 1.5.1) Exportação no formato CoNLL-2003


# ─── Regex para tokenização clínica ──────────────────────────────────────────

# Pontuação que deve ser token separado
_PUNCT = r"""[.,;:!?()\[\]{}"'`/\\@#$%^&*+=<>|~]"""
# Hífen em contexto clínico: manter em "anti-hipertensivo", separar em "---"
_RE_CLINICAL_TOKENIZE = re.compile(
    r"(\d+[.,]\d+)"            # números decimais (ex.: 1.5, 2,5)
    r"|(\w+-\w+)"              # compostos com hífen (ex.: anti-hipertensivo)
    r"|(\w+)"                  # palavras
    r"|(" + _PUNCT + r")"      # pontuação
)


class WordTokenizer:
    """
    Tokenizador baseado em regras para modelos CRF e análise linguística.

    Preserva unidades clínicas como "1.5mg", "2/h", e compostos com hífen.
    """

    def __init__(self, expand_abbreviations: bool = False):
        """
        Args:
            expand_abbreviations: Se True, expande abreviações via dicionário
                                  (útil para análise exploratória, NÃO para NER).
        """
        self.expand_abbreviations = expand_abbreviations
        self._abbrev_dict = None
        if expand_abbreviations:
            from .abbreviations import ABBREV_DICT
            self._abbrev_dict = ABBREV_DICT

    # Início - 1) Pré-processamento - 1.4) Tokenização - 1.4.1) Tokenização por palavras (regex clínico)
    def tokenize(self, sentence: str) -> TokenizedSentence:
        """
        Tokeniza uma sentença clínica.

        Returns:
            TokenizedSentence com lista de Token.
        """
        tokens = []
        for m in _RE_CLINICAL_TOKENIZE.finditer(sentence):
            text = m.group(0)
            start, end = m.start(), m.end()

            # Expandir abreviação se solicitado
            if self.expand_abbreviations and self._abbrev_dict:
                expanded = self._abbrev_dict.get(text.upper().strip("."), None)
                display = expanded if expanded else text
            else:
                display = text

            token = Token(
                text=display,
                start=start,
                end=end,
                is_abbreviation=text.upper() in (self._abbrev_dict or {}),
                is_numeric=bool(re.match(r"^\d+([.,]\d+)?$", text)),
                is_date=text.startswith("__DATA__"),
            )
            tokens.append(token)

        return TokenizedSentence(original_text=sentence, tokens=tokens)
    # Fim - 1) Pré-processamento - 1.4) Tokenização - 1.4.1) Tokenização por palavras (regex clínico)

    def tokenize_batch(self, sentences: list[str]) -> list[TokenizedSentence]:
        return [self.tokenize(s) for s in sentences]


# Início - 1) Pré-processamento - 1.4) Tokenização - 1.4.3) Tokenização subword (WordPiece / BERT)
class SubwordTokenizer:
    """
    Tokenizador subword via HuggingFace para modelos BERT.

    Alinha tokens de palavras com subwords e propaga rótulos BIO
    (estratégia: primeiro subword recebe rótulo; demais recebem 'X').

    Uso:
        tokenizer = SubwordTokenizer("pucpr/biobertpt-clin")
        encoding = tokenizer.tokenize("Paciente com HAS e DM2.")
    """

    def __init__(
        self,
        model_name: str = "pucpr/biobertpt-clin",
        max_length: int = 512,
        stride: int = 128,
    ):
        self.model_name = model_name
        self.max_length = max_length
        self.stride = stride
        self._tokenizer = None

    def _load(self):
        """Carrega tokenizador HuggingFace sob demanda (lazy loading)."""
        if self._tokenizer is None:
            try:
                from transformers import AutoTokenizer
                self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            except ImportError:
                raise RuntimeError("transformers não instalado. Execute: pip install transformers")

    def tokenize(
        self,
        words: list[str],
        labels: Optional[list[str]] = None,
    ) -> dict:
        """
        Tokeniza lista de palavras e alinha rótulos BIO.

        Args:
            words: Lista de palavras (saída de WordTokenizer).
            labels: Lista de rótulos BIO alinhados com words (opcional).

        Returns:
            Dicionário compatível com HuggingFace Dataset (input_ids,
            attention_mask, labels, word_ids).
        """
        self._load()

        encoding = self._tokenizer(
            words,
            is_split_into_words=True,
            truncation=True,
            max_length=self.max_length,
            padding="max_length",
            return_offsets_mapping=True,
        )

        if labels is not None:
            aligned_labels = self._align_labels(encoding, labels)
            encoding["labels"] = aligned_labels

        return encoding

    @staticmethod
    def _align_labels(encoding, word_labels: list[str]) -> list[int]:
        """
        Alinha rótulos BIO com subwords.
        Estratégia: primeiro subword herda rótulo; subwords continuação → -100.

        Retorna lista de inteiros (índices de label) para CrossEntropyLoss.
        Label -100 é ignorado pelo PyTorch.
        """
        # Mapeamento label → índice (definido em ner/labels.py)
        from ..ner.labels import LABEL2ID
        aligned = []
        previous_word_idx = None

        for word_idx in encoding.word_ids():
            if word_idx is None:
                # Tokens especiais ([CLS], [SEP], padding)
                aligned.append(-100)
            elif word_idx != previous_word_idx:
                # Primeiro subword da palavra
                label = word_labels[word_idx] if word_idx < len(word_labels) else "O"
                aligned.append(LABEL2ID.get(label, LABEL2ID["O"]))
            else:
                # Subwords continuação
                aligned.append(-100)
            previous_word_idx = word_idx

        return aligned

    def tokenize_dataset(
        self,
        sentences: list[list[str]],
        sentence_labels: Optional[list[list[str]]] = None,
    ) -> list[dict]:
        """Tokeniza lista de sentenças (formato dataset HuggingFace)."""
        results = []
        for i, words in enumerate(sentences):
            labels = sentence_labels[i] if sentence_labels else None
            results.append(self.tokenize(words, labels))
        return results
# Fim - 1) Pré-processamento - 1.4) Tokenização - 1.4.3) Tokenização subword (WordPiece / BERT)
