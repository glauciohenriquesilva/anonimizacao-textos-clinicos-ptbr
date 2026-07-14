from django.db import models
from analise_exploratoria.models import Experimento


class ExecucaoAnonimizacao(models.Model):
    experimento = models.ForeignKey(
        Experimento, on_delete=models.CASCADE,
        null=True, blank=True, related_name='anonimizacoes'
    )
    criado_em   = models.DateTimeField(auto_now_add=True)
    nome_modelo = models.CharField(max_length=100, blank=True, default='')  # ex: CRF, BERTimbau-leNER-large

    # 3.1 Substituição por Marcadores
    total_documentos_anonimizados = models.IntegerField()
    total_spans_substituidos      = models.IntegerField()
    distribuicao_marcadores_json  = models.JSONField(null=True, blank=True)

    # 3.2 Avaliação de Privacidade — Dimensão L
    coverage        = models.FloatField(null=True, blank=True)  # Recall PHI
    precision_anon  = models.FloatField(null=True, blank=True)  # Precision PHI
    levenshtein_ratio = models.FloatField(null=True, blank=True)

    # 3.3 Avaliação de Utilidade — Dimensão I
    f1_downstream_original    = models.FloatField(null=True, blank=True)
    f1_downstream_anonimizado = models.FloatField(null=True, blank=True)
    delta_f1                  = models.FloatField(null=True, blank=True)
    delta_f1_por_entidade_json = models.JSONField(null=True, blank=True)

    # Caminhos dos arquivos gerados
    caminho_corpus_anonimizado = models.CharField(max_length=500, blank=True, null=True)

    obs = models.TextField(blank=True, null=True)

    class Meta:
        db_table     = 'tb_anonclin_execucao_anonimizacao'
        verbose_name = 'Execução de Anonimização'
        verbose_name_plural = 'Execuções de Anonimização'
        ordering     = ['-criado_em']

    @property
    def f1_anon(self):
        """F1 de anonimização = 2·Coverage·Precision_anon / (Coverage + Precision_anon)"""
        c, p = self.coverage, self.precision_anon
        if c and p and (c + p) > 0:
            return round(2 * c * p / (c + p), 4)
        return None

    def __str__(self):
        return f'Anonimização {self.criado_em:%d/%m/%Y %H:%M} [{self.nome_modelo}] Coverage={self.coverage}'