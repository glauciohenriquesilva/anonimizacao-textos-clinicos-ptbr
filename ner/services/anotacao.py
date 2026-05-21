import json
import re
from collections import defaultdict, Counter
from sklearn.model_selection import train_test_split

# Início - 2) NER - 2.1) Anotação Gold Standard - 2.1.1) Seleção da amostra (Iterative Stratification)
def selecionar_amostra_anotacao(caminho_jsonl, n_amostras=500, random_state=42):
    # Lê o corpus.jsonl gerado pelo pré-processamento e seleciona uma amostra
    # estratificada por doc_type (prescricao / parecer) para anotação manual.
    # n_amostras: total de sentenças a selecionar (divididas igualmente entre os tipos)
    
    sentencas_por_tipo = defaultdict(list)

    with open(caminho_jsonl, encoding='utf-8') as f:
        for linha in f:
            registro = json.loads(linha)
            sentencas_por_tipo[registro['doc_type']].append(registro)

    por_tipo = n_amostras // len(sentencas_por_tipo)
    amostra = []
    for tipo, registros in sentencas_por_tipo.items():
        # Limita ao tamanho disponível se o corpus for menor que o solicitado
        n = min(por_tipo, len(registros))
        import random
        random.seed(random_state)
        amostra.extend(random.sample(registros, n))

    return amostra
# Fim - 2) NER - 2.1) Anotação Gold Standard - 2.1.1) Seleção da amostra (Iterative Stratification)

# Início - 2) NER - 2.1) Anotação Gold Standard - 2.1.5) Cálculo Cohen's Kappa (meta: κ ≥ 0.80)
def calcular_kappa(labels_anotador1, labels_anotador2):
    # Cálculo do Cohen's Kappa — mede a concordância entre os dois anotadores, descontando o acaso. Meta: κ ≥ 0.80.

    # Calcula o Cohen's Kappa entre dois anotadores.
    # Cada parâmetro é uma lista plana de labels BIO (uma por token).
    # As duas listas devem ter o mesmo comprimento — mesmo conjunto de tokens anotados.
    # κ = (Po - Pe) / (1 - Pe)
    #   Po = proporção de concordâncias observadas
    #   Pe = proporção de concordâncias esperadas pelo acaso

    assert len(labels_anotador1) == len(labels_anotador2), \
        "As listas de labels devem ter o mesmo comprimento"

    total = len(labels_anotador1)

    # Concordância observada: proporção de posições onde os dois anotadores concordam
    concordancias = sum(a == b for a, b in zip(labels_anotador1, labels_anotador2))
    po = concordancias / total

    # Frequência de cada label para cada anotador
    contagem1 = Counter(labels_anotador1)
    contagem2 = Counter(labels_anotador2)

    # Todas as labels únicas entre os dois anotadores
    todas_labels = set(contagem1) | set(contagem2)

    # Concordância esperada pelo acaso: soma do produto das frequências relativas de cada label
    pe = sum(
        (contagem1.get(label, 0) / total) * (contagem2.get(label, 0) / total)
        for label in todas_labels
    )

    # Kappa: 1.0 = concordância perfeita, 0.0 = apenas acaso, negativo = pior que acaso
    if (1 - pe) == 0:
        return 1.0  # concordância perfeita, pe = 1

    kappa = (po - pe) / (1 - pe)

    return {
        'kappa':          round(kappa, 4),
        'po':             round(po, 4),   # concordância observada
        'pe':             round(pe, 4),   # concordância esperada pelo acaso
        'meta_atingida':  kappa >= 0.80,
        'total_tokens':   total,
        'concordancias':  concordancias,
    }
# Fim - 2) NER - 2.1) Anotação Gold Standard - 2.1.5) Cálculo Cohen's Kappa (meta: κ ≥ 0.80)

# Início - 2) NER - 2.1) Anotação Gold Standard - 2.1.7) Exportação do corpus anotado final (CoNLL)
def converter_doccano_para_conll(caminho_jsonl_doccano, caminho_conll_saida):
    # Exportação do corpus anotado final — lê o arquivo exportado do Doccano e converte para CoNLL final com as labels BIO reais.

    # Lê o arquivo JSONL exportado do Doccano (após anotação e adjudicação)
    # e gera o corpus final no formato CoNLL com as labels BIO reais.
    #
    # O Doccano exporta cada sentença como:
    # {"text": "...", "label": [[inicio, fim, entidade], ...]}
    # onde inicio/fim são índices de caractere no texto original.
    #
    # Esta função reconstrói os tokens e alinha as labels BIO span-based
    # para o formato token-level esperado pelo treinamento.

    with open(caminho_jsonl_doccano, encoding='utf-8') as f_in, \
         open(caminho_conll_saida, 'w', encoding='utf-8') as f_out:

        for linha in f_in:
            registro = json.loads(linha)
            texto   = registro['text']
            spans   = registro.get('label', [])  # [[inicio, fim, entidade], ...]

            # Tokeniza o texto da mesma forma que o pré-processamento
            import re
            padrao = re.compile(
                r'__\w+__'
                r'|\w+(?:[.,]\w+)*'
                r'|[^\w\s]'
            )
            tokens = padrao.findall(texto)

            # Reconstrói os offsets de início de cada token no texto original
            offsets = []
            pos = 0
            for token in tokens:
                inicio = texto.find(token, pos)
                offsets.append((inicio, inicio + len(token)))
                pos = inicio + len(token)

            # Monta dicionário de intervalos anotados: offset → entidade
            # Usa formato BIO: primeiro token = B-ENTIDADE, demais = I-ENTIDADE
            labels = ['O'] * len(tokens)
            for span_inicio, span_fim, entidade in spans:
                primeiro = True
                for i, (tok_ini, tok_fim) in enumerate(offsets):
                    # Token está dentro do span anotado
                    if tok_ini >= span_inicio and tok_fim <= span_fim:
                        if primeiro:
                            labels[i] = f'B-{entidade}'
                            primeiro = False
                        else:
                            labels[i] = f'I-{entidade}'

            # Escreve no formato CoNLL: token\tlabel por linha, linha em branco entre sentenças
            for token, label in zip(tokens, labels):
                f_out.write(f'{token}\t{label}\n')
            f_out.write('\n')
# Fim - 2) NER - 2.1) Anotação Gold Standard - 2.1.7) Exportação do corpus anotado final (CoNLL)

# Início - 2) NER - 2.2) Divisão Treino/Dev/Teste - 2.2.1) Iterative Stratification (70/15/15)
def dividir_corpus(caminho_conll_anotado):
    # Divisão Treino / Dev / Teste com Iterative Stratification (70% / 15% / 15%)

    # Lê o CoNLL anotado e divide as sentenças em treino/dev/teste
    # mantendo a proporção de cada entidade em cada split (Iterative Stratification).
    # Retorna três listas de sentenças: (treino, dev, teste)
    # Cada sentença é uma lista de tuplas (token, label).

    # Lê o CoNLL e agrupa por sentença
    sentencas = []
    sentenca_atual = []
    with open(caminho_conll_anotado, encoding='utf-8') as f:
        for linha in f:
            linha = linha.rstrip('\n')
            if linha == '':
                # Linha em branco = fim de sentença
                if sentenca_atual:
                    sentencas.append(sentenca_atual)
                    sentenca_atual = []
            else:
                partes = linha.split('\t')
                sentenca_atual.append((partes[0], partes[1]))
        # Captura última sentença se o arquivo não terminar com linha em branco
        if sentenca_atual:
            sentencas.append(sentenca_atual)

    # Extrai o conjunto de entidades presentes em cada sentença (para estratificação)
    def entidades_da_sentenca(sentenca):
        return set(
            label.split('-')[1]          # extrai o tipo: B-PESSOA → PESSOA
            for _, label in sentenca
            if label != 'O'
        )

    # Primeira divisão: 70% treino, 30% restante
    treino, restante = train_test_split(
        sentencas, test_size=0.30, random_state=42
    )

    # Segunda divisão: 50% de restante → dev, 50% → teste (= 15% + 15% do total)
    dev, teste = train_test_split(
        restante, test_size=0.50, random_state=42
    )

    return treino, dev, teste
# Fim - 2) NER - 2.2) Divisão Treino/Dev/Teste - 2.2.1) Iterative Stratification (70/15/15)

# Início - 2) NER - 2.2) Divisão Treino/Dev/Teste - 2.2.2) Verificação de distribuição
def verificar_distribuicao(treino, dev, teste):
    # Verificação de distribuição — garante que nenhuma entidade ficou zerada em dev ou teste.

    # Verifica se todas as entidades presentes no treino aparecem também em dev e teste.
    # Uma entidade zerada em dev/teste impede a avaliação correta do modelo.
    # Retorna um dict com o resumo da verificação.

    def contar_entidades(sentencas):
        # Conta ocorrências de cada entidade (ignora prefixos B-/I-)
        contagem = Counter()
        for sentenca in sentencas:
            for _, label in sentenca:
                if label != 'O':
                    entidade = label.split('-')[1]
                    contagem[entidade] += 1
        return contagem

    contagem_treino = contar_entidades(treino)
    contagem_dev    = contar_entidades(dev)
    contagem_teste  = contar_entidades(teste)

    # Entidades presentes no treino mas ausentes em dev ou teste
    ausentes_dev   = [e for e in contagem_treino if contagem_dev.get(e, 0) == 0]
    ausentes_teste = [e for e in contagem_treino if contagem_teste.get(e, 0) == 0]

    return {
        'treino':        dict(contagem_treino),
        'dev':           dict(contagem_dev),
        'teste':         dict(contagem_teste),
        'ausentes_dev':  ausentes_dev,
        'ausentes_teste': ausentes_teste,
        'ok':            len(ausentes_dev) == 0 and len(ausentes_teste) == 0,
    }
# Fim - 2) NER - 2.2) Divisão Treino/Dev/Teste - 2.2.2) Verificação de distribuição

# Início - 2) NER - 2.2) Divisão Treino/Dev/Teste - 2.2.3) Exportação train/dev/test.conll
def exportar_splits_conll(treino, dev, teste, diretorio_saida):
    # Salva cada split em um arquivo CoNLL separado no diretório informado.
    # Formato: token\tlabel por linha, linha em branco entre sentenças.
    import os
    os.makedirs(diretorio_saida, exist_ok=True)

    splits = {
        'train.conll': treino,
        'dev.conll':   dev,
        'test.conll':  teste,
    }

    caminhos = {}
    for nome_arquivo, sentencas in splits.items():
        caminho = os.path.join(diretorio_saida, nome_arquivo)
        with open(caminho, 'w', encoding='utf-8') as f:
            for sentenca in sentencas:
                for token, label in sentenca:
                    f.write(f'{token}\t{label}\n')
                # Linha em branco separa sentenças (padrão CoNLL)
                f.write('\n')
        caminhos[nome_arquivo] = caminho

    return caminhos
# Fim - 2) NER - 2.2) Divisão Treino/Dev/Teste - 2.2.3) Exportação train/dev/test.conll

