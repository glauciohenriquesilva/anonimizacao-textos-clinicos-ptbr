import os
import time
import json
from collections import Counter
from django.shortcuts import render
from django.http import FileResponse, Http404
from analise_exploratoria.models import Experimento

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
BASE_DIR    = os.path.dirname(os.path.dirname(__file__))


def _varrer_arquivos(extensao, *subpastas):
    """Varre as subpastas de outputs em busca de arquivos com a extensão informada."""
    arquivos = []
    for pasta in subpastas:
        caminho = os.path.join(BASE_DIR, 'outputs', pasta)
        if os.path.isdir(caminho):
            for f in sorted(os.listdir(caminho)):
                if f.endswith(extensao):
                    arquivos.append(os.path.join(caminho, f))
    return arquivos


# Início - 2) NER - Interface Django - Anotação
def anotacao(request):
    contexto = {
        'arquivos_jsonl': _varrer_arquivos('.jsonl', 'preprocessamento', 'ner'),
    }

    if request.method == 'POST':
        acao        = request.POST.get('acao')
        # Usa experimento ativo da sessão
        exp_id      = request.session.get('experimento_ativo_id')
        experimento = Experimento.objects.filter(pk=exp_id).first() if exp_id else None
        os.makedirs(OUTPUTS_DIR, exist_ok=True)

        if acao == 'selecionar':
            caminho_jsonl = request.POST.get('caminho_jsonl')
            n_amostras    = int(request.POST.get('n_amostras', 500))
            amostra       = selecionar_amostra_anotacao(caminho_jsonl, n_amostras)

            caminho_saida = os.path.join(OUTPUTS_DIR, 'amostra_anotacao.jsonl')
            with open(caminho_saida, 'w', encoding='utf-8') as f:
                for registro in amostra:
                    f.write(json.dumps(registro, ensure_ascii=False) + '\n')

            ExecucaoAnotacao.objects.create(
                experimento=experimento,
                total_sentencas_amostra=len(amostra),
            )
            contexto['amostra_gerada'] = True
            contexto['total_amostra']  = len(amostra)

        elif acao == 'importar':
            arquivo_doccano = request.FILES.get('arquivo_doccano')
            caminho_conll   = os.path.join(OUTPUTS_DIR, 'corpus_anotado.conll')
            converter_doccano_para_conll(arquivo_doccano, caminho_conll)

            tokens, labels = ler_conll(caminho_conll)
            dist = Counter(
                label.split('-')[1]
                for sentenca in labels for label in sentenca
                if label != 'O'
            )

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
        arquivo = request.FILES.get('arquivo_conll')

        if not arquivo:
            contexto['erro'] = 'Selecione um arquivo CoNLL antes de executar.'
            return render(request, 'ner/divisao.html', contexto)

        # Usa experimento ativo da sessão
        exp_id      = request.session.get('experimento_ativo_id')
        experimento = Experimento.objects.filter(pk=exp_id).first() if exp_id else None

        # Salva o arquivo enviado em outputs/ner/ antes de processar
        os.makedirs(OUTPUTS_DIR, exist_ok=True)
        caminho_conll = os.path.join(OUTPUTS_DIR, 'corpus_anotado.conll')
        with open(caminho_conll, 'wb') as f:
            for chunk in arquivo.chunks():
                f.write(chunk)

        treino, dev, teste = dividir_corpus(caminho_conll)
        verificacao        = verificar_distribuicao(treino, dev, teste)
        caminhos           = exportar_splits_conll(treino, dev, teste, OUTPUTS_DIR)

        ExecucaoDivisao.objects.create(
            experimento         = experimento,
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

        # Monta lista por entidade para exibição na tabela (treino/dev/teste por linha)
        verificacao['por_entidade'] = [
            {
                'entidade': ent,
                'treino':   verificacao['treino'].get(ent, 0),
                'dev':      verificacao['dev'].get(ent, 0),
                'teste':    verificacao['teste'].get(ent, 0),
            }
            for ent in sorted(verificacao['treino'])
        ]

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
        arquivo = request.FILES.get('arquivo_conll')

        if not arquivo:
            contexto['erro'] = 'Selecione o arquivo train.conll antes de executar.'
            return render(request, 'ner/treinamento.html', contexto)

        # Usa experimento ativo da sessão
        exp_id      = request.session.get('experimento_ativo_id')
        experimento = Experimento.objects.filter(pk=exp_id).first() if exp_id else None

        # Salva o arquivo de treino enviado em outputs/ner/
        os.makedirs(OUTPUTS_DIR, exist_ok=True)
        caminho_train  = os.path.join(OUTPUTS_DIR, 'train.conll')
        caminho_modelo = os.path.join(OUTPUTS_DIR, 'crf_model.joblib')

        with open(caminho_train, 'wb') as f:
            for chunk in arquivo.chunks():
                f.write(chunk)

        inicio = time.time()
        crf    = treinar_crf(caminho_train, caminho_modelo)
        tempo  = round(time.time() - inicio, 2)

        ExecucaoTreinamento.objects.create(
            experimento           = experimento,
            nome_modelo           = 'CRF',
            hiperparametros_json  = {'c1': 0.1, 'c2': 0.1, 'max_iterations': 300},
            tempo_treinamento_seg = tempo,
            classes_json          = list(crf.classes_),
            caminho_modelo        = caminho_modelo,
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
        import numpy as np

        arquivo_teste  = request.FILES.get('arquivo_conll')
        arquivo_modelo = request.FILES.get('arquivo_modelo')

        if not arquivo_teste or not arquivo_modelo:
            contexto['erro'] = 'Selecione o modelo (.joblib) e o arquivo de teste (.conll).'
            return render(request, 'ner/avaliacao.html', contexto)

        # Salva os arquivos enviados em outputs/ner/
        os.makedirs(OUTPUTS_DIR, exist_ok=True)
        caminho_teste  = os.path.join(OUTPUTS_DIR, 'test_eval.conll')
        caminho_modelo = os.path.join(OUTPUTS_DIR, 'crf_model_eval.joblib')

        with open(caminho_teste, 'wb') as f:
            for chunk in arquivo_teste.chunks():
                f.write(chunk)

        with open(caminho_modelo, 'wb') as f:
            for chunk in arquivo_modelo.chunks():
                f.write(chunk)

        y_real, y_pred  = prever_crf(caminho_modelo, caminho_teste)
        f1_entity       = calcular_f1_entity_level(y_real, y_pred)
        f1_por_entidade = calcular_f1_por_entidade(y_real, y_pred)
        f1_token        = calcular_f1_token_level(y_real, y_pred)

        resultados = {'CRF': {
            'f1_micro':  f1_entity['f1_micro'],
            'f1_macro':  f1_token['f1_macro'],
            'precision': f1_entity.get('precision', '-'),
            'recall':    f1_entity.get('recall', '-'),
        }}
        tabela = gerar_tabela_comparativa(resultados)

        # Converte valores numpy para tipos nativos Python — necessário para JSONField
        def converter_numpy(obj):
            # Percorre recursivamente dicts e listas convertendo int64/float64
            if isinstance(obj, dict):
                return {k: converter_numpy(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [converter_numpy(i) for i in obj]
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            return obj

        f1_por_entidade_limpo   = converter_numpy(f1_por_entidade)
        relatorio_limpo         = converter_numpy(f1_entity['relatorio'])
        f1_entity_micro_limpo   = float(f1_entity['f1_micro'])
        f1_token_macro_limpo    = float(f1_token['f1_macro'])
        f1_token_weighted_limpo = float(f1_token['f1_weighted'])

        treinamento_obj = ExecucaoTreinamento.objects.filter(
            nome_modelo='CRF'
        ).order_by('-criado_em').first()

        if treinamento_obj:
            ExecucaoAvaliacao.objects.update_or_create(
                treinamento = treinamento_obj,
                defaults={
                    'f1_entity_micro':      f1_entity_micro_limpo,
                    'f1_por_entidade_json': f1_por_entidade_limpo,
                    'f1_token_macro':       f1_token_macro_limpo,
                    'f1_token_weighted':    f1_token_weighted_limpo,
                    'relatorio_json':       relatorio_limpo,
                }
            )

        contexto['f1_entity']       = f1_entity
        contexto['f1_por_entidade'] = f1_por_entidade_limpo
        contexto['f1_token']        = f1_token
        contexto['tabela']          = converter_numpy(tabela.to_dict(orient='records'))

    return render(request, 'ner/avaliacao.html', contexto)
# Fim - 2) NER - Interface Django - Avaliação

def baixar_arquivo(request, arquivo):
    permitidos = ['train.conll', 'dev.conll', 'test.conll',
                  'amostra_anotacao.jsonl', 'corpus_anotado.conll',
                  'crf_model.joblib']
    if arquivo not in permitidos:
        raise Http404
    caminho = os.path.join(OUTPUTS_DIR, arquivo)
    if not os.path.exists(caminho):
        raise Http404
    return FileResponse(open(caminho, 'rb'), as_attachment=True, filename=arquivo)