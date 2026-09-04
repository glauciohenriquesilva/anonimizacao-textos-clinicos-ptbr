# -*- coding: utf-8 -*-
"""
Cria as tabelas de registro das gerações de corpus com surrogates.

Escrita à mão, como a 0002 do app anotador, para que o conteúdo fique legível e revisável
antes de rodar. Nenhuma coluna aqui guarda texto clínico, valor de PHI ou surrogate: são
contagens, sementes, hashes e caminhos locais.

A dependência do app anotador existe porque a geração aponta para a sessão de anotação
que serviu de gold standard.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('anonimizacao', '0002_execucaoanonimizacao_nome_modelo'),
        ('anotador', '0002_sentenca_hash_paciente_sentenca_idx'),
        ('analise_exploratoria', '0007_alter_execucaoanalise_id_alter_experimento_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='GeracaoCorpusSurrogate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('anotador_base_id', models.IntegerField(
                    blank=True, null=True,
                    help_text='Anotador usado como base onde não houve adjudicação. Com '
                              'um anotador só é redundante, mas passa a importar quando '
                              'o segundo entrar.')),
                ('total_versoes', models.IntegerField(
                    default=0,
                    help_text='Quantas versões verossímeis foram geradas nesta rodada.')),
                ('com_contraprova', models.BooleanField(
                    default=True,
                    help_text='Se os braços placeholder e celebridade foram gerados '
                              'junto.')),
                ('caminho_saida', models.CharField(
                    blank=True, default='', max_length=500,
                    help_text='Pasta onde os arquivos foram gravados. Caminho local, não '
                              'é publicado.')),
                ('hash_mapa_phi', models.CharField(
                    blank=True, default='', max_length=64,
                    help_text='SHA-256 do arquivo *_phi.jsonl usado. Vazio quando a '
                              'geração correu sem mapa, caso em que datas e demais '
                              'valores de regex ficaram como placeholder no corpus.')),
                ('commit_git', models.CharField(
                    blank=True, default='', max_length=40,
                    help_text='Commit do repositório no momento da geração. É o que '
                              'identifica a versão do código do gerador e dos '
                              'catálogos.')),
                ('repositorio_sujo', models.BooleanField(
                    default=False,
                    help_text='Verdadeiro quando havia alteração não commitada no '
                              'momento da geração. Nesse caso o commit sozinho não '
                              'reproduz o resultado.')),
                ('relatorio_leitura_json', models.JSONField(
                    blank=True, null=True,
                    help_text='Contagens da leitura do gold: sentenças lidas, labels por '
                              'origem, sentenças sem paciente e sem PHI.')),
                ('obs', models.TextField(blank=True, null=True)),
                ('experimento', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='geracoes_surrogate',
                    to='analise_exploratoria.experimento')),
                ('sessao', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='geracoes_surrogate',
                    to='anotador.sessaoanotacao',
                    help_text='Sessão de anotação que serviu de gold standard para esta '
                              'geração.')),
            ],
            options={
                'verbose_name': 'Geração de Corpus com Surrogates',
                'verbose_name_plural': 'Gerações de Corpus com Surrogates',
                'db_table': 'tb_anonclin_geracao_surrogate',
                'ordering': ['-criado_em'],
            },
        ),
        migrations.CreateModel(
            name='VersaoCorpusSurrogate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('rotulo', models.CharField(
                    max_length=30,
                    help_text='Como a versão aparece no nome do arquivo: v01, v02, '
                              'placeholder, celebridade.')),
                ('seed', models.IntegerField(
                    help_text='Semente do gerador. Junto com o commit e o catálogo, é o '
                              'que reproduz exatamente este arquivo.')),
                ('modo', models.CharField(
                    choices=[('verossimil', 'Verossímil (braço B)'),
                             ('placeholder', 'Placeholder (braço C)'),
                             ('celebridade', 'Celebridade (braço C)')],
                    default='verossimil', max_length=20)),
                ('arquivo', models.CharField(
                    max_length=255,
                    help_text='Nome do arquivo dentro da pasta de saída da geração.')),
                ('hash_arquivo', models.CharField(
                    blank=True, default='', max_length=64,
                    help_text='SHA-256 do JSONL gerado. Confere se o arquivo mudou '
                              'depois de gerado.')),
                ('bytes_arquivo', models.BigIntegerField(blank=True, null=True)),
                ('sentencas', models.IntegerField(default=0)),
                ('entidades_distintas', models.IntegerField(
                    default=0,
                    help_text='Valores distintos que o gerador precisou inventar nesta '
                              'versão.')),
                ('pacientes_com_shift', models.IntegerField(
                    default=0,
                    help_text='Pacientes que receberam deslocamento de datas. Um '
                              'deslocamento fixo por paciente é o que preserva os '
                              'intervalos entre eventos.')),
                ('colisoes_evitadas', models.IntegerField(
                    default=0,
                    help_text='Vezes em que o sorteio caiu no próprio valor original e '
                              'foi refeito.')),
                ('colisoes_nao_resolvidas', models.IntegerField(
                    default=0,
                    help_text='Valores que continuaram iguais ao original mesmo após as '
                              'tentativas. Diferente de zero significa catálogo pequeno '
                              'demais para este corpus.')),
                ('placeholders_restantes', models.IntegerField(
                    default=0,
                    help_text='Marcadores __TIPO__ que sobraram no texto. Esperado '
                              'quando a geração correu sem mapa de PHI; suspeito quando '
                              'o mapa foi informado.')),
                ('problemas_alinhamento', models.IntegerField(
                    default=0,
                    help_text='Sentenças em que tokens e labels não ficaram alinhados '
                              'após a substituição. O mesmo número em todas as versões '
                              'aponta para o gold standard, não para o gerador.')),
                ('tipos_nao_suportados_json', models.JSONField(
                    blank=True, null=True,
                    help_text='Tipos de entidade sem tratamento no gerador. Eles '
                              'permaneceram no corpus com o valor real, então a lista '
                              'precisa estar vazia antes de qualquer publicação.')),
                ('avisos_json', models.JSONField(blank=True, null=True)),
                ('geracao', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='versoes',
                    to='anonimizacao.geracaocorpussurrogate')),
            ],
            options={
                'verbose_name': 'Versão de Corpus com Surrogates',
                'verbose_name_plural': 'Versões de Corpus com Surrogates',
                'db_table': 'tb_anonclin_versao_surrogate',
                'ordering': ['geracao', 'rotulo'],
                'unique_together': {('geracao', 'rotulo')},
            },
        ),
    ]
