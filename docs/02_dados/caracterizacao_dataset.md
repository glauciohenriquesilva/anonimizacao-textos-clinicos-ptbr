# Caracterização do Dataset

> Fonte: Sistema de prontuário eletrônico MV — hospitais do Espírito Santo  
> Atualização: abril/2026

---

## Volumes

| Tipo | Registros totais | Observação |
|------|-----------------|------------|
| Prescrições | ~10.317.859 | Campo-alvo: `ds_evolucao` |
| Pareceres | ~426.706 | Campo-alvo: `ds_parecer` |
| **Total** | **~10.744.565** | |

---

## Estrutura dos CSVs

Separador: `;` | Encoding: UTF-8 | Campos texto: aspas duplas

### Colunas comuns (pareceres e prescrições)

```
cd_paciente; cd_convenio; nm_convenio; dt_atendimento; tp_atendimento;
cd_ori_ate; ds_ori_ate; cd_servico; ds_servico; cd_mot_alt; ds_mot_alt;
cd_cid; ds_cid; cd_tipo_internacao; ds_tipo_internacao;
cd_loc_proced; ds_loc_proced; cd_multi_empresa; ds_multi_empresa;
cd_especialid_atendimento; ds_especialid_atendimento;
cd_tip_mar; ds_tip_mar
```

### Colunas exclusivas

| Tipo | Colunas extras |
|------|---------------|
| Pareceres | `dt_parecer; ds_situacao; ds_parecer` |
| Prescrições | `dt_pre_med; ds_evolucao` |

---

## Formatos de data detectados

⚠️ **Quatro formatos coexistem no mesmo arquivo:**

| Formato | Exemplo | Observação |
|---------|---------|-----------|
| `dd/mm/yyyy` | `04/07/2026` | Padrão BR |
| `m/dd/yyyy` | `3/30/2026` | **Americano — presente nos dados!** |
| `dd/mm/yyyy HH:MM` | `04/08/2026 07:09` | Com horário |
| `dd/mm/yy` (no texto) | `18/02/26` | Ano abreviado dentro do texto clínico |

Normalização: `TextNormalizer._normalize_date_iso()` em `src/preprocessing/normalizer.py`

---

## Tipos de texto detectados

### 1. Texto livre clínico
Narrativa informal do médico. Exemplo:

```
Paciente de 68 anos, feminino, trazida pela filha ROSIANE DA SILVA RISO.
Queixa de dor lombar há 3 dias. PA: 140/90 mmHg. FC: 88 bpm.
Conduta: prescrever losartana 50mg VO 1x ao dia.
```

### 2. Template estruturado (UTI/Enfermagem)
Formulários com checkboxes. Exemplo:

```
SISTEMA NEUROLÓGICO: ( X ) Orientado ( ) Desorientado
SINAIS VITAIS: PA: 120/80 FC: 72 FR: 18 TAX: 36.5 SAT: 98%
ACESSO VASCULAR: ( X ) AVP MSD ( ) CVC
```

---

## PHI encontrado nos dados reais (exemplos)

| Categoria | Exemplo real |
|-----------|-------------|
| Nome paciente | "ROSIANE DA SILVA RISO" |
| Nome médico | "DRª MILENA GOTTARDI" |
| Endereço completo | "RUA MINAS GERAIS, Nº 20, BAIRRO VILA BETHANIA, VIANA-ES" |
| Telefone | "(27) 99516-5083" |
| Data no texto | "18/02/26", "30/07/2024" |
| Número exame | presente nos textos |

---

## Tamanho da amostra para anotação

> ⚠️ A definir na qualificação com o orientador.

Referência: AnonyMed-BR usou ~2.000 documentos; i2b2 2014 usou ~1.300 registros.

**Estimativa mínima recomendada:**
- 500–1000 sentenças anotadas para treinamento viável
- Estratificadas por tipo de texto (livre vs. template) e por especialidade médica
