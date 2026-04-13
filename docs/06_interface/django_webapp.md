# Interface Web — Django App

> Stack: Django 4.2 + PostgreSQL + Bootstrap 5 (sugerido para os templates)

---

## Módulos da aplicação

### 1. Dashboard (`/`)
- Estatísticas gerais: total de documentos, prescrições vs. pareceres
- Status dos experimentos (pendentes, em execução, concluídos)
- Link rápido para os últimos experimentos executados

### 2. Dataset (`/dataset/`)

| Rota | Descrição |
|------|-----------|
| `/dataset/` | Lista de documentos com filtro por tipo e busca textual |
| `/dataset/importar/` | Upload de CSV (prescrições ou pareceres) |
| `/dataset/<pk>/` | Detalhe: texto bruto vs. texto normalizado lado a lado |
| `/dataset/explorar/` | Análise exploratória interativa (executa `exploratory.py`) |

### 3. Experimentos (`/experimentos/`)

| Rota | Descrição |
|------|-----------|
| `/experimentos/` | Lista de experimentos com F1 e status |
| `/experimentos/novo/` | Criar novo experimento (formulário de configuração) |
| `/experimentos/<pk>/` | Detalhe: configuração + resultados TILD |
| `/experimentos/<pk>/run/` | Executar CRF local (BERT: link para notebook Colab) |

### 4. Anonimizador (`/anonimizar/`)

| Rota | Descrição |
|------|-----------|
| `/anonimizar/` | Página inicial do módulo |
| `/anonimizar/demo/` | Demo interativa: digitar texto → ver anonimização |
| `/anonimizar/batch/` | Anonimização em lote (requer modelo treinado) |

### 5. Resultados (`/resultados/`)

| Rota | Descrição |
|------|-----------|
| `/resultados/` | Tabela comparativa de todos os modelos |
| `/resultados/comparar/` | Gráfico de barras F1 × modelo (Chart.js) |
| `/resultados/exportar/` | Download CSV para dissertação |

---

## Configuração do banco de dados

```env
DB_NAME=anonimizacao_clinica
DB_USER=postgres
DB_PASSWORD=sua_senha
DB_HOST=localhost
DB_PORT=5432
```

**Setup inicial:**
```bash
# 1. Criar banco no PostgreSQL
createdb anonimizacao_clinica

# 2. Aplicar migrations
python manage.py makemigrations dataset experiments
python manage.py migrate

# 3. Criar superusuário
python manage.py createsuperuser

# 4. Iniciar servidor
python manage.py runserver
```

---

## Templates a criar

Os templates HTML não foram gerados automaticamente — criar em `webapp_django/templates/`:

```
templates/
├── base.html                    # Layout base com navbar
├── dashboard/
│   └── index.html
├── dataset/
│   ├── list.html
│   ├── detail.html
│   ├── import.html
│   └── exploratory.html
├── experiments/
│   ├── list.html
│   ├── detail.html
│   └── create.html
├── anonymizer/
│   ├── home.html
│   ├── demo.html
│   └── batch.html
└── results/
    ├── dashboard.html
    ├── compare.html
    └── (export: retorna CSV direto)
```

**Sugestão:** usar Bootstrap 5 via CDN para agilizar o desenvolvimento dos templates.
