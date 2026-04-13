"""
Registro de modelos NER disponíveis
======================================
Define os 5 modelos do experimento com HuggingFace IDs, configurações
de treinamento e requisitos de hardware.

Modelos:
    1. CRF (baseline)          — sklearn-crfsuite, CPU
    2. BioBERTpt-clin          — pucpr/biobertpt-clin, GPU (16 GB VRAM)
    3. BERTimbau-leNER         — pierreguillou/bert-base-cased-pt-lenerbr, GPU (16 GB)
    4. mmBERT-base             — jhu-clsp/mmBERT, GPU (16 GB)
    5. ModernBERT-base         — answerdotai/ModernBERT-base, GPU (16 GB)

Referências:
    BioBERTpt-clin: Schneider et al. (2020) — PROPOR
    BERTimbau:      Souza et al. (2020) — PROPOR / dissertação UNICAMP
    mmBERT:         Schiezaro et al. (2026) — SOTA SemClinBr F1=0.7646
    ModernBERT:     Warner et al. (2024) — arXiv 2412.13663
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ModelConfig:
    """Configuração completa de um modelo NER."""
    name: str                           # identificador curto
    display_name: str                   # nome para relatórios
    hf_model_id: Optional[str]          # None para modelos sem HF
    model_type: str                     # 'crf' | 'bert' | 'modernbert'

    # Treinamento
    max_length: int = 512
    batch_size_train: int = 16
    batch_size_eval: int = 32
    learning_rate: float = 2e-5
    num_epochs: int = 10
    warmup_ratio: float = 0.1
    weight_decay: float = 0.01

    # Hardware
    requires_gpu: bool = True
    vram_gb: float = 16.0
    colab_recommended: bool = True      # GPU-intensive → Colab

    # Features CRF (apenas para model_type='crf')
    crf_features: list[str] = field(default_factory=list)

    # Referência bibliográfica
    reference: str = ""

    def __str__(self) -> str:
        return f"ModelConfig({self.name}, {self.hf_model_id or 'N/A'})"


# ─── Definição dos modelos ────────────────────────────────────────────────────

MODEL_REGISTRY: dict[str, ModelConfig] = {

    "crf": ModelConfig(
        name="crf",
        display_name="CRF Baseline",
        hf_model_id=None,
        model_type="crf",
        requires_gpu=False,
        vram_gb=0.0,
        colab_recommended=False,
        crf_features=[
            "word.lower()",
            "word[-3:]",                  # sufixo 3 chars
            "word[-2:]",                  # sufixo 2 chars
            "word[:3]",                   # prefixo 3 chars
            "word.isupper()",
            "word.istitle()",
            "word.isdigit()",
            "word.has_hyphen",
            "is_abbreviation",            # dicionário médico
            "pos_tag",                    # POS via spaCy
            "BOS",                        # beginning of sentence
            "EOS",                        # end of sentence
        ],
        reference="Lafferty et al. (2001) — CRF; sklearn-crfsuite",
    ),

    "biobertpt_clin": ModelConfig(
        name="biobertpt_clin",
        display_name="BioBERTpt-clin",
        hf_model_id="pucpr/biobertpt-clin",
        model_type="bert",
        max_length=512,
        batch_size_train=16,
        learning_rate=2e-5,
        num_epochs=10,
        reference="Schneider et al. (2020), PROPOR — BioBERTpt fine-tuned em corpus clínico PT-BR",
    ),

    "bertimbau_lener": ModelConfig(
        name="bertimbau_lener",
        display_name="BERTimbau-leNER",
        hf_model_id="pierreguillou/bert-base-cased-pt-lenerbr",
        model_type="bert",
        max_length=512,
        batch_size_train=16,
        learning_rate=3e-5,
        num_epochs=10,
        reference="Souza et al. (2020), PROPOR/UNICAMP — BERTimbau; leNER-Br fine-tuned",
    ),

    "mmbert": ModelConfig(
        name="mmbert",
        display_name="mmBERT-base",
        hf_model_id="jhu-clsp/mmBERT",
        model_type="bert",
        max_length=512,
        batch_size_train=16,
        learning_rate=2e-5,
        num_epochs=10,
        vram_gb=16.0,
        reference=(
            "Schiezaro et al. (2026) — mmBERT (CALL), SOTA SemClinBr F1=0.7646 "
            "com Iterative Stratification"
        ),
    ),

    "modernbert": ModelConfig(
        name="modernbert",
        display_name="ModernBERT-base",
        hf_model_id="answerdotai/ModernBERT-base",
        model_type="modernbert",
        max_length=8192,                  # suporte nativo 8192 tokens
        batch_size_train=8,               # batch menor devido ao contexto longo
        learning_rate=1e-5,
        num_epochs=10,
        vram_gb=24.0,                     # A100 recomendado para ctx 8192
        reference=(
            "Warner et al. (2024) — ModernBERT, arXiv:2412.13663; "
            "RoPE + Flash Attention + alternating local/global attention"
        ),
    ),
}

# Alias para acesso rápido
ALL_MODEL_NAMES: list[str] = list(MODEL_REGISTRY.keys())
BERT_MODEL_NAMES: list[str] = [k for k, v in MODEL_REGISTRY.items() if v.model_type in ("bert", "modernbert")]
GPU_MODEL_NAMES: list[str] = [k for k, v in MODEL_REGISTRY.items() if v.requires_gpu]


def get_model_config(name: str) -> ModelConfig:
    """Retorna ModelConfig pelo nome. Lança KeyError se não encontrado."""
    if name not in MODEL_REGISTRY:
        raise KeyError(f"Modelo '{name}' não encontrado. Disponíveis: {ALL_MODEL_NAMES}")
    return MODEL_REGISTRY[name]
