"""
Modelos do app Dataset.
Armazena documentos clínicos importados e metadados de anotação.
"""
from django.db import models


class ClinicalDocument(models.Model):
    """
    Representa um documento clínico (prescrição ou parecer).
    Armazena texto bruto, texto pré-processado e metadados.
    """

    DOC_TYPE_CHOICES = [
        ("prescricao", "Prescrição"),
        ("parecer", "Parecer"),
    ]

    TEXT_TYPE_CHOICES = [
        ("texto_livre", "Texto Livre"),
        ("template_estruturado", "Template Estruturado"),
    ]

    # Identificadores
    cd_paciente    = models.CharField(max_length=50, blank=True, db_index=True)
    doc_type       = models.CharField(max_length=20, choices=DOC_TYPE_CHOICES)

    # Texto
    raw_text        = models.TextField(verbose_name="Texto bruto")
    processed_text  = models.TextField(blank=True, verbose_name="Texto normalizado")
    text_type       = models.CharField(max_length=30, choices=TEXT_TYPE_CHOICES, blank=True)

    # Metadados
    doc_date         = models.DateField(null=True, blank=True)
    hospital         = models.CharField(max_length=200, blank=True)
    specialty        = models.CharField(max_length=200, blank=True)
    token_count      = models.IntegerField(default=0)
    char_count       = models.IntegerField(default=0)
    sentence_count   = models.IntegerField(default=0)

    # Controle
    imported_at     = models.DateTimeField(auto_now_add=True)
    is_preprocessed = models.BooleanField(default=False)
    is_annotated    = models.BooleanField(default=False)
    is_anonymized   = models.BooleanField(default=False)

    class Meta:
        db_table = "tb_texto_clinico"
        verbose_name = "Documento Clínico"
        verbose_name_plural = "Documentos Clínicos"
        ordering = ["-imported_at"]
        indexes = [
            models.Index(fields=["doc_type", "text_type"]),
            models.Index(fields=["cd_paciente"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_doc_type_display()} | {self.cd_paciente}"


class AnnotatedSentence(models.Model):
    """
    Sentença anotada com rótulos BIO.
    Unidade básica de treinamento e avaliação NER.
    """

    SPLIT_CHOICES = [
        ("train", "Treino"),
        ("dev", "Validação"),
        ("test", "Teste"),
    ]

    document   = models.ForeignKey(ClinicalDocument, on_delete=models.CASCADE,
                                   related_name="sentences")
    sentence   = models.TextField(verbose_name="Sentença")
    tokens     = models.JSONField(default=list, verbose_name="Tokens")
    labels     = models.JSONField(default=list, verbose_name="Rótulos BIO")
    split      = models.CharField(max_length=10, choices=SPLIT_CHOICES, blank=True)
    sentence_index = models.IntegerField(default=0)

    # Concordância inter-anotadores
    annotator_1_labels = models.JSONField(null=True, blank=True)
    annotator_2_labels = models.JSONField(null=True, blank=True)
    cohen_kappa        = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = "annotated_sentence"
        verbose_name = "Sentença Anotada"
        verbose_name_plural = "Sentenças Anotadas"
        ordering = ["document", "sentence_index"]

    def __str__(self) -> str:
        return f"Sent {self.sentence_index} | {self.sentence[:60]}..."


class ImportBatch(models.Model):
    """Registro de um lote de importação de CSVs."""
    filename      = models.CharField(max_length=255)
    doc_type      = models.CharField(max_length=20)
    total_records = models.IntegerField(default=0)
    imported_ok   = models.IntegerField(default=0)
    imported_at   = models.DateTimeField(auto_now_add=True)
    notes         = models.TextField(blank=True)

    class Meta:
        db_table = "import_batch"
        verbose_name = "Lote de Importação"
        verbose_name_plural = "Lotes de Importação"
        ordering = ["-imported_at"]

    def __str__(self) -> str:
        return f"{self.filename} ({self.imported_at:%d/%m/%Y %H:%M})"
