# Design do Corpus — Decisões Metodológicas

> Documento gerado após conclusão do Experimento 001 (julho/2026).
> Registra as lições aprendidas e as decisões que orientam o Experimento 002.
> Serve como referência para a dissertação, o artigo e as reuniões de orientação.

---

## 1. Lição principal do Experimento 001

**A qualidade e a diversidade do corpus de anotação são determinantes para o desempenho dos modelos NER.**

No Exp 001, os dados foram extraídos do banco de forma sequencial (primeiros 5.000 registros) sem nenhum critério de distribuição de PHI. Isso gerou um corpus com distribuição desequilibrada de entidades:

| PHI | n total (estimado) | n test set | Melhor F1 (BERTimbau-L) |
|-----|-------------------|------------|------------------------|
| PESSOA | ~853 | 128 | 0.8712 ✅ |
| INSTITUICAO | ~500 | 75 | 0.6711 ✅ |
| ENDERECO | ~313 | 47 | 0.7579 ✅ |
| HORA | ~200 | 30 | 0.5231 ⚠️ |
| CONTATO | ~93 | 14 | 0.7692 ⚠️ |
| DOCUMENTO | ~53 | 8 | 0.1667 ❌ |

**Conclusão:** DOCUMENTO teve F1=0.17 com apenas ~53 exemplos — insuficiente para o modelo aprender o padrão. A literatura de NER com BERT aponta 100 exemplos de treino como mínimo para generalização razoável. ENDERECO e INSTITUICAO tiveram resultados aceitáveis mas podem melhorar com mais dados.

---

## 2. Problema da seleção sequencial

Pegar os primeiros N registros do banco introduz **viés temporal**: todos os registros são do mesmo período, dos mesmos médicos, com padrões de escrita similares. O modelo aprende aquele recorte — não o dataset como um todo.

**Solução para o Exp 002:** seleção aleatória em cada bloco de extração.

---

## 3. Tipos de texto: pareceres vs prescrições

O corpus do MV contém dois tipos de texto com características radicalmente diferentes:

**Pareceres** (`ds_parecer`): narrativa clínica do médico — acompanhamento do paciente, história clínica, evolução. Texto livre, rico em PHI contextual (PESSOA, ENDERECO, INSTITUICAO). São 426.706 registros no banco.

**Prescrições** (`ds_evolucao`): estruturado como "receita" — medicamentos, doses, procedimentos a executar. Menos PHI contextual, mais padronizado. São 10.317.859 registros no banco.

**Decisão:** o corpus do Exp 002 deve ter proporção maior de pareceres do que sua representação natural no banco (1:24), pois pareceres concentram o PHI contextual que o modelo NER precisa aprender.

---

## 4. PHI tratado por regex vs PHI tratado pelo modelo NER

O pipeline é híbrido: nem toda entidade PHI precisa ser aprendida pelo modelo.

| PHI | Camada | Impacto no corpus |
|-----|--------|-------------------|
| DATA | Regex (`__DATA__`) | Não precisa de quota — aparece naturalmente em todo texto clínico |
| HORA | Regex (`__HORA__`) | Não precisa de quota — aparece naturalmente |
| CONTATO (telefone, e-mail) | Regex | Não precisa de quota — aparece naturalmente |
| PESSOA | NER | Quota mínima obrigatória |
| ENDERECO | NER | Quota mínima obrigatória |
| INSTITUICAO | NER | Quota mínima obrigatória |
| DOCUMENTO | NER | Quota mínima obrigatória — entidade crítica |

DATA/HORA/CONTATO devem ser anotadas quando aparecerem, mas a estratégia de extração do banco não precisa buscá-las ativamente. O foco da extração é nas 4 entidades NER.

---

## 5. Quotas mínimas de PHI para o Exp 002

Baseadas nos resultados do Exp 001 e na literatura (mínimo de 100 exemplos de treino para BERT):

| PHI | Quota mínima (corpus total) | Mínimo aceitável | Justificativa |
|-----|----------------------------|-----------------|---------------|
| PESSOA | >= 1000 | 800 | F1=0.87 com ~853 — ampliar consolida o resultado |
| INSTITUICAO | >= 800 | 600 | F1=0.67 com ~500 — mais dados deve melhorar |
| ENDERECO | >= 500 | 350 | F1=0.76 com ~313 — resultado bom, manter e ampliar |
| DOCUMENTO | >= 250 | 150 | F1=0.17 com ~53 — gargalo crítico do Exp 001 |

**Nota sobre DOCUMENTO:** médicos raramente escrevem RG/CNS/CNH no texto clínico livre — esses dados ficam no cadastro administrativo do MV. A raridade é estrutural, não falha de amostragem. Se 250 não for atingível, 150 é o mínimo aceitável com respaldo na literatura.

---

## 6. Estratégia de extração do banco (Exp 002)

Extração em blocos segmentados por objetivo, todos com seleção aleatória:

```sql
-- Bloco 1: pareceres gerais — cobre PESSOA e INSTITUICAO
SELECT TOP 2000 ds_parecer, [demais colunas]
FROM pareceres
ORDER BY NEWID()

-- Bloco 2: pareceres com provável ENDERECO
SELECT TOP 500 ds_parecer, [demais colunas]
FROM pareceres
WHERE ds_parecer LIKE '%Rua %'
   OR ds_parecer LIKE '%Avenida %'
   OR ds_parecer LIKE '%Bairro %'
   OR ds_parecer LIKE '%CEP%'
ORDER BY NEWID()

-- Bloco 3: busca agressiva por DOCUMENTO (alto índice de falso positivo esperado)
SELECT TOP 1000 ds_parecer, [demais colunas]
FROM pareceres
WHERE ds_parecer LIKE '% RG %'
   OR ds_parecer LIKE '% CNS %'
   OR ds_parecer LIKE '% CNH %'
   OR ds_parecer LIKE '%RG:%'
   OR ds_parecer LIKE '%CNS:%'
ORDER BY NEWID()

-- Bloco 4: prescrições — diversidade de tipo textual
SELECT TOP 500 ds_evolucao, [demais colunas]
FROM prescricoes
ORDER BY NEWID()
```

---

## 7. Análise exploratória antes da anotação

Antes de abrir o Doccano para anotação:
1. Rodar o modelo do Exp 001 (BERTimbau-leNER-large) sobre os registros extraídos
2. Estimar a distribuição de PHI por entidade
3. Verificar se as quotas mínimas serão atingidas
4. Ajustar os blocos de extração se necessário

Lição do Exp 001: a anotação começou sem verificar se a amostra tinha o que era necessário.

---

## 8. Curva de aprendizado (plano B — pós Exp 002)

**Decisão:** fazer o Exp 002 completo com 5000 sentenças. Se houver tempo, treinar os modelos em subconjuntos (1000, 2000, 3000, 5000) usando o mesmo test set fixo.

Não requer anotação adicional — os subconjuntos são extraídos das 5000 sentenças já anotadas.

**Valor científico:** responde "quantos exemplos anotados cada entidade PHI precisa para atingir F1 aceitável em texto clínico PT-BR?" — não explorado pelos artigos de referência.

**Condição:** somente se o Exp 002 estiver concluído com tempo disponível antes da defesa.

---

## 9. Test set fixo

Para comparações válidas entre rodadas, o test set deve ser fixo e anotado antes de qualquer treinamento.

Proporção: 70% treino / 15% dev / 15% teste (Iterative Stratification).
As 750 sentenças do test set não participam de nenhuma rodada de treino em nenhuma circunstância.

---

## 10. Escopo dos hospitais — exclusão do hospital pediátrico

O banco MV contém dados de 5 hospitais do Espírito Santo:
- 1 hospital exclusivamente pediátrico (pacientes até 18 anos)
- 4 hospitais gerais (atendimento predominantemente adulto)

**Decisão:** excluir o hospital pediátrico do corpus do Exp 002 (e retrospectivamente do Exp 001).

**Justificativa (dois motivos complementares):**

1. **Ética/legal:** registros de pacientes menores de 18 anos possuem proteção adicional prevista na LGPD e nas regulamentações do CFM, exigindo salvaguardas éticas além do escopo desta pesquisa.

2. **Padrão de texto:** o texto clínico pediátrico apresenta padrões de PHI distintos do adulto — PESSOA refere-se predominantemente a responsáveis/pais (não ao paciente), o vocabulário clínico difere significativamente e as estruturas de prescrição são diferentes. Incluí-lo introduziria heterogeneidade desnecessária no corpus.

**Impacto nos SQLs:** adicionar filtro de exclusão do hospital pediátrico em todos os blocos de extração.
