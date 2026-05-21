# Diário de Experimentos — Anonimização Clínica PT-BR

> **Objetivo:** Registrar decisões, erros, descobertas e workarounds ao longo da implementação.
> Esse arquivo alimenta diretamente a seção **Métodos** da dissertação e a **discussão** do artigo.
>
> **Como usar:** Cada entrada segue o modelo abaixo. Adicione em ordem cronológica.
> Use as tags para filtrar depois: `#preprocessamento` `#crf` `#bert` `#anotacao` `#avaliacao` `#infra` `#dados`

---

## Modelo de entrada

```
### [DATA] — Título curto da observação                    #tag

**Contexto:** O que você estava tentando fazer.
**Observação:** O que aconteceu (erro, comportamento inesperado, resultado).
**Decisão:** O que foi decidido a partir disso.
**Impacto metodológico:** Como isso muda o pipeline, os experimentos ou o texto.
```

---

## Entradas

---

### 2026-05-19 — Decisão de estratégia de segmentação de tokens                    #preprocessamento #bert

**Contexto:** Modelos BERT têm limite de 512 tokens. Prescrições longas (especialmente templates de UTI com múltiplos campos) estouravam esse limite facilmente.

**Observação:** Ao passar o texto completo de uma prescrição de UTI, o tokenizador do BERTimbau retornava sequências de 800–1200 tokens com frequência. Truncamento simples descartava entidades PHI que apareciam no final do texto.

**Decisão:** Segmentar cada prescrição/parecer em **linhas lógicas** antes de tokenizar. Cada linha vira uma sequência independente. Entidades que cruzam quebra de linha são raras e aceitáveis como perda.

**Impacto metodológico:** Adicionar subseção em Pré-processamento descrevendo a estratégia de *sentence splitting* específica para o domínio MV. Documentar estatísticas: distribuição de comprimento antes e depois da segmentação.

---

### 2026-05-19 — CRF confunde MEDICAMENTO com PESSOA                    #crf #ner

**Contexto:** Treinamento inicial do modelo CRF baseline usando features léxicas simples (prefixo, sufixo, caixa alta, vizinhança).

**Observação:** O CRF estava marcando nomes de medicamentos escritos em caixa alta (ex.: "DIPIRONA", "METFORMINA") como entidade PESSOA, especialmente quando apareciam no início de uma linha ou após dois-pontos — padrão similar ao de nomes de pacientes nas prescrições.

**Decisão:** Adicionar feature de **lista negra de medicamentos** (gazeteer) como feature booleana para o CRF. Usar lista do ANVISA/Rename como fonte. Avaliar se isso resolve ou se é necessário feature de posição no documento.

**Impacto metodológico:** Demonstra limitação estrutural dos modelos baseados em features manuais vs. contextual (BERT). Usar como motivação para os modelos neurais na seção de Resultados.

---

### 2026-05-19 — Estrutura real do CSV diverge da especificação original    #dados #preprocessamento

**Contexto:** Ao implementar a função `contar_hospitais` na Análise Exploratória, ocorreu `KeyError: 'cd_multi_empresa'`.

**Observação:** Os arquivos CSV reais do sistema MV não possuem as colunas de código (`cd_`) para a maioria dos campos — apenas as colunas descritivas (`ds_`). Exceção: `cd_paciente` existe (é o identificador PHI estruturado). A especificação inicial no CLAUDE.md estava incorreta.

**Decisão:** Usar `ds_multi_empresa` para hospitais, `ds_especialid_atendimento` para especialidades. Atualizar o CLAUDE.md com a estrutura real confirmada. Nunca assumir existência de `cd_` sem verificar o CSV real primeiro.

**Impacto metodológico:** Mencionar na dissertação que a documentação do sistema MV era incompleta e que foi necessária inspeção manual dos arquivos para mapear o schema real.

---

### 2026-05-19 — Distribuição de tokens fortemente assimétrica (cauda longa)    #dados #preprocessamento #bert

**Contexto:** Geração do histograma de tokens (0.5.2) na Análise Exploratória com amostra de 2.000 registros.

**Observação:** Tanto prescrições quanto pareceres mostram distribuição com cauda longa pronunciada. A grande maioria dos documentos tem menos de 470 tokens (prescrições) e menos de 63 tokens (pareceres). Porém existe uma cauda de documentos com 1.400–4.600 tokens — provavelmente templates de UTI com múltiplos campos preenchidos.

**Decisão:** Confirma a necessidade de estratégia de segmentação antes do BERT (limite 512 tokens). Documentar o percentil 95 e 99 da distribuição para justificar o ponto de corte da segmentação.

**Impacto metodológico:** Usar os histogramas como Figura 1 ou Figura 2 na seção de Caracterização do Dataset da dissertação. Reforça a decisão de segmentação por linha/campo para templates.

---

### 2026-05-19 — Amostra de 2.000 registros (1.000 + 1.000) para desenvolvimento    #dados #infra

**Contexto:** Dataset completo tem 10,7 milhões de registros. Ciclo de desenvolvimento inviável com o dataset completo em máquina local.

**Observação:** Amostra de 1.000 prescrições + 1.000 pareceres processa em menos de 2 segundos na Análise Exploratória. Suficiente para validar pipeline end-to-end.

**Decisão:** Usar amostra de 1.000+1.000 para desenvolvimento e testes unitários. Escalar para o dataset completo apenas para os experimentos finais (rodar no servidor do IFES ou Colab Pro). Documentar o tamanho da amostra em cada execução via campo `obs` na tabela `tb_anonclin_execucao_analise`.

**Impacto metodológico:** Reportar na dissertação que todos os experimentos de desenvolvimento foram validados em amostra estratificada antes de escalar.

---

### 2026-05-19 — Estratégia de segmentação dual (texto livre vs. template)    #preprocessamento

**Contexto:** Implementação do grupo 1.3) Segmentação em Sentenças.

**Observação:** Um único segmentador por pontuação não funciona para os dois tipos de texto do dataset. Templates de UTI têm poucos pontos finais — a estrutura é dada por quebras de linha (`\n`). Texto livre clínico usa pontuação normalmente.

**Decisão:** Segmentação dual: detectar tipo do documento (1.3.1) e aplicar estratégia específica — `segmentar_texto_livre` para narrativas, `segmentar_template` para formulários. Abreviações médicas protegidas com placeholder `§` antes de segmentar e restauradas depois.

**Impacto metodológico:** Descrever na dissertação como a heterogeneidade do dataset exigiu duas estratégias de segmentação. Avaliar na seção de Pré-processamento o impacto do filtro de sentenças curtas (1.3.5) na redução de ruído.

---

### 2026-05-21 — Colunas de data específica do documento ausentes no CSV real    #dados #preprocessamento

**Contexto:** Implementação de `selecionar_colunas` no pré-processamento tentou acessar `dt_pre_med` (prescrições) e `dt_parecer` (pareceres), conforme especificado no CLAUDE.md.

**Observação:** Essas colunas não existem nos arquivos CSV reais. Ambas as tabelas compartilham exatamente as mesmas colunas, diferindo apenas na coluna de texto (`ds_evolucao` vs `ds_parecer`). A única data disponível é `dt_atendimento`. Erro: `KeyError: "['dt_pre_med'] not in index"`.

**Decisão:** Usar apenas `dt_atendimento` como referência temporal para ambos os tipos de documento. Remover `dt_pre_med` e `dt_parecer` da seleção de colunas.

**Impacto metodológico:** A data de anonimização será baseada em `dt_atendimento`. Atualizar o CLAUDE.md para refletir o schema real confirmado.

---

<!-- PRÓXIMAS ENTRADAS ABAIXO -->
