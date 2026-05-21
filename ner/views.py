import os
import time
import joblib
from django.shortcuts import render
from django.http import FileResponse, Http404

from .services.anotacao import (
    selecionar_amostra_anotacao,
    converter_doccano_para_conll,
    dividir_corpus,
    verificar_distribuicao,
    exportar_splits_conll,
)
from .services.crf import ler_conll, treinar_crf
from .services.avaliacao import (
    prever_crf,
    calcular_f1_entity_level,
    calcular_f1_por_entidade,
    calcular_f1_token_level,
    gerar_tabela_comparativa,
)
from .models import (
    ExecucaoAnotacao,
    ExecucaoDivisao,
    ExecucaoTreinamento,
    ExecucaoAvaliacao,
)

OUTPUTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs', 'ner')


# Início - 2) NER - Interface Django - Anotação
def anotacao(request):
    contexto = {}

    if request.method == 'POST':
        acao = request.POST.get('acao')
        os.makedirs(OUTPUTS_DIR, exist_ok=True)

        if acao == 'selecionar':
            import json
            caminho_jsonl = request.POST.get('caminho_jsonl')
            n_amostras    = int(request.POST.get('n_amostras', 500))
            amostra       = selecionar_amostra_anotacao(caminho_jsonl, n_amostras)

            caminho_saida = os.path.join(OUTPUTS_DIR, 'amostra_anotacao.jsonl')
            with open(caminho_saida, 'w', encoding='utf-8') as f:
                for registro in amostra:
                    f.write(json.dumps(registro, ensure_ascii=False) + '\n')

            # Salva no banco
            ExecucaoAnotacao.objects.create(
                total_sentencas_amostra=len(amostra),
            )

            contexto['amostra_gerada'] = True
            contexto['total_amostra']  = len(amostra)

        elif acao == 'importar':
            arquivo_doccano = request.FILES.get('arquivo_doccano')
            caminho_conll   = os.path.join(OUTPUTS_DIR, 'corpus_anotado.conll')
            converter_doccano_para_conll(arquivo_doccano, caminho_conll)

            # Conta sentenças do CoNLL gerado
            tokens, labels = ler_conll(caminho_conll)
            from collections import Counter
            dist = Counter(
                label.split('-')[1]
                for sentenca in labels for label in sentenca
                if label != 'O'
            )

            # Atualiza o registro de anotação mais recente
            execucao = ExecucaoAnotacao.objects.order_by('-criado_em').first()
            if execucao:
                execucao.total_sentencas_anotadas    = len(tokens)
                execucao.distribuicao_entidades_json = dict(dist)
                execucao.caminho_conll_anotado       = caminho_conll
                execucao.save()

            contexto['importacao_ok'] = True

    return render(request, 'ner/anotacao.html', contexto)
# Fim - 2) NER - Interface Django - Anotação


# Início - 2) NER - Interface Django - Divisão
def divisao(request):
    contexto = {}

    if request.method == 'POST':
        os.makedirs(OUTPUTS_DIR, exist_ok=True)
        caminho_conll = os.path.join(OUTPUTS_DIR, 'corpus_anotado.conll')
        treino, dev, teste = dividir_corpus(caminho_conll)
        verificacao        = verificar_distribuicao(treino, dev, teste)
        caminhos           = exportar_splits_conll(treino, dev, teste, OUTPUTS_DIR)

        # Salva no banco
        ExecucaoDivisao.objects.create(
            total_treino        = len(treino),
            total_dev           = len(dev),
            total_teste         = len(teste),
            verificacao_ok      = verificacao['ok'],
            ausentes_dev_json   = verificacao['ausentes_dev'],
            ausentes_teste_json = verificacao['ausentes_teste'],
            distribuicao_json   = verificacao,
            caminho_train       = caminhos['train.conll'],
            caminho_dev         = caminhos['dev.conll'],
            caminho_teste       = caminhos['test.conll'],
        )

        contexto['verificacao']  = verificacao
        contexto['total_treino'] = len(treino)
        contexto['total_dev']    = len(dev)
        contexto['total_teste']  = len(teste)
        contexto['caminhos']     = caminhos

    return render(request, 'ner/divisao.html', contexto)
# Fim - 2) NER - Interface Django - Divisão


# Início - 2) NER - Interface Django - Treinamento CRF
def treinamento(request):
    contexto = {}

    if request.method == 'POST':
        os.makedirs(OUTPUTS_DIR, exist_ok=True)
        caminho_train  = os.path.join(OUTPUTS_DIR, 'train.conll')
        caminho_modelo = os.path.join(OUTPUTS_DIR, 'crf_model.joblib')

        inicio = time.time()
        crf    = treinar_crf(caminho_train, caminho_modelo)
        tempo  = round(time.time() - inicio, 2)

        # Salva no banco
        ExecucaoTreinamento.objects.create(
            nome_modelo          = 'CRF',
            hiperparametros_json = {'c1': 0.1, 'c2': 0.1, 'max_iterations': 100},
            tempo_treinamento_seg = tempo,
            classes_json         = list(crf.classes_),
            caminho_modelo       = caminho_modelo,
        )

        contexto['treinamento_ok'] = True
        contexto['classes']        = list(crf.classes_)
        contexto['tempo']          = tempo

    return render(request, 'ner/treinamento.html', contexto)
# Fim - 2) NER - Interface Django - Treinamento CRF


# Início - 2) NER - Interface Django - Avaliação
def avaliacao(request):
    contexto = {}

    if request.method == 'POST':
        caminho_modelo = os.path.join(OUTPUTS_DIR, 'crf_model.joblib')
        caminho_teste  = os.path.join(OUTPUTS_DIR, 'test.conll')

        y_real, y_pred  = prever_crf(caminho_modelo, caminho_teste)
        f1_entity       = calcular_f1_entity_level(y_real, y_pred)
        f1_por_entidade = calcular_f1_por_entidade(y_real, y_pred)
        f1_token        = calcular_f1_token_level(y_real, y_pred)

        resultados = {'CRF': {
            'f1_micro': f1_entity['f1_micro'],
            'f1_macro': f1_token['f1_macro'],
        }}
        tabela = gerar_tabela_comparativa(resultados)

        # Salva no banco ligado ao treinamento CRF mais recente
        treinamento = ExecucaoTreinamento.objects.filter(
            nome_modelo='CRF'
        ).order_by('-criado_em').first()

        if treinamento:
            ExecucaoAvaliacao.objects.create(
                treinamento          = treinamento,
                f1_entity_micro      = f1_entity['f1_micro'],
                f1_por_entidade_json = f1_por_entidade,
                f1_token_macro       = f1_token['f1_macro'],
                f1_token_weighted    = f1_token['f1_weighted'],
                relatorio_json       = f1_entity['relatorio'],
            )

        contexto['f1_entity']       = f1_entity
        contexto['f1_por_entidade'] = f1_por_entidade
        contexto['f1_token']        = f1_token
        contexto['tabela']          = tabela.to_dict(orient='records')

    return render(request, 'ner/avaliacao.html', contexto)
# Fim - 2) NER - Interface Django - Avaliação


def baixar_arquivo(request, arquivo):
    permitidos = ['train.conll', 'dev.conll', 'test.conll',
                  'amostra_anotacao.jsonl', 'corpus_anotado.conll']
    if arquivo not in permitidos:
        raise Http404
    caminho = os.path.join(OUTPUTS_DIR, arquivo)
    if not os.path.exists(caminho):
        raise Http404
    return FileResponse(open(caminho, 'rb'), as_attachment=True, filename=arquivo)