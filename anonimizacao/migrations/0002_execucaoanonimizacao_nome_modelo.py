from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('anonimizacao', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='execucaoanonimizacao',
            name='nome_modelo',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
    ]
