# -*- coding: utf-8 -*-
"""
Reaproveita um benchmark já rodado quando só alguns braços mudaram.

Compara, arquivo por arquivo, a pasta antiga e a nova pelo SHA-256. Copia o JSON de
resultados para a pasta nova removendo apenas os braços cujo corpus mudou. O benchmark,
ao ser rodado de novo com --saida apontando para essa cópia, retoma e treina só esses.

Só reaproveita quando grupos_paciente.json e corpus_real.jsonl são idênticos nas duas
pastas, porque as partições e o teste real dependem deles.

Uso:
    python scripts/reaproveitar_benchmark.py --antiga outputs/surrogates_exp004_r3 \\
        --nova outputs/surrogates_exp004_r4 --json benchmark_crf_duplo.json
"""
import argparse
import hashlib
import json
import os
import sys


def sha(caminho):
    h = hashlib.sha256()
    with open(caminho, 'rb') as f:
        for bloco in iter(lambda: f.read(1 << 20), b''):
            h.update(bloco)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--antiga', required=True)
    p.add_argument('--nova', required=True)
    p.add_argument('--json', default='benchmark_crf_duplo.json')
    a = p.parse_args()

    for base in ('grupos_paciente.json', 'corpus_real.jsonl'):
        if sha(os.path.join(a.antiga, base)) != sha(os.path.join(a.nova, base)):
            sys.exit(f'{base} difere entre as pastas. Rode o benchmark inteiro.')

    mudaram = []
    for nome in sorted(os.listdir(a.nova)):
        if not (nome.startswith('corpus_') and nome.endswith('.jsonl')):
            continue
        antigo = os.path.join(a.antiga, nome)
        braco = nome[len('corpus_'):-len('.jsonl')]
        if not os.path.exists(antigo) or sha(antigo) != sha(os.path.join(a.nova, nome)):
            mudaram.append(braco)
        print(f"  {braco:<12} {'MUDOU' if braco in mudaram else 'igual'}")

    with open(os.path.join(a.antiga, a.json), encoding='utf-8') as f:
        resultados = json.load(f)
    resultados.pop('resumo', None)
    for particao in resultados['particoes'].values():
        for campo in ('f1', 'por_entidade', 'f1_proprio', 'por_entidade_proprio'):
            for braco in mudaram:
                particao.get(campo, {}).pop(braco, None)
    with open(os.path.join(a.nova, a.json), 'w', encoding='utf-8') as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)
    print(f'\nBracos a treinar de novo: {mudaram or "nenhum"}')


if __name__ == '__main__':
    main()
