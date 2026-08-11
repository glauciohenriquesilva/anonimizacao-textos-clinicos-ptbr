from django.db import models
from analise_exploratoria.models import Experimento


class ExecucaoExtracaoMV(models.Model):
    """Registra uma execução do script extrair_mv_sqlite.py, disparado em background
    (subprocess) a partir da tela de Extração MV. Nunca armazena a senha do banco Oracle —
    ela só é passada para o ambiente do processo filho no momento do disparo."""

    STATUS_CHOICES = [
        ('em_execucao', 'Em execução'),
        ('concluido', 'Concluído'),
        ('erro', 'Erro'),
    ]

    experimento = models.ForeignKey(
        Experimento, on_delete=models.CASCADE,
        null=True, blank=True, related_name='extracoes_mv'
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    finalizado_em = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='em_execucao')
    pid = models.IntegerField(null=True, blank=True)

    # Parâmetros da execução (sem credenciais)
    hospitais_incluidos = models.CharField(max_length=50, blank=True)   # ex: "2,3,4,5,6"
    teto_prescricoes    = models.IntegerField(null=True, blank=True)
    batch_size           = models.IntegerField(null=True, blank=True)

    caminho_sqlite = models.CharField(max_length=500, blank=True, null=True)
    caminho_log    = models.CharField(max_length=500, blank=True, null=True)

    obs = models.TextField(blank=True, null=True)

    class Meta:
        db_table     = 'tb_anonclin_execucao_extracao_mv'
        verbose_name = 'Execução de Extração MV'
        verbose_name_plural = 'Execuções de Extração MV'
        ordering     = ['-criado_em']

    def __str__(self):
        return f'Extração MV {self.criado_em:%d/%m/%Y %H:%M} ({self.status})'


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