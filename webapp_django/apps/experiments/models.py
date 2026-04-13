"""
Modelos do app Experiments.
Registra experimentos de treinamento NER e seus resultados.
"""
from django.db import models


class Experiment(models.Model):
    """
    Registro de um experimento de treinamento/avaliação NER.
    """

    STATUS_CHOICES = [
        ("pending",   "Aguardando"),
        ("running",   "Em execução"),
        ("completed", "Concluído"),
        ("failed",    "Falhou"),
    ]

    MODEL_CHOICES = [
        ("crf",               "CRF Baseline"),
        ("biobertpt_clin",    "BioBERTpt-clin"),
        ("bertimbau_lener",   "BERTimbau-leNER"),
        ("mmbert",            "mmBERT-base"),
        ("modernbert",        "ModernBERT-base"),
    ]

    SPLIT_STRATEGY_CHOICES = [
        ("random",               "Random Split"),
        ("iterative_stratified", "Iterative Stratification"),
    ]

    # Identificação
    name        = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    # Configuração
    model_name       = models.CharField(max_length=50, choices=MODEL_CHOICES)
    split_strategy   = models.CharField(max_length=30, choices=SPLIT_STRATEGY_CHOICES,
                                        default="iterative_stratified")
    train_ratio      = models.FloatField(default=0.70)
    dev_ratio        = models.FloatField(default=0.15)
    test_ratio       = models.FloatField(default=0.15)
    max_length       = models.IntegerField(default=512)
    batch_size       = models.IntegerField(default=16)
    learning_rate    = models.FloatField(default=2e-5)
    num_epochs       = models.IntegerField(default=10)
    random_seed      = models.IntegerField(default=42)
    only_phi_labels  = models.BooleanField(default=True,
                                           help_text="Apenas entidades PHI (anonimização)")

    # Dados
    n_train = models.IntegerField(default=0)
    n_dev   = models.IntegerField(default=0)
    n_test  = models.IntegerField(default=0)

    # Controle
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_log  = models.TextField(blank=True)
    colab_notebook = models.CharField(max_length=500, blank=True,
                                      help_text="URL do notebook Colab usado para treino GPU")

    class Meta:
        db_table = "experiment"
        verbose_name = "Experimento"
        verbose_name_plural = "Experimentos"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} [{self.model_name}] — {self.get_status_display()}"

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None


class ExperimentResult(models.Model):
    """
    Resultados numéricos de um experimento concluído.
    Mapeamento direto das métricas do framework TILD.
    """
    experiment = models.OneToOneField(Experiment, on_delete=models.CASCADE,
                                      related_name="result")

    # Dimensão T — Técnica (seqeval, entity-level)
    precision_overall = models.FloatField(null=True)
    recall_overall    = models.FloatField(null=True)
    f1_overall        = models.FloatField(null=True)
    per_entity_json   = models.JSONField(null=True, blank=True,
                                         help_text="F1 por tipo de entidade (JSON)")

    # Dimensão I — Informacional (ΔF1 downstream)
    f1_original    = models.FloatField(null=True, blank=True)
    f1_anonymized  = models.FloatField(null=True, blank=True)
    delta_f1       = models.FloatField(null=True, blank=True)

    # Dimensão L — Legal
    phi_coverage         = models.FloatField(null=True, blank=True)
    phi_precision_anon   = models.FloatField(null=True, blank=True)

    # Levenshtein (Pissarra et al. 2024)
    levenshtein_ratio = models.FloatField(null=True, blank=True)

    # Inter-anotadores
    cohen_kappa = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = "experiment_result"
        verbose_name = "Resultado de Experimento"

    def __str__(self) -> str:
        f1 = f"{self.f1_overall:.4f}" if self.f1_overall else "N/A"
        return f"Resultado {self.experiment.name} — F1={f1}"
