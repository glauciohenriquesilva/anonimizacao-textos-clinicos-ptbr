# -*- coding: utf-8 -*-
"""
Gera uma pasta de experimento inteiramente inventada, para testar os benchmarks.

Mesmo formato da pasta real (corpus_real.jsonl, corpus_v01.jsonl..., corpus_placeholder.jsonl,
corpus_celebridade.jsonl e grupos_paciente.json), mas as sentenças saem de modelos de
frase escritos aqui, e todos os nomes, datas e lugares são de listas fixas deste arquivo.
Nenhum dado de paciente é lido. Por isso a pasta pode ir para qualquer máquina, inclusive
a de casa, e serve para validar o ambiente, o fluxo e o tempo de treino.

Os números de F1 que saírem desse corpus não significam nada. É só um teste de encanamento.

Uso:
    python scripts/gerar_corpus_ficticio.py --saida outputs/corpus_ficticio
"""
import argparse
import json
import os
import random

MODELOS = [
    'Paciente {PESSOA} admitido em {DATA} no {INSTITUICAO} .',
    'Retorno agendado para {DATA} com o Dr {PESSOA} .',
    '{PESSOA} reside em {ENDERECO} , acompanhado pela filha .',
    'Encaminhado ao {INSTITUICAO} para avaliacao cardiologica em {DATA} .',
    'Familiar {PESSOA} informa que o paciente mora em {ENDERECO} .',
    'Paciente estavel , sem queixas , dieta oral aceita .',
    'Solicitado exame de imagem no {INSTITUICAO} .',
    'Alta hospitalar em {DATA} , orientado retorno ao {INSTITUICAO} .',
    'Avaliado por {PESSOA} , mantida conduta .',
    'Documento {DOCUMENTO} apresentado na admissao .',
]
REAL = {
    'PESSOA': ['Antonio Pereira', 'Maria Lucia', 'Jose Carlos', 'Ana Paula Souza', 'Joao'],
    'INSTITUICAO': ['HOSPITAL CENTRAL', 'HCA', 'UPA NORTE', 'HMVV'],
    'ENDERECO': ['Rua das Flores', 'Bairro Centro', 'Vila Nova', 'Rua A , 12'],
    'DATA': ['12 / 03', '05 / 11', '2024-03-12', 'marco de 2024'],
    'DOCUMENTO': ['CNS 123', 'RG 4567'],
}
FICTICIO = {
    'PESSOA': ['Carlos Rocha', 'Helena Dias', 'Paulo', 'Rita Moura', 'Bruno Lima Alves'],
    'INSTITUICAO': ['HOSPITAL SUL', 'HEAB', 'UPA LESTE', 'HMSR'],
    'ENDERECO': ['Rua dos Ipes', 'Bairro Jardim', 'Vila Bela', 'Rua B , 45'],
    'DATA': ['22 / 03', '15 / 11', '2024-04-02', 'abril de 2024'],
    'DOCUMENTO': ['CNS 987', 'RG 6543'],
}
CELEBRIDADES = ['Machado de Assis', 'Cecilia Meireles', 'Pele', 'Elis Regina']


def montar(modelo, escolher):
    tokens, labels = [], []
    for parte in modelo.split():
        if parte.startswith('{') and parte.endswith('}'):
            tipo = parte[1:-1]
            valor = escolher(tipo).split()
            tokens += valor
            labels += [f'B-{tipo}'] + [f'I-{tipo}'] * (len(valor) - 1)
        else:
            tokens.append(parte)
            labels.append('O')
    return tokens, labels


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--saida', default='outputs/corpus_ficticio')
    p.add_argument('--sentencas', type=int, default=600)
    p.add_argument('--pacientes', type=int, default=150)
    p.add_argument('--versoes', type=int, default=2)
    a = p.parse_args()
    os.makedirs(a.saida, exist_ok=True)

    rng = random.Random(0)
    plano = [(rng.choice(MODELOS), rng.randrange(a.pacientes), rng.random())
             for _ in range(a.sentencas)]

    def gravar(nome, escolher):
        with open(os.path.join(a.saida, f'corpus_{nome}.jsonl'), 'w', encoding='utf-8') as f:
            for i, (modelo, paciente, sorteio) in enumerate(plano):
                r = random.Random(f'{nome}|{paciente}|{sorteio}')
                tokens, labels = montar(modelo, lambda t: escolher(t, r))
                f.write(json.dumps({'doc_id': paciente, 'doc_type': 'parecer',
                                    'tokens': tokens, 'labels': labels},
                                   ensure_ascii=False) + '\n')

    gravar('real', lambda t, r: r.choice(REAL[t]))
    for v in range(1, a.versoes + 1):
        gravar(f'v{v:02d}', lambda t, r: r.choice(FICTICIO[t]))
    contador = {}

    def marcador(t, r):
        contador[t] = contador.get(t, 0) + 1
        return f'{t}_{contador[t]}'
    gravar('placeholder', marcador)
    gravar('celebridade', lambda t, r: r.choice(CELEBRIDADES) if t == 'PESSOA'
           else r.choice(FICTICIO[t]))
    with open(os.path.join(a.saida, 'grupos_paciente.json'), 'w', encoding='utf-8') as f:
        json.dump([paciente for _, paciente, _ in plano], f)
    print(f'Corpus ficticio em {a.saida}: {a.sentencas} sentencas, {a.pacientes} pacientes, '
          f'{a.versoes} versoes. Nenhum dado real.')


if __name__ == '__main__':
    main()
