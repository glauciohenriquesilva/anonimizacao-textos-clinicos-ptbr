# Framework de Avaliação TILD

> Referência principal: Schiezaro et al. (2026) — AnonyMed-BR

---

## Visão geral

O framework TILD avalia a anonimização em três dimensões complementares:

```
T — Técnica       → qualidade do NER em si (F1)
I — Informacional → utilidade clínica preservada (ΔF1)
L — Legal         → cobertura de privacidade (Coverage)
```

---

## T — Desempenho Técnico (NER)

Mede a qualidade do modelo NER em identificar entidades PHI.

| Métrica | Fórmula | Observação |
|---------|---------|-----------|
| Precision | TP / (TP + FP) | % das entidades preditas que são PHI real |
| Recall | TP / (TP + FN) | % das entidades PHI reais que foram encontradas |
| F1 | 2·P·R / (P+R) | Média harmônica |

**Avaliação:** entity-level, esquema BIO, biblioteca seqeval  
**Modo principal:** micro-averaged (todas as entidades juntas)  
**Modo complementar:** por tipo de entidade (PESSOA, DATA, etc.)

---

## I — Preservação de Utilidade (ΔF1)

Mede quanto de informação clínica **útil** foi perdida com a anonimização.

```
ΔF1 = F1_anonimizado − F1_original
```

**Protocolo:**
1. Treinar modelo downstream NER de utilidade (MEDICAMENTO, DOSE, VIA…) no corpus original
2. Aplicar anonimização PHI no corpus
3. Avaliar o mesmo modelo downstream no corpus anonimizado
4. ΔF1 mede a diferença de desempenho

**Interpretação:**
- ΔF1 ≈ 0 → anonimização não prejudicou a utilidade clínica ✓
- ΔF1 << 0 → muita informação clínica perdida ✗
- ΔF1 > 0 → improvável; indicaria erro na metodologia

**Vantagem vs. LLM-as-a-Judge:** reproduzível, não depende de modelo proprietário

---

## L — Proteção de Privacidade (Legal)

Mede a efetividade da anonimização sob perspectiva da LGPD.

| Métrica | Sinônimo NER | Fórmula | O que mede |
|---------|-------------|---------|-----------|
| Coverage | Recall | TP/(TP+FN) | % de PHI real que foi anonimizado |
| Precision_anon | Precision | TP/(TP+FP) | % do que foi anonimizado que era PHI real |

**Prioridade:** Coverage (recall) > Precision_anon  
Razão: falso negativo (PHI não anonimizado) é mais grave que falso positivo (algo anônimo anonimizado de novo).

---

## Métricas complementares (Pissarra et al. 2024)

| Sigla | Nome | O que mede |
|-------|------|-----------|
| LR | Levenshtein Ratio | Similaridade textual original ↔ anonimizado |
| ALID | Anonymization with Least Information Distortion | Equilíbrio privacidade/utilidade |
| LRDI | LR com Deleção/Inserção | Variante com penalidade diferenciada |
| LRQI | LR Quantificado por Instâncias | Normalizado por número de instâncias |

**Implementação:** `src/evaluation/metrics.py` → `AnonymizationMetrics.compute_levenshtein_ratio()`

---

## Quadro resumo — métricas reportadas na dissertação

| Dimensão | Métrica | Nível | Biblioteca |
|----------|---------|-------|-----------|
| T | P/R/F1 (entity-level) | Geral + por entidade | seqeval |
| T | P/R/F1 (token-level) | Complementar | seqeval |
| I | ΔF1 | Por entidade clínica | seqeval |
| L | Coverage (Recall) | Geral + por entidade PHI | seqeval |
| L | Precision_anon | Geral | seqeval |
| L | LR (Levenshtein) | Documento | python-Levenshtein |
| L | κ (Cohen's Kappa) | Inter-anotadores | sklearn |
