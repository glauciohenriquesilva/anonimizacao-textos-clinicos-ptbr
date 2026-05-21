from django.db import models
from analise_exploratoria.models import Experimento


class ExecucaoAnotacao(models.Model):
    experimento = models.OneToOneField(
        Experimento, on_delete=models.CASCADE,
        null=True, blank=True, related_name='anotacao'
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    # 2.1.1 Amostra selecionada
    total_sentencas_amostra = models.IntegerField()

    # 2.1.5 Cohen's Kappa
    kappa               = models.FloatField(null=True, blank=True)
    kappa_meta_atingida = models.BooleanField(null=True, blank=True)
    concordancia_obs    = models.FloatField(null=True, blank=True)  # Po
    concordancia_esp    = models.FloatField(null=True, blank=True)  # Pe
    total_tokens_kappa  = models.IntegerField(null=True, blank=True)

    # 2.1.7 Corpus anotado final
    total_sentencas_anotadas = models.IntegerField(null=True, blank=True)
    distribuicao_entidades_json = models.JSONField(null=True, blank=True)
    caminho_conll_anotado = models.CharField(max_length=500, blank=True, null=True)

    obs = models.TextField(blank=True, null=True)

    class Meta:
        db_table     = 'tb_anonclin_execucao_anotacao'
        verbose_name = 'Execução de Anotação'
        verbose_name_plural = 'Execuções de Anotação'
        ordering     = ['-criado_em']

    def __str__(self):
        return f'Anotação {self.criado_em:%d/%m/%Y %H:%M} — κ={self.kappa}'


class ExecucaoDivisao(models.Model):
    experimento = models.OneToOneField(
        Experimento, on_delete=models.CASCADE,
        null=True, blank=True, related_name='divisao'
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    # 2.2.1 Splits
    total_treino = models.IntegerField()
    total_dev    = models.IntegerField()
    total_teste  = models.IntegerField()

    # 2.2.2 Verificação de distribuição
    verificacao_ok      = models.BooleanField()
    ausentes_dev_json   = models.JSONField(null=True, blank=True)
    ausentes_teste_json = models.JSONField(null=True, blank=True)
    distribuicao_json   = models.JSONField(null=True, blank=True)

    # 2.2.3 Caminhos dos arquivos
    caminho_train = models.CharField(max_length=500, blank=True, null=True)
    caminho_dev   = models.CharField(max_length=500, blank=True, null=True)
    caminho_teste = models.CharField(max_length=500, blank=True, null=True)

    obs = models.TextField(blank=True, null=True)

    class Meta:
        db_table     = 'tb_anonclin_execucao_divisao'
        verbose_name = 'Execução de Divisão'
        verbose_name_plural = 'Execuções de Divisão'
        ordering     = ['-criado_em']

    def __str__(self):
        return f'Divisão {self.criado_em:%d/%m/%Y %H:%M}'


class ExecucaoTreinamento(models.Model):
    MODELOS = [
        ('CRF',            'CRF Baseline'),
        ('BioBERTpt-clin', 'BioBERTpt-clin'),
        ('BERTimbau-leNER','BERTimbau-leNER'),
        ('mmBERT',         'mmBERT'),
        ('ModernBERT',     'ModernBERT'),
    ]

    experimento = models.ForeignKey(
        Experimento, on_delete=models.CASCADE,
        null=True, blank=True, related_name='treinamentos'
    )
    criado_em   = models.DateTimeField(auto_now_add=True)
    nome_modelo = models.CharField(max_length=50, choices=MODELOS)

    # Hiperparâmetros
    hiperparametros_json = models.JSONField(null=True, blank=True)

    # Resultado do treinamento
    epochs               = models.IntegerField(null=True, blank=True)
    tempo_treinamento_seg = models.FloatField(null=True, blank=True)
    classes_json         = models.JSONField(null=True, blank=True)
    caminho_modelo       = models.CharField(max_length=500, blank=True, null=True)

    obs = models.TextField(blank=True, null=True)

    class Meta:
        db_table     = 'tb_anonclin_execucao_treinamento'
        verbose_name = 'Execução de Treinamento'
        verbose_name_plural = 'Execuções de Treinamento'
        ordering     = ['-criado_em']

    def __str__(self):
        return f'{self.nome_modelo} — {self.criado_em:%d/%m/%Y %H:%M}'


class ExecucaoAvaliacao(models.Model):
    treinamento = models.OneToOneField(
        ExecucaoTreinamento, on_delete=models.CASCADE,
        related_name='avaliacao'
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    # 2.4.2 F1 entity-level
    f1_entity_micro = models.FloatField(null=True, blank=True)

    # 2.4.3 F1 por entidade
    f1_por_entidade_json = models.JSONField(null=True, blank=True)

    # 2.4.4 F1 token-level
    f1_token_macro    = models.FloatField(null=True, blank=True)
    f1_token_weighted = models.FloatField(null=True, blank=True)

    # Relatório completo (para exportação)
    relatorio_json = models.JSONField(null=True, blank=True)

    obs = models.TextField(blank=True, null=True)

    class Meta:
        db_table     = 'tb_anonclin_execucao_avaliacao'
        verbose_name = 'Execução de Avaliação'
        verbose_name_plural = 'Execuções de Avaliação'
        ordering     = ['-criado_em']

    def __str__(self):
        return f'Avaliação {self.treinamento.nome_modelo} — F1={self.f1_entity_micro}'