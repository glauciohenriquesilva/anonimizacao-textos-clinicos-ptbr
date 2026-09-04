# Generated for Fase 2, extensão de corpus com surrogates
#
# Acrescenta a Sentenca o vínculo com o paciente (pseudonimizado) e a posição da
# sentença dentro do documento de origem.
#
# Antes desta migração o corpus perdia o vínculo com a pessoa: `doc_id` é o índice
# posicional do DataFrame no pré-processamento, não identifica o paciente. Sem isso, a
# consistência de surrogate por paciente e o rastreio longitudinal são irrealizáveis.
#
# Ambos os campos são nulos: sessões de anotação carregadas antes desta migração
# continuam válidas e a interface de anotação não os utiliza.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('anotador', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='sentenca',
            name='hash_paciente',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='SHA-256 com salt do cd_paciente. Chave de consistência do '
                          'gerador de surrogates. Nunca o identificador em claro.',
                max_length=64,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='sentenca',
            name='sentenca_idx',
            field=models.IntegerField(
                blank=True,
                help_text='Posição da sentença dentro do documento de origem. Liga esta '
                          'sentença à linha correspondente do arquivo *_phi.jsonl.',
                null=True,
            ),
        ),
    ]
