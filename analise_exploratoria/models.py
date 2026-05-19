from django.db import models

# Create your models here.
from django.db import models

class ExecucaoAnalise(models.Model):
    criado_em = models.DateTimeField(auto_now_add=True)
    
    # 0.2 Estatísticas Descritivas
    total_registros = models.IntegerField()
    total_prescricoes = models.IntegerField()
    total_pareceres = models.IntegerField()
    pacientes_unicos = models.IntegerField()
    periodo_inicio = models.DateField(null=True)
    periodo_fim = models.DateField(null=True)
    total_hospitais = models.IntegerField()

    # 0.3 Distribuição de Tokens — Prescrições
    tokens_presc_min = models.IntegerField()
    tokens_presc_media = models.FloatField()
    tokens_presc_mediana = models.IntegerField()
    tokens_presc_max = models.IntegerField()
    tokens_presc_p25 = models.IntegerField()
    tokens_presc_p75 = models.IntegerField()

    # 0.3 Distribuição de Tokens — Pareceres
    tokens_par_min = models.IntegerField()
    tokens_par_media = models.FloatField()
    tokens_par_mediana = models.IntegerField()
    tokens_par_max = models.IntegerField()
    tokens_par_p25 = models.IntegerField()
    tokens_par_p75 = models.IntegerField()

    # 0.4 Classificação do Tipo de Texto — Prescrições
    presc_texto_livre = models.IntegerField()
    presc_template = models.IntegerField()
    presc_pct_texto_livre = models.FloatField()
    presc_pct_template = models.FloatField()

    # 0.4 Classificação do Tipo de Texto — Pareceres
    par_texto_livre = models.IntegerField()
    par_template = models.IntegerField()
    par_pct_texto_livre = models.FloatField()
    par_pct_template = models.FloatField()

    # Observações livres sobre esta execução
    obs = models.TextField(blank=True, null=True)

    # 0.5 Geração de Saídas
    especialidades_json = models.JSONField(null=True, blank=True)
    
    class Meta:
        db_table = 'tb_anonclin_execucao_analise'
        verbose_name = 'Execução de Análise'
        verbose_name_plural = 'Execuções de Análise'
        ordering = ['-criado_em']

    def __str__(self):
        return f'Análise {self.criado_em:%d/%m/%Y %H:%M}'