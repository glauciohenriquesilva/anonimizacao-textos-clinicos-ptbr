from django.db import models
from analise_exploratoria.models import Experimento


class ExecucaoPreprocessamento(models.Model):
    experimento = models.OneToOneField(
        Experimento, on_delete=models.CASCADE,
        null=True, blank=True, related_name='preprocessamento'
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    # Configuração da execução
    amostra_por_tipo    = models.IntegerField(null=True, blank=True)

    # Resultado do pipeline
    total_documentos    = models.IntegerField()
    total_sentencas     = models.IntegerField()

    # Distribuição por tipo de documento
    total_prescricoes   = models.IntegerField()
    total_pareceres     = models.IntegerField()

    # Distribuição de tipos de texto — Prescrições
    presc_texto_livre       = models.IntegerField(null=True, blank=True)
    presc_template          = models.IntegerField(null=True, blank=True)
    presc_pct_texto_livre   = models.FloatField(null=True, blank=True)
    presc_pct_template      = models.FloatField(null=True, blank=True)

    # Distribuição de tipos de texto — Pareceres
    par_texto_livre         = models.IntegerField(null=True, blank=True)
    par_template            = models.IntegerField(null=True, blank=True)
    par_pct_texto_livre     = models.FloatField(null=True, blank=True)
    par_pct_template        = models.FloatField(null=True, blank=True)

    # Caminhos dos arquivos gerados
    caminho_conll   = models.CharField(max_length=500, blank=True, null=True)
    caminho_jsonl   = models.CharField(max_length=500, blank=True, null=True)

    caminho_anotacao = models.CharField(max_length=500, blank=True, null=True)
    selecao_phi      = models.JSONField(null=True, blank=True)    

    obs = models.TextField(blank=True, null=True)

    class Meta:
        db_table     = 'tb_anonclin_execucao_preprocessamento'
        verbose_name = 'Execução de Pré-processamento'
        verbose_name_plural = 'Execuções de Pré-processamento'
        ordering     = ['-criado_em']

    def __str__(self):
        return f'Pré-processamento {self.criado_em:%d/%m/%Y %H:%M}'