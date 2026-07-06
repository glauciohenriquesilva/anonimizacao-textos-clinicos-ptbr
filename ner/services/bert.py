import torch
from transformers import (
    AutoTokenizer,
    AutoModelForTokenClassification,
    TrainingArguments,
    Trainer,
    DataCollatorForTokenClassification,
)
from datasets import Dataset
from seqeval.metrics import classification_report

# Início - 2) NER - 2.3) Treinamento dos Modelos - 2.3.2 a 2.3.5) Fine-tuning BERT (Colab GPU)
# Nota: tokenizar_e_alinhar_bert foi internalizada aqui para que bert.py seja
# importável sem dependência do Django (permite uso direto em notebooks Colab/local).

def tokenizar_e_alinhar_bert(sentenca, labels_bio, tokenizer, max_length=512, stride=64):
    # Tokeniza uma sentença com o tokenizer do HuggingFace e alinha as labels BIO
    # com os subtokens gerados pelo WordPiece.
    # sentenca   : lista de tokens word-level
    # labels_bio : lista de labels BIO alinhadas (None em modo inferência)
    # tokenizer  : instância de AutoTokenizer já carregada
    encoding = tokenizer(
        sentenca,
        is_split_into_words=True,
        return_offsets_mapping=False,
        truncation=True,
        max_length=max_length,
        stride=stride,
        return_overflowing_tokens=True,
        padding='max_length',
        return_tensors=None,
    )
    todas_labels = []
    for chunk_idx in range(len(encoding['input_ids'])):
        word_ids = encoding.word_ids(batch_index=chunk_idx)
        labels_alinhadas = []
        palavra_anterior = None
        for word_id in word_ids:
            if word_id is None:
                labels_alinhadas.append(-100)
            elif word_id != palavra_anterior:
                labels_alinhadas.append(labels_bio[word_id] if labels_bio is not None else None)
                palavra_anterior = word_id
            else:
                labels_alinhadas.append(-100)
        todas_labels.append(labels_alinhadas)
    return encoding, todas_labels
# MODEL_ID — trocar conforme o modelo a treinar:
#   BioBERTpt-clin  : 'pucpr/biobertpt-clin'
#   BERTimbau-leNER : 'pierreguillou/bert-base-cased-pt-lenerbr'
#   mmBERT          : 'jhu-clsp/mmBERT'
#   ModernBERT      : 'answerdotai/ModernBERT-base'

def carregar_conll(caminho):
    # Lê um arquivo CoNLL e retorna lista de dicts {tokens, labels}
    exemplos = []
    tokens_atual, labels_atual = [], []
    with open(caminho, encoding='utf-8') as f:
        for linha in f:
            linha = linha.rstrip('\n')
            if linha == '':
                if tokens_atual:
                    exemplos.append({'tokens': tokens_atual, 'labels': labels_atual})
                    tokens_atual, labels_atual = [], []
            else:
                partes = linha.split('\t')
                tokens_atual.append(partes[0])
                labels_atual.append(partes[1])
        if tokens_atual:
            exemplos.append({'tokens': tokens_atual, 'labels': labels_atual})
    return exemplos


def construir_mapa_labels(treino, dev, teste):
    # Coleta todas as labels únicas e cria mapeamento label → id e id → label
    todas = set()
    for split in [treino, dev, teste]:
        for ex in split:
            todas.update(ex['labels'])
    labels_ordenadas = sorted(todas)
    label2id = {l: i for i, l in enumerate(labels_ordenadas)}
    id2label = {i: l for l, i in label2id.items()}
    return label2id, id2label


def tokenizar_dataset(exemplos, tokenizer, label2id, max_length=512, stride=64):
    # Tokeniza cada exemplo e alinha as labels BIO com os subtokens gerados pelo WordPiece
    resultado = {'input_ids': [], 'attention_mask': [], 'labels': []}
    for ex in exemplos:
        labels_ids = [label2id[l] for l in ex['labels']]
        encoding, labels_alinhadas = tokenizar_e_alinhar_bert(
            ex['tokens'], labels_ids, tokenizer,
            max_length=max_length, stride=stride,
        )
        for i in range(len(encoding['input_ids'])):
            resultado['input_ids'].append(encoding['input_ids'][i])
            resultado['attention_mask'].append(encoding['attention_mask'][i])
            resultado['labels'].append(labels_alinhadas[i])
    return resultado


def treinar_bert(model_id, caminho_train, caminho_dev, caminho_saida, epochs=5, batch_size=16):
    # Carrega tokenizer e modelo, tokeniza os splits, treina e salva o modelo.

    tokenizer = AutoTokenizer.from_pretrained(model_id)

    treino = carregar_conll(caminho_train)
    dev    = carregar_conll(caminho_dev)

    # Constrói mapa de labels a partir dos dois splits disponíveis no treino
    label2id, id2label = construir_mapa_labels(treino, dev, dev)

    # Tokeniza os splits de treino e dev
    ds_treino = Dataset.from_dict(tokenizar_dataset(treino, tokenizer, label2id))
    ds_dev    = Dataset.from_dict(tokenizar_dataset(dev,   tokenizer, label2id))

    # Carrega o modelo com cabeça de classificação de tokens (NER)
    modelo = AutoModelForTokenClassification.from_pretrained(
        model_id,
        num_labels=len(label2id),
        id2label=id2label,
        label2id=label2id,
        ignore_mismatched_sizes=True,  # necessário para modelos sem cabeça NER pré-treinada
    )

    # Configuração de treinamento
    args = TrainingArguments(
        output_dir=caminho_saida,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        learning_rate=2e-5,             # taxa de aprendizado padrão para fine-tuning BERT
        weight_decay=0.01,              # regularização L2
        eval_strategy='epoch',          # avalia ao final de cada época
        save_strategy='best',           # salva apenas o melhor checkpoint
        load_best_model_at_end=True,    # carrega o melhor modelo ao final do treino
        metric_for_best_model='eval_loss',
        fp16=torch.cuda.is_available(), # half-precision se GPU disponível
        logging_steps=50,
    )

    data_collator = DataCollatorForTokenClassification(tokenizer)

    # 'tokenizer' foi renomeado para 'processing_class' no transformers >= 4.46
    import transformers as _tf
    _major, _minor = [int(x) for x in _tf.__version__.split('.')[:2]]
    _tokenizer_kwarg = 'processing_class' if (_major, _minor) >= (4, 46) else 'tokenizer'

    trainer = Trainer(
        model=modelo,
        args=args,
        train_dataset=ds_treino,
        eval_dataset=ds_dev,
        data_collator=data_collator,
        **{_tokenizer_kwarg: tokenizer},
    )

    trainer.train()
    trainer.save_model(caminho_saida)
    tokenizer.save_pretrained(caminho_saida)  # garante que o tokenizer é salvo junto

    return trainer, tokenizer, label2id, id2label
# Fim - 2) NER - 2.3) Treinamento dos Modelos - 2.3.2 a 2.3.5) Fine-tuning BERT (Colab GPU)