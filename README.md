# Anonimização de Textos Clínicos em Português Brasileiro

Dissertação de Mestrado — IFES Serra-ES  
Programa de Pós-Graduação em Computação Aplicada com ênfase em IA

## Resumo

Pipeline de anonimização automática de prescrições médicas e pareceres clínicos em português brasileiro, com base em Reconhecimento de Entidades Nomeadas (NER) e conformidade com a LGPD. Compara CRF baseline com modelos BERT (BioBERTpt, BERTimbau-leNER, mmBERT, ModernBERT) e avalia desempenho técnico, preservação de utilidade clínica (ΔF1) e cobertura de privacidade.

## Estrutura do Projeto

```
projeto/
├── data/               # dados (raw/ não versionado)
├── diagramas/          # diagramas drawio do pipeline
├── docs/               # documentação markdown por seção
├── src/                # código fonte
│   ├── analysis/       # análise exploratória
│   ├── preprocessing/  # pipeline de pré-processamento
│   ├── ner/            # modelos NER
│   ├── anonymization/  # anonimizador
│   └── evaluation/     # métricas TILD
├── notebooks/          # Jupyter (alguns executam no Colab)
├── outputs/            # resultados, modelos, figuras
├── webapp_django/      # interface web Django
└── tests/              # testes pytest
```

## Setup

```bash
# 1. Criar ambiente virtual
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Configurar variáveis de ambiente
cp .env.example .env
# editar .env com credenciais do PostgreSQL e paths dos dados

# 4. Configurar banco de dados
python webapp_django/manage.py migrate

# 5. Rodar a interface web
python webapp_django/manage.py runserver
```

## Dados

Os arquivos de dados brutos ficam em `data/raw/` e **não são versionados no git** por conterem informações hospitalares reais. São CSVs com separador `;`:
- `pareceres.csv` — campo `ds_parecer` é o texto-alvo
- `prescricoes.csv` — campo `ds_evolucao` é o texto-alvo

## Execução dos Experimentos

```bash
# Análise exploratória (gera Tabela 1)
python src/analysis/exploratory.py --input data/raw/ --output outputs/exploratory_analysis/

# Pré-processamento
python src/preprocessing/pipeline.py --input data/raw/ --output data/processed/

# Treinamento CRF (CPU)
python src/ner/train.py --model crf --data data/annotated/ --output outputs/models/

# Treinamento BERT (recomenda GPU — use notebooks/04_bert_finetuning.ipynb no Colab)
python src/ner/train.py --model biobertpt --data data/annotated/ --output outputs/models/

# Avaliação completa
python src/evaluation/run_evaluation.py --models outputs/models/ --output outputs/results/
```

## Contexto e Decisões

Ver `CLAUDE.md` na pasta pai (`Mestrado - Dissertação/`) para contexto completo do projeto, decisões metodológicas e estratégia de implementação.

## Referências Principais

- Schiezaro et al. (2026) — AnonyMed-BR, NER + LLM para anonimização PT-BR
- Almeida et al. (2026) — Benchmark NER clínico PT: mmBERT como SOTA
- Stubbs et al. (2015) — i2b2 2014, referência internacional de desidentificação
- Silva & Pazin-Filho (2025) — GLiNER para anonimização de prontuários PT-BR
