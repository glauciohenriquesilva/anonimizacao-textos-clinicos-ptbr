"""
Definição do esquema de rótulos BIO (IOB2)
============================================
Decisão: usar BIO em vez de BILOU.
Justificativa: BIO é o padrão na literatura PT-BR (SemClinBr, AnonyMed-BR),
facilita comparação direta de métricas F1. BILOU não oferece ganho
estatisticamente significativo em datasets < 50k tokens.
Ver docs/07_decisoes/decisoes_ner.md.

Entidades de ANONIMIZAÇÃO (PHI — LGPD/HIPAA Safe Harbour):
    PESSOA       — nome de paciente, familiar, profissional de saúde
    DOCUMENTO    — CPF, RG, prontuário, CRM
    ENDEREÇO     — rua, cidade, estado, CEP
    CONTATO      — telefone, e-mail
    DATA         — qualquer data
    HORA         — horário
    INSTITUIÇÃO  — nome de hospital, laboratório, plano de saúde

Entidades de UTILIDADE CLÍNICA (ΔF1 downstream):
    MEDICAMENTO  — nome de fármaco / princípio ativo
    DOSE         — valor numérico + unidade (ex.: "500mg")
    VIA          — via de administração (ex.: "v.o.", "EV")
    FREQUÊNCIA   — frequência de administração (ex.: "8/8h", "1x ao dia")
    DIAGNÓSTICO  — CID / descrição diagnóstica
    PROCEDIMENTO — nome de procedimento clínico/cirúrgico
"""

from __future__ import annotations


# ─── Entidades ────────────────────────────────────────────────────────────────

# Início - 2) NER - 2.3) Treinamento - Definição do esquema de rótulos BIO (IOB2)
# Entidades de anonimização (PHI)
PHI_ENTITIES: list[str] = [
    "PESSOA",
    "DOCUMENTO",
    "ENDEREÇO",
    "CONTATO",
    "DATA",
    "HORA",
    "INSTITUIÇÃO",
]

# Entidades de utilidade clínica
UTILITY_ENTITIES: list[str] = [
    "MEDICAMENTO",
    "DOSE",
    "VIA",
    "FREQUÊNCIA",
    "DIAGNÓSTICO",
    "PROCEDIMENTO",
]

ALL_ENTITIES: list[str] = PHI_ENTITIES + UTILITY_ENTITIES


# ─── Esquema BIO ──────────────────────────────────────────────────────────────

def build_bio_labels(entities: list[str]) -> list[str]:
    """Constrói lista de rótulos BIO a partir de lista de entidades."""
    labels = ["O"]
    for ent in entities:
        labels.append(f"B-{ent}")
        labels.append(f"I-{ent}")
    return labels


# Rótulos apenas de PHI (para experimentos de anonimização)
PHI_LABELS: list[str] = build_bio_labels(PHI_ENTITIES)

# Rótulos completos (PHI + utilidade)
ALL_LABELS: list[str] = build_bio_labels(ALL_ENTITIES)

# Mapeamentos índice ↔ rótulo (usados no treinamento)
LABEL2ID: dict[str, int] = {label: i for i, label in enumerate(ALL_LABELS)}
ID2LABEL: dict[int, str] = {i: label for label, i in LABEL2ID.items()}

# Versão apenas PHI
PHI_LABEL2ID: dict[str, int] = {label: i for i, label in enumerate(PHI_LABELS)}
PHI_ID2LABEL: dict[int, str] = {i: label for label, i in PHI_LABEL2ID.items()}

NUM_LABELS: int = len(ALL_LABELS)
NUM_PHI_LABELS: int = len(PHI_LABELS)
# Fim - 2) NER - 2.3) Treinamento - Definição do esquema de rótulos BIO (IOB2)


# ─── Utilitários ─────────────────────────────────────────────────────────────

def is_valid_bio_sequence(labels: list[str]) -> bool:
    """
    Verifica se uma sequência BIO é válida (não há I-X sem B-X anterior).

    Args:
        labels: Lista de rótulos BIO.

    Returns:
        True se a sequência for válida.
    """
    current_entity = None
    for label in labels:
        if label == "O":
            current_entity = None
        elif label.startswith("B-"):
            current_entity = label[2:]
        elif label.startswith("I-"):
            entity = label[2:]
            if current_entity != entity:
                return False  # I-X sem B-X anterior
        else:
            return False  # rótulo desconhecido
    return True


# Início - 3) Anonimização - 3.1) Substituição por Marcadores - Conversão de sequência BIO em spans
def bio_to_spans(
    tokens: list[str], labels: list[str]
) -> list[tuple[str, str, int, int]]:
    """
    Converte sequência BIO em spans de entidades.

    Returns:
        Lista de (entity_type, text_span, start_idx, end_idx).
    """
    spans = []
    current_entity = None
    current_tokens: list[str] = []
    current_start = 0

    for i, (token, label) in enumerate(zip(tokens, labels)):
        if label == "O":
            if current_entity:
                spans.append((
                    current_entity,
                    " ".join(current_tokens),
                    current_start,
                    i - 1,
                ))
                current_entity = None
                current_tokens = []
        elif label.startswith("B-"):
            if current_entity:
                spans.append((
                    current_entity,
                    " ".join(current_tokens),
                    current_start,
                    i - 1,
                ))
            current_entity = label[2:]
            current_tokens = [token]
            current_start = i
        elif label.startswith("I-"):
            if current_entity:
                current_tokens.append(token)

    if current_entity:
        spans.append((
            current_entity,
            " ".join(current_tokens),
            current_start,
            len(tokens) - 1,
        ))

    return spans
# Fim - 3) Anonimização - 3.1) Substituição por Marcadores - Conversão de sequência BIO em spans
