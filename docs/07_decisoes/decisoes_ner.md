# Decisões de Projeto — Modelos NER

> Última atualização: abril/2026

---

## 1. Modelos selecionados para comparação

| # | Modelo | HuggingFace ID | Tipo | GPU |
|---|--------|---------------|------|-----|
| 1 | CRF Baseline | — | sklearn-crfsuite | CPU |
| 2 | BioBERTpt-clin | `pucpr/biobertpt-clin` | BERT clínico PT-BR | T4 |
| 3 | BERTimbau-leNER | `pierreguillou/bert-base-cased-pt-lenerbr` | BERT PT + NER | T4 |
| 4 | mmBERT-base | `jhu-clsp/mmBERT` | SOTA multilingual | T4 |
| 5 | ModernBERT-base | `answerdotai/ModernBERT-base` | Arquitetura moderna | A100 |

**Justificativa da seleção:**
- CRF: baseline clássico, sem dependência de GPU, interpretável
- BioBERTpt-clin: único BERT pré-treinado em corpus clínico PT-BR
- BERTimbau-leNER: melhor BERT PT-BR geral + fine-tuning no leNER-Br (jurídico, mas PT-BR)
- mmBERT: SOTA SemClinBr F1=0.7646 (Schiezaro 2026); usa Cascading Annealed Language Learning, 3T tokens
- ModernBERT: arquitetura moderna (RoPE, Flash Attention, ctx 8192); ainda não avaliado em PT clínico — **GAP original**

**Modelos excluídos (com justificativa):**
- GPT-4/Gemini: LLMs superam BERT em NER geral, mas não em PT clínico (Schiezaro 2026 mostra BERT superior); custo e privacidade incompatíveis com dados hospitalares reais

---

## 2. Hiperparâmetros de fine-tuning

Baseados nos defaults de Schiezaro et al. (2026) para SemClinBr:

| Parâmetro | Valor | Fonte |
|-----------|-------|-------|
| Learning rate | 2e-5 | Devlin et al. (2019) |
| Batch size | 16 | Schiezaro (2026) |
| Epochs | 10 (early stopping) | Schiezaro (2026) |
| Warmup ratio | 0.1 | HuggingFace default |
| Weight decay | 0.01 | HuggingFace default |
| Max length | 512 (BERT) / 8192 (ModernBERT) | Arquitetura |
| Random seed | 42 | Reprodutibilidade |

---

## 3. Avaliação: entity-level vs. token-level

**Decisão:** Reportar **entity-level** (seqeval) como métrica principal; token-level como complementar

**Justificativa:**
- Entity-level é o padrão do i2b2 2014 (Stubbs et al. 2015) e SemClinBr
- Permite comparação direta com literatura
- Token-level superestima performance em entidades multi-token

**Biblioteca:** seqeval (Nakayama 2018) — suporte nativo a BIO

---

## 4. Configuração especial ModernBERT

ModernBERT requer atenção especial:

- **Flash Attention:** instalar `flash-attn` no Colab para velocidade; funciona sem ele
- **Contexto 8192 tokens:** útil para templates longos; usar `batch_size=1` + `gradient_accumulation_steps=16`
- **Transformers:** requer `transformers >= 4.48`
- **GPU:** A100 recomendado; com T4 usar `max_length=512` (contexto reduzido)

---

## 5. Anotação gold standard

**Ferramenta:** Doccano (interface web, formato BIO nativo)
**Meta de kappa:** κ ≥ 0.80 (Cohen's Kappa entre 2 anotadores)
**Tamanho mínimo do corpus:** a definir na qualificação (sugestão: 500–1000 sentenças anotadas)
**Divisão:** Iterative Stratification 70/15/15

**Protocolo de adjudicação:** discordâncias resolvidas por consenso; casos duvidosos decididos pelo orientador
