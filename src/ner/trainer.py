"""
Treinamento de modelos NER
============================
Stub documentado para treinamento de CRF e modelos BERT/mmBERT/ModernBERT.

IMPORTANTE: O treinamento de modelos BERT requer GPU com ≥16 GB VRAM.
Use os notebooks em notebooks/colab/ para executar no Google Colab (GPU T4/A100).

Uso local (apenas CRF):
    python src/ner/trainer.py \
        --model crf \
        --train data/processed/prescricoes/train.conll \
        --dev   data/processed/prescricoes/dev.conll \
        --output outputs/models/

Uso no Colab (BERT):
    Ver notebooks/colab/03_bert_finetuning.ipynb
"""

from __future__ import annotations

import argparse
import pickle
from pathlib import Path
from typing import Optional

from .labels import LABEL2ID, ID2LABEL, NUM_LABELS, is_valid_bio_sequence
from .models import get_model_config, ModelConfig


# ─── Carregamento de dados ────────────────────────────────────────────────────

# Início - 2) NER - 2.3) Treinamento - 2.3.1) Carregamento de dados CoNLL (tokens e rótulos BIO)
def load_conll(filepath: str) -> list[tuple[list[str], list[str]]]:
    """
    Carrega arquivo CoNLL-2003 (token\\tlabel por linha, sentenças separadas por \\n).

    Returns:
        Lista de (tokens, labels) por sentença.
    """
    sentences = []
    tokens, labels = [], []

    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip()
            if not line:
                if tokens:
                    sentences.append((tokens[:], labels[:]))
                    tokens, labels = [], []
            else:
                parts = line.split("\t")
                if len(parts) >= 2:
                    tokens.append(parts[0])
                    labels.append(parts[1])

    if tokens:
        sentences.append((tokens, labels))

    return sentences
# Fim - 2) NER - 2.3) Treinamento - 2.3.1) Carregamento de dados CoNLL (tokens e rótulos BIO)


# ─── CRF Trainer ─────────────────────────────────────────────────────────────

class CRFTrainer:
    """
    Treina e avalia um modelo CRF com sklearn-crfsuite.

    Features extraídas por token (documentadas em src/ner/models.py).
    """

    def __init__(self, config: Optional[ModelConfig] = None):
        self.config = config or get_model_config("crf")
        self.model = None

    # Início - 2) NER - 2.3) Treinamento - 2.3.2) Extração de features por token (CRF)
    @staticmethod
    def _extract_features(tokens: list[str], i: int) -> dict:
        """Extrai features de contexto para o token na posição i."""
        word = tokens[i]
        features = {
            "bias": 1.0,
            "word.lower": word.lower(),
            "word[-3:]": word[-3:],
            "word[-2:]": word[-2:],
            "word[:3]": word[:3],
            "word.isupper": word.isupper(),
            "word.istitle": word.istitle(),
            "word.isdigit": word.isdigit(),
            "word.has_hyphen": "-" in word,
        }

        # Contexto anterior
        if i > 0:
            prev = tokens[i - 1]
            features.update({
                "-1:word.lower": prev.lower(),
                "-1:word.istitle": prev.istitle(),
                "-1:word.isupper": prev.isupper(),
            })
        else:
            features["BOS"] = True

        # Contexto posterior
        if i < len(tokens) - 1:
            nxt = tokens[i + 1]
            features.update({
                "+1:word.lower": nxt.lower(),
                "+1:word.istitle": nxt.istitle(),
            })
        else:
            features["EOS"] = True

        return features

    def _sentence_to_features(self, tokens: list[str]) -> list[dict]:
        return [self._extract_features(tokens, i) for i in range(len(tokens))]
    # Fim - 2) NER - 2.3) Treinamento - 2.3.2) Extração de features por token (CRF)

    # Início - 2) NER - 2.3) Treinamento - 2.3.3) Treinamento do modelo CRF (sklearn-crfsuite)
    def train(
        self,
        train_sentences: list[tuple[list[str], list[str]]],
        dev_sentences: Optional[list[tuple[list[str], list[str]]]] = None,
    ) -> None:
        """
        Treina modelo CRF.

        Args:
            train_sentences: Lista de (tokens, labels) de treino.
            dev_sentences: Lista de (tokens, labels) de validação (opcional).
        """
        try:
            import sklearn_crfsuite
        except ImportError:
            raise RuntimeError("sklearn-crfsuite não instalado. Execute: pip install sklearn-crfsuite")

        X_train = [self._sentence_to_features(t) for t, _ in train_sentences]
        y_train = [l for _, l in train_sentences]

        self.model = sklearn_crfsuite.CRF(
            algorithm="lbfgs",
            c1=0.1,
            c2=0.1,
            max_iterations=200,
            all_possible_transitions=True,
        )
        self.model.fit(X_train, y_train)
        print(f"✓ CRF treinado com {len(train_sentences)} sentenças")

        if dev_sentences:
            from .evaluator import NERMetrics
            X_dev = [self._sentence_to_features(t) for t, _ in dev_sentences]
            y_true = [l for _, l in dev_sentences]
            y_pred = self.model.predict(X_dev)
            metrics = NERMetrics.compute_seqeval(y_true, y_pred)
            print(f"  Dev F1: {metrics['overall_f1']:.4f}")
    # Fim - 2) NER - 2.3) Treinamento - 2.3.3) Treinamento do modelo CRF (sklearn-crfsuite)

    # Início - 2) NER - 2.3) Treinamento - 2.3.5) Predição / Inferência NER
    def predict(self, sentences: list[list[str]]) -> list[list[str]]:
        """Prediz rótulos BIO para lista de sentenças tokenizadas."""
        if self.model is None:
            raise RuntimeError("Modelo não treinado. Execute train() primeiro.")
        X = [self._sentence_to_features(tokens) for tokens in sentences]
        return self.model.predict(X)
    # Fim - 2) NER - 2.3) Treinamento - 2.3.5) Predição / Inferência NER

    # Início - 2) NER - 2.4) Avaliação - 2.4.1) Serialização do modelo (save / load)
    def save(self, output_path: Path) -> None:
        """Salva modelo CRF em pickle."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            pickle.dump(self.model, f)
        print(f"✓ Modelo CRF salvo em {output_path}")

    def load(self, model_path: Path) -> None:
        """Carrega modelo CRF de pickle."""
        with open(model_path, "rb") as f:
            self.model = pickle.load(f)
        print(f"✓ Modelo CRF carregado de {model_path}")
    # Fim - 2) NER - 2.4) Avaliação - 2.4.1) Serialização do modelo (save / load)


# ─── BERT Trainer (stub) ──────────────────────────────────────────────────────

# Início - 2) NER - 2.3) Treinamento - 2.3.4) Configuração do HuggingFace Trainer (BERT / mmBERT / ModernBERT)
class BERTNERTrainer:
    """
    Treina modelos BERT para NER via HuggingFace Trainer.

    STUB: implementação completa nos notebooks Colab.
    Ver: notebooks/colab/03_bert_finetuning.ipynb
         notebooks/colab/04_mmbert_modernbert_finetuning.ipynb

    Exemplo de uso (em notebook Colab):
        from src.ner.trainer import BERTNERTrainer
        trainer = BERTNERTrainer(model_name="biobertpt_clin")
        trainer.setup(train_data, dev_data)
        trainer.train()
        trainer.save("outputs/models/biobertpt_clin/")
    """

    def __init__(self, model_name: str):
        self.config = get_model_config(model_name)
        self.trainer = None
        self.model = None
        self.tokenizer = None

    def setup(
        self,
        train_data: list[tuple[list[str], list[str]]],
        dev_data: list[tuple[list[str], list[str]]],
        output_dir: Optional[str] = None,
    ) -> None:
        """
        Configura HuggingFace Trainer com TrainingArguments.

        TODO (implementar no notebook Colab):
          1. Carregar AutoTokenizer do model_id
          2. Tokenizar com SubwordTokenizer e alinhar labels
          3. Criar Dataset HuggingFace (train/dev)
          4. Carregar AutoModelForTokenClassification com num_labels
          5. Definir compute_metrics usando seqeval
          6. Configurar TrainingArguments (lr, batch_size, epochs, etc.)
          7. Instanciar Trainer e chamar trainer.train()
        """
        raise NotImplementedError(
            "BERTNERTrainer.setup() deve ser implementado no notebook Colab.\n"
            f"Ver: notebooks/colab/03_bert_finetuning.ipynb\n"
            f"Modelo: {self.config.hf_model_id}"
        )

    def train(self) -> None:
        raise NotImplementedError("Implementar no notebook Colab.")

    def save(self, output_dir: str) -> None:
        raise NotImplementedError("Implementar no notebook Colab.")

    def load(self, model_dir: str) -> None:
        raise NotImplementedError("Implementar no notebook Colab.")
# Fim - 2) NER - 2.3) Treinamento - 2.3.4) Configuração do HuggingFace Trainer (BERT / mmBERT / ModernBERT)


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Treina modelo NER")
    parser.add_argument("--model", required=True, choices=["crf"],
                        help="Apenas CRF disponível localmente (BERT: usar Colab)")
    parser.add_argument("--train", required=True)
    parser.add_argument("--dev", required=False)
    parser.add_argument("--output", default="outputs/models/")
    args = parser.parse_args()

    train_data = load_conll(args.train)
    dev_data = load_conll(args.dev) if args.dev else None
    print(f"→ {len(train_data)} sentenças de treino carregadas")

    if args.model == "crf":
        trainer = CRFTrainer()
        trainer.train(train_data, dev_data)
        out = Path(args.output) / "crf" / "model.pkl"
        trainer.save(out)

    print(f"\n✅ Treinamento concluído. Modelo salvo em: {args.output}")


if __name__ == "__main__":
    main()
