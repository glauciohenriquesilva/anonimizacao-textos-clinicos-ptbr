from django.db import models
from analise_exploratoria.models import Experimento
from anotador.models import SessaoAnotacao


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


class GeracaoCorpusSurrogate(models.Model):
    """
    Registro de uma rodada do gerador de surrogates.

    Por que este modelo existe
    ==========================
    O gerador é determinístico: mesma semente, mesmo catálogo, mesmo código, mesmo
    resultado. Isso só vale como reprodutibilidade se as três coisas estiverem anotadas em
    algum lugar. Sem registro, daqui a seis meses existirão dez arquivos JSONL numa pasta
    e ninguém saberá qual semente gerou qual, nem se o catálogo de nomes era o mesmo, nem
    se o código já tinha a correção da partícula de sobrenome.

    O que fica guardado aqui é só metadado: contagens, sementes, hashes e caminhos. Nenhum
    valor de PHI, nenhum nome real, nenhum surrogate. Os corpora gerados ficam em disco, e
    o mapa de PHI, que é o material sensível, nunca é referenciado por conteúdo, apenas
    pelo hash do arquivo, que serve para conferir que a mesma entrada foi usada sem
    guardar nada dela.

    A relação com a sessão de anotação é o que amarra o corpus gerado ao gold standard de
    onde ele saiu. Se a anotação for corrigida depois, como aconteceu com as sequências
    BIO inválidas, dá para saber quais gerações precisam ser refeitas.
    """

    sessao = models.ForeignKey(
        SessaoAnotacao, on_delete=models.PROTECT, related_name='geracoes_surrogate',
        help_text='Sessão de anotação que serviu de gold standard para esta geração.',
    )
    experimento = models.ForeignKey(
        Experimento, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='geracoes_surrogate',
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    anotador_base_id = models.IntegerField(
        null=True, blank=True,
        help_text='Anotador usado como base onde não houve adjudicação. Com um anotador '
                  'só é redundante, mas passa a importar quando o segundo entrar.',
    )

    total_versoes = models.IntegerField(
        default=0,
        help_text='Quantas versões verossímeis foram geradas nesta rodada.',
    )
    com_contraprova = models.BooleanField(
        default=True,
        help_text='Se os braços placeholder e celebridade foram gerados junto.',
    )

    caminho_saida = models.CharField(
        max_length=500, blank=True, default='',
        help_text='Pasta onde os arquivos foram gravados. Caminho local, não é publicado.',
    )
    hash_mapa_phi = models.CharField(
        max_length=64, blank=True, default='',
        help_text='SHA-256 do arquivo *_phi.jsonl usado. Vazio quando a geração correu '
                  'sem mapa, caso em que datas e demais valores de regex ficaram como '
                  'placeholder no corpus.',
    )

    commit_git = models.CharField(
        max_length=40, blank=True, default='',
        help_text='Commit do repositório no momento da geração. É o que identifica a '
                  'versão do código do gerador e dos catálogos.',
    )
    repositorio_sujo = models.BooleanField(
        default=False,
        help_text='Verdadeiro quando havia alteração não commitada no momento da geração. '
                  'Nesse caso o commit sozinho não reproduz o resultado.',
    )

    relatorio_leitura_json = models.JSONField(
        null=True, blank=True,
        help_text='Contagens da leitura do gold: sentenças lidas, labels por origem, '
                  'sentenças sem paciente e sem PHI.',
    )
    obs = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'tb_anonclin_geracao_surrogate'
        verbose_name = 'Geração de Corpus com Surrogates'
        verbose_name_plural = 'Gerações de Corpus com Surrogates'
        ordering = ['-criado_em']

    @property
    def reproduzivel(self):
        """
        Diz se esta geração pode ser refeita a partir do que ficou registrado.

        Precisa das três coisas juntas: o commit do código, a árvore limpa naquele
        momento, e o mapa de PHI identificado por hash quando ele foi usado. Faltando
        qualquer uma, o resultado pode não bater na próxima execução, e é melhor saber
        disso antes de citar os números na dissertação.
        """
        if not self.commit_git or self.repositorio_sujo:
            return False
        precisa_de_mapa = bool(
            self.relatorio_leitura_json
            and self.relatorio_leitura_json.get('mapa_phi_carregado')
        )
        if precisa_de_mapa and not self.hash_mapa_phi:
            return False
        return True

    def __str__(self):
        return (f'Geração {self.criado_em:%d/%m/%Y %H:%M} '
                f'sessão {self.sessao_id}, {self.total_versoes} versões')


class VersaoCorpusSurrogate(models.Model):
    """
    Uma versão do corpus produzida numa geração, ou seja, um arquivo JSONL.

    Cada linha desta tabela corresponde a um arquivo em disco. O par (semente, modo) é o
    que identifica a versão do ponto de vista do método; o hash do arquivo é o que prova
    que o arquivo em disco continua sendo aquele que produziu os números reportados.

    Os contadores repetidos do relatório do gerador estão aqui de propósito, em colunas e
    não dentro de um JSON: são eles que entram na tabela de resultados e nas conferências
    de sanidade, e coluna é o que permite ordenar, filtrar e somar sem abrir cada registro.
    """

    MODO_VEROSSIMIL = 'verossimil'
    MODO_PLACEHOLDER = 'placeholder'
    MODO_CELEBRIDADE = 'celebridade'
    MODOS = [
        (MODO_VEROSSIMIL, 'Verossímil (braço B)'),
        (MODO_PLACEHOLDER, 'Placeholder (braço C)'),
        (MODO_CELEBRIDADE, 'Celebridade (braço C)'),
    ]

    geracao = models.ForeignKey(
        GeracaoCorpusSurrogate, on_delete=models.CASCADE, related_name='versoes'
    )
    rotulo = models.CharField(
        max_length=30,
        help_text='Como a versão aparece no nome do arquivo: v01, v02, placeholder, '
                  'celebridade.',
    )
    seed = models.IntegerField(
        help_text='Semente do gerador. Junto com o commit e o catálogo, é o que reproduz '
                  'exatamente este arquivo.',
    )
    modo = models.CharField(max_length=20, choices=MODOS, default=MODO_VEROSSIMIL)

    arquivo = models.CharField(
        max_length=255,
        help_text='Nome do arquivo dentro da pasta de saída da geração.',
    )
    hash_arquivo = models.CharField(
        max_length=64, blank=True, default='',
        help_text='SHA-256 do JSONL gerado. Confere se o arquivo mudou depois de gerado.',
    )
    bytes_arquivo = models.BigIntegerField(null=True, blank=True)

    sentencas = models.IntegerField(default=0)
    entidades_distintas = models.IntegerField(
        default=0,
        help_text='Valores distintos que o gerador precisou inventar nesta versão.',
    )
    pacientes_com_shift = models.IntegerField(
        default=0,
        help_text='Pacientes que receberam deslocamento de datas. Um deslocamento fixo '
                  'por paciente é o que preserva os intervalos entre eventos.',
    )
    colisoes_evitadas = models.IntegerField(
        default=0,
        help_text='Vezes em que o sorteio caiu no próprio valor original e foi refeito.',
    )
    colisoes_nao_resolvidas = models.IntegerField(
        default=0,
        help_text='Valores que continuaram iguais ao original mesmo após as tentativas. '
                  'Diferente de zero significa catálogo pequeno demais para este corpus.',
    )
    placeholders_restantes = models.IntegerField(
        default=0,
        help_text='Marcadores __TIPO__ que sobraram no texto. Esperado quando a geração '
                  'correu sem mapa de PHI; suspeito quando o mapa foi informado.',
    )
    problemas_alinhamento = models.IntegerField(
        default=0,
        help_text='Sentenças em que tokens e labels não ficaram alinhados após a '
                  'substituição. O mesmo número em todas as versões aponta para o gold '
                  'standard, não para o gerador.',
    )

    tipos_nao_suportados_json = models.JSONField(
        null=True, blank=True,
        help_text='Tipos de entidade sem tratamento no gerador. Eles permaneceram no '
                  'corpus com o valor real, então a lista precisa estar vazia antes de '
                  'qualquer publicação.',
    )
    avisos_json = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = 'tb_anonclin_versao_surrogate'
        verbose_name = 'Versão de Corpus com Surrogates'
        verbose_name_plural = 'Versões de Corpus com Surrogates'
        unique_together = [('geracao', 'rotulo')]
        ordering = ['geracao', 'rotulo']

    @property
    def limpa(self):
        """
        Diz se a versão está pronta para entrar num experimento.

        Verdadeiro quando nada ficou pendente: sem colisão irresolvida, sem placeholder
        sobrando, sem desalinhamento e sem tipo de entidade fora do tratamento. Qualquer
        um deles significa que o corpus ainda carrega valor real ou estrutura quebrada.
        """
        return not (
            self.colisoes_nao_resolvidas
            or self.placeholders_restantes
            or self.problemas_alinhamento
            or (self.tipos_nao_suportados_json or [])
        )

    def __str__(self):
        return f'{self.rotulo} ({self.modo}), seed {self.seed}, {self.sentencas} sentenças'
