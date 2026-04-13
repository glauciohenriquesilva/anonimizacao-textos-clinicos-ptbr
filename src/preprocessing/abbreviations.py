"""
Dicionário de abreviações médicas e expansões
===============================================
Construído a partir da análise exploratória dos dados reais de pareceres
e prescrições do HUCAM/PRODEST.

Referência: inspeção manual dos CSVs de amostra (abril/2026).
"""

from __future__ import annotations

# ─── Dicionário principal ───────────────────────────────────────────────────────
# Chave: abreviação (MAIÚSCULA, sem pontos)
# Valor: expansão por extenso

ABBREV_DICT: dict[str, str] = {
    # ── Lesões / feridas ────────────────────────────────────────────
    "LPP": "lesão por pressão",
    "LLP": "lesão por pressão",          # grafia alternativa vista nos dados
    # ── Dispositivos invasivos ──────────────────────────────────────
    "SVD": "sonda vesical de demora",
    "SVA": "sonda vesical de alívio",
    "SNG": "sonda nasogástrica",
    "SNE": "sonda nasoenteral",
    "GTT": "gastrostomia",
    "TOT": "tubo orotraqueal",
    "TQT": "traqueostomia",
    "AVP": "acesso venoso periférico",
    "AVP1": "acesso venoso periférico",
    "CVC": "cateter venoso central",
    "PICC": "cateter central de inserção periférica",
    "VJEE": "via jejunal",
    # ── Nutrição / infusão ──────────────────────────────────────────
    "NPT": "nutrição parenteral total",
    "NE": "nutrição enteral",
    "BIC": "bomba de infusão contínua",
    "BH": "balanço hídrico",
    "SF": "soro fisiológico",
    "SGI": "soro glicosado isotônico",
    "SG": "soro glicosado",
    # ── Sinais vitais / monitorização ───────────────────────────────
    "PA": "pressão arterial",
    "PAM": "pressão arterial média",
    "FC": "frequência cardíaca",
    "FR": "frequência respiratória",
    "SAT": "saturação de oxigênio",
    "SPO2": "saturação periférica de oxigênio",
    "TAX": "temperatura axilar",
    "GCS": "escala de coma de Glasgow",
    "RASS": "Richmond Agitation-Sedation Scale",
    # ── Anatomia / localização ──────────────────────────────────────
    "MID": "membro inferior direito",
    "MIE": "membro inferior esquerdo",
    "MSD": "membro superior direito",
    "MSE": "membro superior esquerdo",
    "MMII": "membros inferiores",
    "MMSS": "membros superiores",
    "LOTE": "lóbulo da orelha",
    # ── Procedimentos / cuidados ────────────────────────────────────
    "PHMB": "polihexanida",
    "HTX": "hematotórax",
    "PCR": "parada cardiorrespiratória",
    "RCP": "ressuscitação cardiopulmonar",
    "OTI": "intubação orotraqueal",
    "BIPAP": "bilevel positive airway pressure",
    "CPAP": "continuous positive airway pressure",
    "VM": "ventilação mecânica",
    "O2": "oxigênio",
    "FIO2": "fração inspirada de oxigênio",
    "PEEP": "pressão expiratória final positiva",
    # ── Diagnósticos / condições ────────────────────────────────────
    "HAS": "hipertensão arterial sistêmica",
    "DM": "diabetes mellitus",
    "DM2": "diabetes mellitus tipo 2",
    "DRC": "doença renal crônica",
    "FA": "fibrilação atrial",
    "IC": "insuficiência cardíaca",
    "DPOC": "doença pulmonar obstrutiva crônica",
    "AVC": "acidente vascular cerebral",
    "IAM": "infarto agudo do miocárdio",
    "TEP": "tromboembolismo pulmonar",
    "TVP": "trombose venosa profunda",
    "IRA": "insuficiência renal aguda",
    "EAP": "edema agudo de pulmão",
    "SRIS": "síndrome da resposta inflamatória sistêmica",
    "SDRA": "síndrome do desconforto respiratório agudo",
    "SOFA": "sequential organ failure assessment",
    # ── Medicamentos / vias ─────────────────────────────────────────
    "VO": "via oral",
    "EV": "via endovenosa",
    "IV": "via intravenosa",
    "SC": "via subcutânea",
    "IM": "via intramuscular",
    "SL": "via sublingual",
    "NHD": "não há dados",
    # ── Estrutura da nota clínica ───────────────────────────────────
    "SIC": "segundo informações do/a",
    "HDA": "história da doença atual",
    "HPP": "história patológica pregressa",
    "DP": "diagnóstico principal",
    "QP": "queixa principal",
    "EVOL": "evolução",
    "COND": "conduta",
    # ── Turno / escala ──────────────────────────────────────────────
    "PLAN": "plantão",
    "ENF": "enfermagem",
    "MED": "médico/a",
}

# ─── Funções de utilidade ───────────────────────────────────────────────────────

def expand_abbreviation(token: str) -> str:
    """
    Retorna a expansão de uma abreviação, ou o token original se não encontrada.

    Args:
        token: Token em qualquer capitalização (ex.: "LPP", "lpp", "Lpp").

    Returns:
        Expansão em minúsculas ou token original.
    """
    return ABBREV_DICT.get(token.upper().strip("."), token)


def contains_abbreviation(text: str) -> bool:
    """Retorna True se o texto contém ao menos uma abreviação conhecida."""
    tokens = text.upper().split()
    return any(t.strip(".,;:()") in ABBREV_DICT for t in tokens)


def list_abbreviations(text: str) -> list[str]:
    """Retorna lista de abreviações encontradas no texto."""
    tokens = text.upper().split()
    found = [t.strip(".,;:()") for t in tokens if t.strip(".,;:()") in ABBREV_DICT]
    return list(dict.fromkeys(found))  # preserva ordem, remove duplicatas
