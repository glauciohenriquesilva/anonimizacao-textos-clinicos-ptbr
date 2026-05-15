"""
Migration inicial do app NER.

As tabelas `experiment` e `experiment_result` já existem no PostgreSQL
(criadas pelo app legado `experiments`). Esta migration descreve o schema
atual para que o Django reconheça o estado — execute com:

    python manage.py migrate --fake-initial ner

O flag --fake-initial marca a migration como aplicada sem executar SQL,
preservando os dados existentes.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Experiment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                ("model_name", models.CharField(
                    choices=[
                        ("crf",             "CRF Baseline"),
                        ("biobertpt_clin",  "BioBERTpt-clin"),
                        ("bertimbau_lener", "BERTimbau-leNER"),
                        ("mmbert",          "mmBERT-base"),
                        ("modernbert",      "ModernBERT-base"),
                    ],
                    max_length=50,
                )),
                ("split_strategy", models.CharField(
                    choices=[
                        ("random",               "Random Split"),
                        ("iterative_stratified", "Iterative Stratification"),
                    ],
                    default="iterative_stratified",
                    max_length=30,
                )),
                ("train_ratio",     models.FloatField(default=0.7)),
                ("dev_ratio",       models.FloatField(default=0.15)),
                ("test_ratio",      models.FloatField(default=0.15)),
                ("max_length",      models.IntegerField(default=512)),
                ("batch_size",      models.IntegerField(default=16)),
                ("learning_rate",   models.FloatField(default=2e-05)),
                ("num_epochs",      models.IntegerField(default=10)),
                ("random_seed",     models.IntegerField(default=42)),
                ("only_phi_labels", models.BooleanField(default=True)),
                ("n_train",         models.IntegerField(default=0)),
                ("n_dev",           models.IntegerField(default=0)),
                ("n_test",          models.IntegerField(default=0)),
                ("status", models.CharField(
                    choices=[
                        ("pending",   "Aguardando"),
                        ("running",   "Em execução"),
                        ("completed", "Concluído"),
                        ("failed",    "Falhou"),
                    ],
                    default="pending",
                    max_length=20,
                )),
                ("created_at",     models.DateTimeField(auto_now_add=True)),
                ("started_at",     models.DateTimeField(blank=True, null=True)),
                ("finished_at",    models.DateTimeField(blank=True, null=True)),
                ("error_log",      models.TextField(blank=True)),
                ("colab_notebook", models.CharField(blank=True, max_length=500)),
            ],
            options={
                "db_table": "experiment",
                "verbose_name": "Experimento",
                "verbose_name_plural": "Experimentos",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="ExperimentResult",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("experiment", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="result",
                    to="ner.experiment",
                )),
                ("precision_overall",   models.FloatField(null=True)),
                ("recall_overall",      models.FloatField(null=True)),
                ("f1_overall",          models.FloatField(null=True)),
                ("per_entity_json",     models.JSONField(blank=True, null=True)),
                ("f1_original",         models.FloatField(blank=True, null=True)),
                ("f1_anonymized",       models.FloatField(blank=True, null=True)),
                ("delta_f1",            models.FloatField(blank=True, null=True)),
                ("phi_coverage",        models.FloatField(blank=True, null=True)),
                ("phi_precision_anon",  models.FloatField(blank=True, null=True)),
                ("levenshtein_ratio",   models.FloatField(blank=True, null=True)),
                ("cohen_kappa",         models.FloatField(blank=True, null=True)),
            ],
            options={
                "db_table": "experiment_result",
                "verbose_name": "Resultado de Experimento",
            },
        ),
    ]
