"""
Pipeline de Pré-processamento — Orquestrador
================================================
Integra as etapas de normalização → segmentação → tokenização em um
único fluxo configurável.

Fluxo principal:
    CSV bruto
      → load_csv()           [analysis/exploratory]
      → TextNormalizer       [normalizer.py]
      → ClinicalSegmenter    [segmenter.py]
      → WordTokenizer        [tokenizer.py]
      → Dataset CoNLL/JSONL  [saída para NER]

Uso (linha de comando):
    python src/preprocessing/pipeline.py \
        --input data/raw/prescricoes.csv \
        --doc-type prescricoes \
        --output data/processed/ \
        --format conll

Uso (API Python):
    from src.preprocessing.pipeline import PreprocessingPipeline
    pipe = PreprocessingPipeline(doc_type="prescricoes")
    samples = pipe.run(df)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Optional

import pandas as pd

from .normalizer import TextNormalizer
from .segmenter import ClinicalSegmenter
from .tokenizer import WordTokenizer, TokenizedSentence

# Colunas de texto por tipo de documento (mesmas constantes do exploratory.py)
TEXT_COLUMN = {
    "prescricoes": "ds_evolucao",
    "pareceres": "ds_parecer",
}

# Colunas de ID para rastreabilidade
ID_COLUMN = {
    "prescricoes": "cd_atendimento",
    "pareceres": "cd_atendimento",
}


class PreprocessingPipeline:
    """
    Pipeline completo de pré-processamento de textos clínicos.

    Atributos configuráveis (via construtor ou config dict):
        doc_type:          'prescricoes' | 'pareceres'
        lowercase:         normalizar para minúsculas
        mask_phi:          substituir PHI numérico por placeholders
        expand_abbrev:     expandir abreviações médicas
        use_spacy:         usar spaCy para segmentação (mais preciso)
        min_tokens:        descartar sentenças com menos de N tokens
    """

    DEFAULT_CONFIG = {
        "lowercase": False,
        "mask_phi": True,
        "mask_dates": False,
        "expand_abbrev": False,
        "use_spacy": False,
        "min_tokens": 3,
    }

    def __init__(self, doc_type: str, **config):
        if doc_type not in TEXT_COLUMN:
            raise ValueError(f"doc_type deve ser 'prescricoes' ou 'pareceres'. Recebido: {doc_type!r}")
        self.doc_type = doc_type
        self.config = {**self.DEFAULT_CONFIG, **config}

        self.normalizer = TextNormalizer(
            lowercase=self.config["lowercase"],
            mask_dates=self.config["mask_dates"],
            mask_phi=self.config["mask_phi"],
        )
        self.segmenter = ClinicalSegmenter(use_spacy=self.config["use_spacy"])
        self.word_tokenizer = WordTokenizer(
            expand_abbreviations=self.config["expand_abbrev"]
        )

    # ── Detecção de tipo de texto ───────────────────────────────────────────

    # Início - 1) Pré-processamento - 1.3) Segmentação - 1.3.1) Detecção do tipo de texto
    @staticmethod
    def _detect_text_type(text: str) -> str:
        """Detecta se o texto é template ou livre (reutiliza lógica do exploratory)."""
        from ..analysis.exploratory import classify_text_type
        return classify_text_type(text)
    # Fim - 1) Pré-processamento - 1.3) Segmentação - 1.3.1) Detecção do tipo de texto

    # ── Processamento por documento ─────────────────────────────────────────

    def process_document(
        self,
        text: str,
        doc_id: Optional[str] = None,
    ) -> list[TokenizedSentence]:
        """
        Processa um único documento textual.

        Args:
            text: Texto bruto do documento.
            doc_id: Identificador do documento (para rastreabilidade).

        Returns:
            Lista de TokenizedSentence prontas para anotação/NER.
        """
        if not isinstance(text, str) or not text.strip():
            return []

        # 1. Normalização
        normalized = self.normalizer.normalize(text)

        # 2. Detecção de tipo
        text_type = self._detect_text_type(normalized)

        # 3. Segmentação
        sentences = self.segmenter.segment(normalized, text_type)

        # 4. Tokenização
        tokenized = []
        for sent in sentences:
            ts = self.word_tokenizer.tokenize(sent)
            ts.doc_type = self.doc_type
            ts.doc_id = doc_id
            if len(ts.tokens) >= self.config["min_tokens"]:
                tokenized.append(ts)

        return tokenized

    # ── Processamento em lote ───────────────────────────────────────────────

    # Início - 1) Pré-processamento - 1.1) Carregamento do DataSet - 1.1.1) Leitura do DataFrame por tipo de documento
    # Início - 1) Pré-processamento - 1.1) Carregamento do DataSet - 1.1.2) Seleção da coluna de texto (ds_evolucao / ds_parecer)
    # Início - 1) Pré-processamento - 1.1) Carregamento do DataSet - 1.1.3) Seleção da coluna de ID para rastreabilidade
    def run(self, df: pd.DataFrame) -> list[TokenizedSentence]:
        """
        Processa um DataFrame inteiro.

        Args:
            df: DataFrame carregado pelo load_csv() do exploratory.py.

        Returns:
            Lista flat de TokenizedSentence de todos os documentos.
        """
        text_col = TEXT_COLUMN[self.doc_type]
        id_col = ID_COLUMN.get(self.doc_type)

        all_sentences: list[TokenizedSentence] = []
        n_docs = 0
        n_empty = 0

        for _, row in df.iterrows():
            text = row.get(text_col, "")
            doc_id = str(row.get(id_col, "")) if id_col else None

            if not isinstance(text, str) or not text.strip():
                n_empty += 1
                continue

            sentences = self.process_document(text, doc_id)
            all_sentences.extend(sentences)
            n_docs += 1

        print(
            f"✓ Pré-processamento concluído: {n_docs} documentos → "
            f"{len(all_sentences)} sentenças | {n_empty} documentos vazios ignorados"
        )
        return all_sentences
    # Fim - 1) Pré-processamento - 1.1) Carregamento do DataSet - 1.1.1) Leitura do DataFrame por tipo de documento
    # Fim - 1) Pré-processamento - 1.1) Carregamento do DataSet - 1.1.2) Seleção da coluna de texto (ds_evolucao / ds_parecer)
    # Fim - 1) Pré-processamento - 1.1) Carregamento do DataSet - 1.1.3) Seleção da coluna de ID para rastreabilidade

    # ── Exportação ──────────────────────────────────────────────────────────

    # Início - 1) Pré-processamento - 1.5) Exportação - 1.5.1) Exportação no formato CoNLL-2003
    @staticmethod
    def to_conll(
        sentences: list[TokenizedSentence],
        output_path: Path,
        encoding: str = "utf-8",
    ) -> None:
        """
        Exporta sentenças no formato CoNLL-2003.

        Formato:
            token_1  LABEL_1
            token_2  LABEL_2
            (linha em branco entre sentenças)

        Args:
            sentences: Lista de TokenizedSentence (com ou sem labels).
            output_path: Arquivo .conll de saída.
            encoding: Encoding do arquivo.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding=encoding) as f:
            for sent in sentences:
                f.write(sent.to_conll())
                f.write("\n\n")

        print(f"✓ CoNLL exportado: {output_path} ({len(sentences)} sentenças)")
    # Fim - 1) Pré-processamento - 1.5) Exportação - 1.5.1) Exportação no formato CoNLL-2003

    # Início - 1) Pré-processamento - 1.5) Exportação - 1.5.2) Exportação no formato JSONL
    @staticmethod
    def to_jsonl(
        sentences: list[TokenizedSentence],
        output_path: Path,
        encoding: str = "utf-8",
    ) -> None:
        """
        Exporta sentenças em JSONL (uma sentença por linha).

        Formato:
            {"id": "...", "tokens": [...], "labels": [...]}
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding=encoding) as f:
            for i, sent in enumerate(sentences):
                record = {
                    "id": f"{sent.doc_id or 'doc'}_{i}",
                    "doc_type": sent.doc_type,
                    "tokens": sent.texts,
                    "labels": sent.labels,
                    "text": sent.original_text,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        print(f"✓ JSONL exportado: {output_path} ({len(sentences)} sentenças)")
    # Fim - 1) Pré-processamento - 1.5) Exportação - 1.5.2) Exportação no formato JSONL


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Pipeline de pré-processamento de textos clínicos"
    )
    parser.add_argument("--input", required=True, help="Arquivo CSV de entrada")
    parser.add_argument(
        "--doc-type",
        required=True,
        choices=["prescricoes", "pareceres"],
        help="Tipo de documento",
    )
    parser.add_argument(
        "--output",
        default="data/processed/",
        help="Diretório de saída",
    )
    parser.add_argument(
        "--format",
        choices=["conll", "jsonl", "both"],
        default="both",
        help="Formato de saída",
    )
    parser.add_argument("--lowercase", action="store_true")
    parser.add_argument("--expand-abbrev", action="store_true")
    parser.add_argument("--use-spacy", action="store_true")
    args = parser.parse_args()

    # Carrega dados
    df = pd.read_csv(
        args.input,
        sep=";",
        quoting=csv.QUOTE_MINIMAL,
        encoding="utf-8",
        dtype=str,
        on_bad_lines="warn",
    )
    print(f"→ {len(df):,} registros carregados de {args.input}")

    # Executa pipeline
    pipe = PreprocessingPipeline(
        doc_type=args.doc_type,
        lowercase=args.lowercase,
        expand_abbrev=args.expand_abbrev,
        use_spacy=args.use_spacy,
    )
    sentences = pipe.run(df)

    # Exporta
    out_dir = Path(args.output) / args.doc_type
    if args.format in ("conll", "both"):
        pipe.to_conll(sentences, out_dir / f"{args.doc_type}.conll")
    if args.format in ("jsonl", "both"):
        pipe.to_jsonl(sentences, out_dir / f"{args.doc_type}.jsonl")

    print(f"\n✅ Concluído. Saída em: {out_dir}")


if __name__ == "__main__":
    main()
