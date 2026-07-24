from anotador.models import Sentenca

titulos = {'sr', 'sra', 'dr', 'dra'}
sessao_id = 5  # ajuste se necessario

sentencas = Sentenca.objects.filter(sessao_id=sessao_id)
suspeitas = []

for s in sentencas:
    tokens = s.tokens  # lista de strings (JSONField)
    anotacoes = {a.posicao: a.label for a in s.anotacoes.all()}
    for i, tok in enumerate(tokens):
        if tok.lower() in titulos:
            label_titulo = anotacoes.get(i, 'O')
            label_prox = anotacoes.get(i + 1, 'O') if i + 1 < len(tokens) else 'O'
            if label_prox.endswith('PESSOA') and not label_titulo.endswith('PESSOA'):
                nome_prox = tokens[i + 1] if i + 1 < len(tokens) else None
                suspeitas.append((s.id, s.ordem, tok, nome_prox))

print(f'Total de casos suspeitos: {len(suspeitas)}')
for sent_id, ordem, titulo, nome in suspeitas:
    print(f'Sentenca id={sent_id} ordem={ordem}: "{titulo}" nao marcado, mas "{nome}" esta como PESSOA')
