# Decisões de Projeto — Anonimização

> Última atualização: abril/2026

---

## 1. Estratégia: substituição por marcadores vs. surrogates

**Decisão:** Substituição por marcadores `[TIPO_N]`

**Justificativa:**
- Objetivo da dissertação é anonimização para pesquisa, não geração de dados sintéticos realistas
- Surrogates exigem geração de nomes/endereços sintéticos coerentes — complexidade desnecessária
- Marcadores são auditáveis: o revisor consegue identificar exatamente o que foi substituído
- Padrão usado pelo AnonyMed-BR (Schiezaro et al. 2026) — comparação direta de métricas

**Marcadores definidos:**

| Entidade | Marcador | Exemplo original | Após anonimização |
|----------|---------|-----------------|-------------------|
| PESSOA | `[PESSOA_1]` | "ROSIANE DA SILVA RISO" | `[PESSOA_1]` |
| DOCUMENTO | `[DOCUMENTO_1]` | "CNS: 12345678" | `[DOCUMENTO_1]` |
| ENDEREÇO | `[ENDEREÇO_1]` | "RUA MINAS GERAIS, Nº 20" | `[ENDEREÇO_1]` |
| CONTATO | `[CONTATO_1]` | "(27) 99516-5083" | `[CONTATO_1]` |
| DATA | `[DATA_1]` | "30/07/2024" | `[DATA_1]` |
| HORA | `[HORA_1]` | "07:09" | `[HORA_1]` |
| INSTITUIÇÃO | `[INSTITUIÇÃO_1]` | "HUCAM" | `[INSTITUIÇÃO_1]` |

**Consistência:** mesma entidade no mesmo documento recebe o mesmo número (ex.: "João Silva" → `[PESSOA_1]` em todas as ocorrências)

---

## 2. O que NÃO anonimizar

Entidades de **utilidade clínica** são preservadas para calcular ΔF1:

- MEDICAMENTO, DOSE, VIA, FREQUÊNCIA, DIAGNÓSTICO, PROCEDIMENTO
- Abreviações clínicas (LPP, SVD, etc.) — não são PHI
- CID-10 (ex.: J18.9) — código diagnóstico, não PHI

---

## 3. Pseudonimização de identificadores estruturados

Campos estruturados do CSV (`cd_paciente`, `cd_atendimento`) são **pseudonimizados** via hash SHA-256 em vez de substituídos por marcador, pois precisam manter a relação de unicidade:

```python
import hashlib
def pseudonymize(value: str, salt: str = "") -> str:
    return hashlib.sha256((salt + value).encode()).hexdigest()[:16]
```

O salt é definido no `.env` (variável `PSEUDONYM_SALT`) e nunca commitado.

---

## 4. Base legal: LGPD e HIPAA Safe Harbour

**Entidades PHI mapeadas conforme:**
- HIPAA Safe Harbour (18 categorias) — adaptado para PT-BR
- LGPD Art. 12 — dado anonimizado como não-dado pessoal
- i2b2 2014 PHI taxonomy (Stubbs et al. 2015)

**Referência:** Lopes et al. (2022); Rocha et al. (2023)
