from django.db import models
from django.contrib.auth.models import User
from analise_exploratoria.models import Experimento


class SessaoAnotacao(models.Model):
    """Representa uma rodada de anotação — um corpus sendo anotado por um grupo de anotadores."""
    experimento = models.ForeignKey(
        Experimento, on_delete=models.CASCADE,
        null=True, blank=True, related_name='sessoes_anotacao'
    )
    criado_em   = models.DateTimeField(auto_now_add=True)
    nome        = models.CharField(max_length=200)
    descricao   = models.TextField(blank=True, null=True)
    encerrada   = models.BooleanField(default=False)
    obs         = models.TextField(blank=True, null=True)

    class Meta:
        db_table     = 'tb_anonclin_anotador_sessao'
        verbose_name = 'Sessão de Anotação'
        ordering     = ['-criado_em']

    def __str__(self):
        return f'[{self.id}] {self.nome}'


class Sentenca(models.Model):
    """Uma sentença do corpus a ser anotada."""
    sessao    = models.ForeignKey(SessaoAnotacao, on_delete=models.CASCADE, related_name='sentencas')
    doc_id    = models.IntegerField()
    doc_type  = models.CharField(max_length=20)
    ordem     = models.IntegerField()
    tokens    = models.JSONField()  # lista de tokens: ['Paciente', 'João', 'Silva', ',', ...]

    class Meta:
        db_table     = 'tb_anonclin_anotador_sentenca'
        verbose_name = 'Sentença'
        ordering     = ['ordem']

    def __str__(self):
        return f'Sentença {self.ordem} — doc {self.doc_id}'


class AnotacaoToken(models.Model):
    """Label BIO atribuída por um anotador a um token específico de uma sentença."""
    LABELS = [
        ('O',             'O — Fora de entidade'),
        ('B-PESSOA',      'B-PESSOA'),
        ('I-PESSOA',      'I-PESSOA'),
        ('B-DATA',        'B-DATA'),
        ('I-DATA',        'I-DATA'),
        ('B-ENDERECO',    'B-ENDERECO'),
        ('I-ENDERECO',    'I-ENDERECO'),
        ('B-CONTATO',     'B-CONTATO'),
        ('I-CONTATO',     'I-CONTATO'),
        ('B-DOCUMENTO',   'B-DOCUMENTO'),
        ('I-DOCUMENTO',   'I-DOCUMENTO'),
        ('B-HORA',        'B-HORA'),
        ('I-HORA',        'I-HORA'),
        ('B-INSTITUICAO', 'B-INSTITUICAO'),
        ('I-INSTITUICAO', 'I-INSTITUICAO'),
    ]

    sentenca    = models.ForeignKey(Sentenca, on_delete=models.CASCADE, related_name='anotacoes')
    anotador    = models.ForeignKey(User, on_delete=models.CASCADE, related_name='anotacoes')
    posicao     = models.IntegerField()   # índice do token na sentença
    label       = models.CharField(max_length=20, choices=LABELS, default='O')
    criado_em   = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table        = 'tb_anonclin_anotador_token'
        verbose_name    = 'Anotação de Token'
        unique_together = [('sentenca', 'anotador', 'posicao')]
        ordering        = ['sentenca', 'posicao']

    def __str__(self):
        return f'Sentença {self.sentenca.ordem} — pos {self.posicao} — {self.label}'


class AdjudicacaoToken(models.Model):
    """Label final após adjudicação de discordâncias entre anotadores."""
    sentenca  = models.ForeignKey(Sentenca, on_delete=models.CASCADE, related_name='adjudicacoes')
    posicao   = models.IntegerField()
    label     = models.CharField(max_length=20)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table        = 'tb_anonclin_anotador_adjudicacao'
        verbose_name    = 'Adjudicação de Token'
        unique_together = [('sentenca', 'posicao')]
        ordering        = ['sentenca', 'posicao']

    def __str__(self):
        return f'Adjudicação sentença {self.sentenca.ordem} — pos {self.posicao} — {self.label}'