from anotador.models import SessaoAnotacao, Sentenca

for s in SessaoAnotacao.objects.all().order_by('id'):
    n = Sentenca.objects.filter(sessao_id=s.id).count()
    print(f'id={s.id} nome="{s.nome}" experimento_id={s.experimento_id} sentencas={n}')
