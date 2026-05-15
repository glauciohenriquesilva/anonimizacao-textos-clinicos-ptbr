"""
Normalização de textos clínicos
=================================
Etapa 1 do pré-processamento: limpeza e padronização textual antes da
segmentação e tokenização.

Decisões de projeto documentadas em docs/07_decisoes/decisoes_preprocessamento.md
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Optional


# ─── Padrões de data (4 formatos detectados nos dados reais) ─────────────────

# Formato 1: dd/mm/yyyy  ex.: 15/03/2024
_RE_DATE_DMBR = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
# Formato 2: m/dd/yyyy (americano — presente nos dados)
_RE_DATE_MDY  = re.compile(r"\b(\d{1,2})/(\d{2})/(\d{4})\b")
# Formato 3: dd/mm/yyyy HH:MM
_RE_DATE_DT   = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\s+(\d{2}:\d{2})\b")
# Formato 4: dd/mm/yy (ano 2 dígitos)
_RE_DATE_SHORT = re.compile(r"\b(\d{2})/(\d{2})/(\d{2})\b")

# Entidade de substituição (preservar para NER; não expandir)
DATE_PLACEHOLDER = "__DATA__"

# ─── Padrões de PHI sensível ──────────────────────────────────────────────────

# CPF: 000.000.000-00 ou 00000000000
_RE_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
# Telefone: (00) 00000-0000 ou variantes
_RE_PHONE = re.compile(r"\(?\d{2}\)?\s?\d{4,5}[-\s]?\d{4}\b")
# CEP: 00000-000
_RE_CEP = re.compile(r"\b\d{5}-\d{3}\b")
# E-mail
_RE_EMAIL = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

PHI_PLACEHOLDER = {
    "cpf": "__CPF__",
    "telefone": "__TELEFONE__",
    "cep": "__CEP__",
    "email": "__EMAIL__",
}


# ─── Classe principal ─────────────────────────────────────────────────────────

class TextNormalizer:
    """
    Aplica normalização ao texto clínico bruto preservando estrutura clínica.

    Uso:
        normalizer = TextNormalizer()
        texto_normalizado = normalizer.normalize(texto_bruto)

    Etapas (em ordem):
        1. Decodificação Unicode (NFC)
        2. Remoção de caracteres de controle (exceto \\n)
        3. Normalização de espaços múltiplos
        4. Padronização de datas → ISO 8601 (YYYY-MM-DD)
        5. Substituição preventiva de PHI numérico (CPF, tel, CEP)
        6. Padronização de maiúsculas/minúsculas (opção)
    """

    def __init__(
        self,
        lowercase: bool = False,
        mask_dates: bool = False,
        mask_phi: bool = True,
    ):
        """
        Args:
            lowercase: Se True, converte tudo para minúsculas após normalização.
            mask_dates: Se True, substitui datas por placeholder __DATA__.
            mask_phi: Se True, substitui CPF/tel/CEP/email por placeholders.
        """
        self.lowercase = lowercase
        self.mask_dates = mask_dates
        self.mask_phi = mask_phi

    # ── Métodos de limpeza ──────────────────────────────────────────────────

    # Início - 1) Pré-processamento - 1.2) Normalização - 1.2.1) Normalização Unicode NFC
    # Início - 1) Pré-processamento - 1.2) Normalização - 1.2.2) Remoção de caracteres de controle
    @staticmethod
    def _unicode_normalize(text: str) -> str:
        """Normaliza para NFC e remove caracteres de controle exceto \\n e \\t."""
        text = unicodedata.normalize("NFC", text)
        # Remove ASCII ctrl chars (0–8, 11–31) mas mantém \n (10) e \t (9)
        return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)
    # Fim - 1) Pré-processamento - 1.2) Normalização - 1.2.1) Normalização Unicode NFC
    # Fim - 1) Pré-processamento - 1.2) Normalização - 1.2.2) Remoção de caracteres de controle

    # Início - 1) Pré-processamento - 1.2) Normalização - 1.2.3) Normalização de espaços múltiplos
    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        """Colapsa múltiplos espaços/tabs em um único espaço; preserva \\n."""
        text = re.sub(r"[ \t]+", " ", text)      # espaços/tabs → um espaço
        text = re.sub(r"\n{3,}", "\n\n", text)   # >2 quebras → 2 quebras
        return text.strip()
    # Fim - 1) Pré-processamento - 1.2) Normalização - 1.2.3) Normalização de espaços múltiplos

    # Início - 1) Pré-processamento - 1.2) Normalização - 1.2.4) Padronização de datas para ISO 8601
    @staticmethod
    def _normalize_date_iso(text: str) -> str:
        """
        Tenta padronizar datas para ISO (YYYY-MM-DD).
        Apenas formatos claramente dd/mm/yyyy são convertidos.
        Datas ambíguas (m/dd/yyyy americano) são mantidas como estão
        e marcadas para revisão posterior.
        """
        def replace_ddmmyyyy(m: re.Match) -> str:
            d, mo, y = m.group(1), m.group(2), m.group(3)
            try:
                dt = datetime.strptime(f"{d}/{mo}/{y}", "%d/%m/%Y")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                return m.group(0)  # mantém original se inválido

        def replace_ddmmyyyy_hhmm(m: re.Match) -> str:
            d, mo, y, hm = m.group(1), m.group(2), m.group(3), m.group(4)
            try:
                dt = datetime.strptime(f"{d}/{mo}/{y} {hm}", "%d/%m/%Y %H:%M")
                return dt.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                return m.group(0)

        def replace_ddmmyy(m: re.Match) -> str:
            d, mo, y = m.group(1), m.group(2), m.group(3)
            # Assume 20xx para anos <= 99
            full_year = "20" + y if int(y) <= 30 else "19" + y
            try:
                dt = datetime.strptime(f"{d}/{mo}/{full_year}", "%d/%m/%Y")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                return m.group(0)

        # Ordem importa: primeiro datetime, depois data simples
        text = _RE_DATE_DT.sub(replace_ddmmyyyy_hhmm, text)
        text = _RE_DATE_DMBR.sub(replace_ddmmyyyy, text)
        text = _RE_DATE_SHORT.sub(replace_ddmmyy, text)
        return text
    # Fim - 1) Pré-processamento - 1.2) Normalização - 1.2.4) Padronização de datas para ISO 8601

    # Início - 1) Pré-processamento - 1.2) Normalização - 1.2.5) Substituição de CPF por placeholder
    # Início - 1) Pré-processamento - 1.2) Normalização - 1.2.6) Substituição de telefone por placeholder
    # Início - 1) Pré-processamento - 1.2) Normalização - 1.2.7) Substituição de CEP por placeholder
    # Início - 1) Pré-processamento - 1.2) Normalização - 1.2.8) Substituição de e-mail por placeholder
    @staticmethod
    def _mask_phi_patterns(text: str) -> str:
        """Substitui padrões numéricos de PHI por placeholders."""
        text = _RE_CPF.sub(PHI_PLACEHOLDER["cpf"], text)
        text = _RE_PHONE.sub(PHI_PLACEHOLDER["telefone"], text)
        text = _RE_CEP.sub(PHI_PLACEHOLDER["cep"], text)
        text = _RE_EMAIL.sub(PHI_PLACEHOLDER["email"], text)
        return text
    # Fim - 1) Pré-processamento - 1.2) Normalização - 1.2.5) Substituição de CPF por placeholder
    # Fim - 1) Pré-processamento - 1.2) Normalização - 1.2.6) Substituição de telefone por placeholder
    # Fim - 1) Pré-processamento - 1.2) Normalização - 1.2.7) Substituição de CEP por placeholder
    # Fim - 1) Pré-processamento - 1.2) Normalização - 1.2.8) Substituição de e-mail por placeholder

    @staticmethod
    def _mask_dates(text: str) -> str:
        """Substitui datas (após normalização ISO) por placeholder."""
        text = re.sub(r"\b\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?\b", DATE_PLACEHOLDER, text)
        return text

    # ── Pipeline principal ──────────────────────────────────────────────────

    def normalize(self, text: str) -> str:
        """
        Aplica o pipeline completo de normalização.

        Args:
            text: Texto clínico bruto.

        Returns:
            Texto normalizado.
        """
        if not isinstance(text, str) or not text.strip():
            return ""

        text = self._unicode_normalize(text)
        text = self._normalize_whitespace(text)
        text = self._normalize_date_iso(text)

        if self.mask_phi:
            text = self._mask_phi_patterns(text)

        if self.mask_dates:
            text = self._mask_dates(text)

        if self.lowercase:
            text = text.lower()

        return text

    def normalize_batch(self, texts: list[str]) -> list[str]:
        """Aplica normalize() a uma lista de textos."""
        return [self.normalize(t) for t in texts]
