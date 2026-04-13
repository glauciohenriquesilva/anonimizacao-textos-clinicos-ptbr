# Decisões de Projeto — Pré-processamento

> Última atualização: abril/2026

---

## 1. Esquema de anotação: BIO (IOB2) vs. BILOU

**Decisão:** BIO (IOB2)

**Justificativa:**
- BIO é o padrão nas principais referências do domínio: SemClinBr, AnonyMed-BR, i2b2 2014
- Todos os cinco modelos comparados (CRF, BioBERTpt-clin, BERTimbau-leNER, mmBERT, ModernBERT) suportam BIO nativamente
- BILOU adiciona rótulos L-X e U-X, dobrando o espaço de labels sem ganho estatisticamente significativo em datasets < 50k tokens
- Comparação direta de F1 com benchmarks da literatura é direta em BIO

**Referências:** Stubbs et al. (2015) i2b2 2014; Almeida et al. (2026) SemClinBr

---

## 2. Divisão treino/dev/teste: Iterative Stratification vs. Random Split

**Decisão:** Iterative Stratification (MultilabelStratifiedShuffleSplit — iterstrat)

**Justificativa:**
- Entidades PHI são distribuídas de forma muito desigual (DATA >> DOCUMENTO >> ENDEREÇO)
- Random split pode gerar subconjuntos sem exemplos de entidades raras (ex.: HORA, INSTITUIÇÃO)
- Schiezaro et al. (2026) documentaram ganho de **+0.0742 F1** com Iterative Stratification vs. random no SemClinBr
- Reprodutibilidade: `random_state=42` fixado em todos os experimentos

**Proporções:** 70% treino / 15% dev / 15% teste

**Implementação:** `iterstrat.ml_stratifiers.MultilabelStratifiedShuffleSplit`

---

## 3. Tratamento de datas: normalização para ISO 8601

**Decisão:** Normalizar para YYYY-MM-DD antes da tokenização

**Justificativa:**
- Dataset contém 4 formatos de data inconsistentes no mesmo arquivo:
  - `dd/mm/yyyy` (ex.: `04/07/2026`) — padrão BR
  - `m/dd/yyyy` (ex.: `3/30/2026`) — **formato americano detectado nos dados reais**
  - `dd/mm/yyyy HH:MM` (ex.: `04/08/2026 07:09`)
  - `dd/mm/yy` dentro do texto (ex.: `18/02/26`)
- Normalização evita que o mesmo PHI seja representado de 4 formas diferentes para o NER
- Datas ambíguas `m/dd/yyyy` são mantidas como estão (risco de inversão de dia/mês) e marcadas com log

**Código:** `src/preprocessing/normalizer.py` → `_normalize_date_iso()`

---

## 4. Dois tipos de texto: texto livre vs. template estruturado

**Decisão:** Detectar e segmentar de forma diferenciada

**Justificativa:**
- Prescrições e pareceres contêm dois tipos radicalmente diferentes:
  - Texto livre clínico: narrativa informal do médico
  - Template estruturado: formulários UTI/enfermagem com checkboxes `( X )`
- Templates não devem ser segmentados por pontuação (cada campo é uma unidade)
- Detector: `classify_text_type()` em `src/analysis/exploratory.py`
  - Marcadores: `"( X )"`, `"SISTEMA NEUROLÓGICO"`, `"SINAIS VITAIS:"`, etc.

**Código:** `src/preprocessing/segmenter.py` → `segment_template()` vs `segment_free_text()`

---

## 5. Dicionário de abreviações médicas

**Decisão:** Manter abreviações no token de entrada; dicionário usado apenas para features CRF e análise exploratória

**Justificativa:**
- Modelos BERT aprendem representações contextuais — expandir abreviações pode remover informação contextual
- Para CRF, `is_abbreviation` é feature útil (booleano)
- Expansão só ativada explicitamente via `expand_abbrev=True` no pipeline

**Dicionário:** `src/preprocessing/abbreviations.py` — ~80 abreviações do domínio MV

**Abreviações críticas com duplo significado:**
- `PA` → pressão arterial (contexto clínico) vs. Pará (estado) — **não expandir automaticamente**
- `FC` → frequência cardíaca vs. Futsal Club — **não expandir automaticamente**
