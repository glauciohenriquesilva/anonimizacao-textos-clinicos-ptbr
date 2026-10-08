# -*- coding: utf-8 -*-
"""
Fase 6, segunda parte: benchmark dos três braços com modelos da família BERT.

Faz para um modelo BERT o mesmo que benchmark_bracos_crf.py faz para o CRF: treina em
cada braço, em cada partição por paciente, e avalia duas vezes, no texto real e no
próprio corpus. As partições e a estatística vêm de comum_benchmark.py, as mesmas do CRF.

FEITO PARA RODAR FORA DA MÁQUINA DA SESA

Não usa Django nem o banco. Precisa só da pasta do experimento (os arquivos corpus_*.jsonl
e grupos_paciente.json) e deste script com comum_benchmark.py ao lado. Nada mais vai para
o servidor.

Os modelos treinados NÃO são guardados: cada um é treinado numa pasta temporária, avaliado
e apagado. O que fica é o arquivo de resultados, só com números.

HIPERPARÂMETROS

Os mesmos de ner/services/bert.py (Exp 002): 5 épocas, lote 16, taxa de aprendizado 2e-5,
weight decay 0,01, acumulação de gradiente 4, fp16 se houver GPU. O melhor checkpoint é
escolhido pela perda na partição de validação do próprio braço.

Diferente do CRF, o BERT tem sorteios internos. A semente do treino é a da partição, então
cada combinação é reproduzível, e a variação entre partições já inclui esse ruído.

MODELOS E HIPERPARÂMETROS DO EXP 002 (notebooks/04_bert_finetuning.ipynb, conferido em
08/10/2026). Cada modelo tem os seus, e é preciso passá-los na linha de comando:

    pucpr/biobertpt-clin                            --lote 16 --epocas 5 --lr 2e-5
    pierreguillou/bert-base-cased-pt-lenerbr        --lote 16 --epocas 5 --lr 2e-5
    pierreguillou/ner-bert-large-cased-pt-lenerbr   --lote 8  --epocas 5 --lr 1e-5
    jhu-clsp/mmBERT-base                            --lote 32 --epocas 8 --lr 1e-5
    answerdotai/ModernBERT-base                     --lote 32 --epocas 8 --lr 1e-5

Em todos, acumulação de gradiente 4 (padrão do script). No Exp 002 o ModernBERT usava
flash attention, que exige GPU Ampere ou mais nova. A Titan V do IFES é anterior: ele roda
sem, mais devagar. Se faltar memória, reduza --lote e aumente --acumulacao na mesma
proporção, para manter o lote efetivo, e anote a mudança no handoff.

Uso, teste rápido com o corpus fictício:
    python scripts/benchmark_bracos_bert.py --dir outputs/corpus_ficticio \\
        --modelo pucpr/biobertpt-clin --particoes 1 --versoes 1 --epocas 1

Uso real, um modelo por vez:
    python scripts/benchmark_bracos_bert.py --dir <pasta do experimento> \\
        --modelo pucpr/biobertpt-clin --particoes 5
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum_benchmark import (  # noqa: E402
    contar_entidades, dividir_por_paciente, ler_corpus, metricas_seqeval, resumir_benchmark,
)

import torch  # noqa: E402
from transformers import (  # noqa: E402
    AutoModelForTokenClassification,
    AutoTokenizer,
    DataCollatorForTokenClassification,
    Trainer,
    TrainingArguments,
)

ENTIDADES = ('PESSOA', 'ENDERECO', 'INSTITUICAO', 'DATA', 'DOCUMENTO')
LABELS = ['O'] + [f'{p}-{e}' for e in ENTIDADES for p in ('B', 'I')]
LABEL2ID = {l: i for i, l in enumerate(LABELS)}
ID2LABEL = {i: l for l, i in LABEL2ID.items()}
MAX_TOKENS = 512


class Conjunto(torch.utils.data.Dataset):
    """Sentenças já tokenizadas, com as labels alinhadas ao primeiro subtoken."""

    def __init__(self, tokens, labels, tokenizer):
        self.itens = []
        for palavras, rotulos in zip(tokens, labels):
            enc = tokenizer(palavras, is_split_into_words=True, truncation=True,
                            max_length=MAX_TOKENS)
            alinhadas, anterior = [], None
            for indice in enc.word_ids():
                if indice is None or indice == anterior:
                    alinhadas.append(-100)
                else:
                    # Label desconhecida (não deveria existir) vira O, e não derruba o treino
                    alinhadas.append(LABEL2ID.get(rotulos[indice], 0))
                anterior = indice
            enc['labels'] = alinhadas
            self.itens.append(dict(enc))

    def __len__(self):
        return len(self.itens)

    def __getitem__(self, i):
        return self.itens[i]


def prever(modelo, tokenizer, tokens, lote=32):
    """
    Devolve uma sequência de labels por sentença, alinhada às palavras.

    A label de cada palavra é a do seu primeiro subtoken. Sentença maior que 512 subtokens
    é cortada, e as palavras que sobram recebem O. Isso é raro no corpus e é contado.
    """
    modelo.eval()
    dispositivo = next(modelo.parameters()).device
    saida, cortadas = [], 0
    for inicio in range(0, len(tokens), lote):
        bloco = tokens[inicio:inicio + lote]
        enc = tokenizer(bloco, is_split_into_words=True, truncation=True,
                        max_length=MAX_TOKENS, padding=True, return_tensors='pt')
        with torch.no_grad():
            logits = modelo(**{k: v.to(dispositivo) for k, v in enc.items()}).logits
        predito = logits.argmax(-1).cpu().tolist()
        for b, palavras in enumerate(bloco):
            rotulos = ['O'] * len(palavras)
            anterior = None
            vistos = 0
            for posicao, indice in enumerate(enc.word_ids(batch_index=b)):
                if indice is not None and indice != anterior:
                    rotulos[indice] = ID2LABEL[predito[b][posicao]]
                    vistos += 1
                anterior = indice
            cortadas += vistos < len(palavras)
            saida.append(rotulos)
    return saida, cortadas


def avaliar(y_real, y_previsto):
    """Devolve (F1 micro, F1 por entidade, métricas completas com precisão e cobertura)."""
    return metricas_seqeval(y_real, y_previsto)


def treinar(args, semente, tok_treino, lab_treino, tok_val, lab_val, tokenizer):
    pasta = tempfile.mkdtemp(prefix='bert_bracos_')
    try:
        modelo = AutoModelForTokenClassification.from_pretrained(
            args.modelo, num_labels=len(LABELS), id2label=ID2LABEL, label2id=LABEL2ID,
            ignore_mismatched_sizes=True)
        argumentos = TrainingArguments(
            output_dir=pasta, num_train_epochs=args.epocas,
            per_device_train_batch_size=args.lote, per_device_eval_batch_size=args.lote,
            learning_rate=args.lr, weight_decay=0.01,
            gradient_accumulation_steps=args.acumulacao,
            eval_strategy='epoch', save_strategy='epoch', save_total_limit=1,
            load_best_model_at_end=True, metric_for_best_model='eval_loss',
            fp16=torch.cuda.is_available(), seed=semente, report_to=[],
            logging_steps=50, disable_tqdm=not args.progresso,
        )
        trainer = Trainer(
            model=modelo, args=argumentos,
            train_dataset=Conjunto(tok_treino, lab_treino, tokenizer),
            eval_dataset=Conjunto(tok_val, lab_val, tokenizer),
            data_collator=DataCollatorForTokenClassification(tokenizer),
        )
        trainer.train()
        return trainer.model
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


def main():
    p = argparse.ArgumentParser(description='Benchmark dos tres bracos com um modelo BERT.')
    p.add_argument('--dir', required=True)
    p.add_argument('--modelo', required=True, help='Identificador do HuggingFace ou pasta local.')
    p.add_argument('--particoes', type=int, default=5)
    p.add_argument('--versoes', type=int, default=None)
    p.add_argument('--epocas', type=int, default=5)
    p.add_argument('--lote', type=int, default=16)
    p.add_argument('--lr', type=float, default=2e-5)
    p.add_argument('--acumulacao', type=int, default=4)
    p.add_argument('--delta', type=float, default=None)
    p.add_argument('--saida', default=None)
    p.add_argument('--progresso', action='store_true', help='Mostra a barra de progresso.')
    args = p.parse_args()

    nome = args.modelo.rstrip('/').split('/')[-1]
    caminho_saida = args.saida or os.path.join(args.dir, f'benchmark_bert_{nome}.json')
    print(f'Modelo: {args.modelo}')
    print(f"GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'nenhuma, rodando em CPU'}")

    with open(os.path.join(args.dir, 'grupos_paciente.json'), encoding='utf-8') as f:
        grupos = json.load(f)
    versoes = sorted(n[len('corpus_'):-len('.jsonl')] for n in os.listdir(args.dir)
                     if n.startswith('corpus_v') and n.endswith('.jsonl'))
    if args.versoes:
        versoes = versoes[:args.versoes]
    bracos = ['real'] + versoes + ['placeholder', 'celebridade']
    corpora = {b: ler_corpus(os.path.join(args.dir, f'corpus_{b}.jsonl')) for b in bracos}
    for b, (tokens, _) in corpora.items():
        if len(tokens) != len(grupos):
            sys.exit(f'corpus_{b}.jsonl tem {len(tokens)} sentencas e grupos tem {len(grupos)}.')

    resultados = {'modelo': args.modelo, 'hiperparametros': {
        'epocas': args.epocas, 'lote': args.lote, 'lr': args.lr,
        'acumulacao': args.acumulacao}, 'particoes': {}}
    if os.path.exists(caminho_saida):
        with open(caminho_saida, encoding='utf-8') as f:
            resultados = json.load(f)
        if resultados.get('modelo') != args.modelo:
            sys.exit(f'{caminho_saida} e de outro modelo. Use outro --saida.')
        print(f'  retomando de {caminho_saida}')

    tokenizer = AutoTokenizer.from_pretrained(args.modelo)
    tok_real, lab_real = corpora['real']

    for semente in range(1, args.particoes + 1):
        treino, validacao, teste = dividir_por_paciente(grupos, semente)
        part = resultados['particoes'].setdefault(str(semente), {
            'f1': {}, 'por_entidade': {}, 'f1_proprio': {}, 'por_entidade_proprio': {},
            'metricas': {}, 'metricas_proprio': {}, 'sentencas_cortadas': {}})
        part['sentencas'] = {'treino': len(treino), 'validacao': len(validacao),
                             'teste': len(teste)}
        part['entidades_teste'] = contar_entidades(lab_real, teste)
        print(f'\nPARTICAO {semente}: treino {len(treino)}, validacao {len(validacao)}, '
              f'teste {len(teste)}')

        for braco in bracos:
            if braco in part['f1_proprio']:
                print(f"  {braco:<12} no real {part['f1'][braco]:.4f} | no proprio "
                      f"{part['f1_proprio'][braco]:.4f}  (ja calculado)")
                continue
            inicio = time.time()
            tok, lab = corpora[braco]
            modelo = treinar(args, semente, [tok[i] for i in treino], [lab[i] for i in treino],
                             [tok[i] for i in validacao], [lab[i] for i in validacao], tokenizer)
            prev_real, cort_real = prever(modelo, tokenizer, [tok_real[i] for i in teste])
            prev_prop, cort_prop = prever(modelo, tokenizer, [tok[i] for i in teste])
            (part['f1'][braco], part['por_entidade'][braco],
             part['metricas'][braco]) = avaliar([lab_real[i] for i in teste], prev_real)
            (part['f1_proprio'][braco], part['por_entidade_proprio'][braco],
             part['metricas_proprio'][braco]) = avaliar([lab[i] for i in teste], prev_prop)
            part['sentencas_cortadas'][braco] = cort_real + cort_prop
            del modelo
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            print(f"  {braco:<12} no real {part['f1'][braco]:.4f} | no proprio "
                  f"{part['f1_proprio'][braco]:.4f}  ({time.time() - inicio:.0f}s)")
            with open(caminho_saida, 'w', encoding='utf-8') as f:
                json.dump(resultados, f, ensure_ascii=False, indent=2)

    resultados['resumo'] = resumir_benchmark(resultados, versoes, args.particoes, args.delta)
    with open(caminho_saida, 'w', encoding='utf-8') as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)
    print('\nRESUMO\n------')
    print(json.dumps(resultados['resumo'], ensure_ascii=False, indent=2))
    if args.delta is None:
        print('\nNenhuma margem informada: o resultado acima e descritivo, nao um teste.')
    print(f'Resultados gravados em {caminho_saida}')


if __name__ == '__main__':
    main()
