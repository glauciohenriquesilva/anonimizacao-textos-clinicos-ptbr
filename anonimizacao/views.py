import os
import json
import time
from collections import Counter
from django.shortcuts import render
from django.http import FileResponse, Http404

from analise_exploratoria.models import Experimento
from .models import ExecucaoAnonimizacao
from .services.anonimizacao import (
    gerar_tabela_tild,
    exportar_tabela_tild_csv,
    gerar_graficos_tild,
)

BASE_DIR    = os.path.dirname(os.path.dirname(__file__))
OUTPUTS_DIR = os.path.join(BASE_DIR, 'outputs', 'anonimizacao')
NER_DIR     = os.path.join(BASE_DIR, 'outputs', 'ner')


def _varrer_arquivos(extensao, *subpastas):
    """Varre outputs/<subpasta>/ em busca de arquivos com a extensão informada."""
    arquivos = []
    for pasta in subpastas:
        caminho = os.path.join(BASE_DIR, 'outputs', pasta)
        if os.path.isdir(caminho):
            for f in sorted(os.listdir(caminho)):
                if f.endswith(extensao):
                    arquivos.append(os.path.join(caminho, f))
    return arquivos


# Início - 3) Anonimização - Interface Django - Executar
def index(request):
    contexto = {
        'experimentos':   Experimento.objects.order_by('-criado_em'),
        'modelos_crf':    _varrer_arquivos('.joblib', 'ner'),
        'arquivos_conll': _varrer_arquivos('.conll', 'ner'),
        'arquivos_jsonl': _varrer_arquivos('.jsonl', 'preprocessamento', 'ner'),
    }

    if request.method != 'POST':
        return render(request, 'anonimizacao/index.html', contexto)

    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    modo = request.POST.get('modo', 'crf')  # 'crf' ou 'importar'

    # Usa experimento ativo da sessão
    exp_id      = request.session.get('experimento_ativo_id')
    experimento = Experimento.objects.filter(pk=exp_id).first() if exp_id else None

    # ------------------------------------------------------------------
    # MODO 1 — CRF local: pipeline completo de anonimização
    # ------------------------------------------------------------------
    if modo == 'crf':
        try:
            import joblib
            from preprocessamento.services.preprocessamento import extrair_features_sentenca
            from anonimizacao.services.anonymizer import HybridAnonymizer

            # Modelo CRF: upload ou arquivo auto-detectado em outputs/ner/
            arquivo_modelo = request.FILES.get('arquivo_modelo')
            if arquivo_modelo:
                caminho_modelo = os.path.join(OUTPUTS_DIR, 'modelo_upload.joblib')
                with open(caminho_modelo, 'wb') as f:
                    for chunk in arquivo_modelo.chunks():
                        f.write(chunk)
            else:
                caminho_modelo = request.POST.get('caminho_modelo_crf', '').strip()
                if not caminho_modelo:
                    caminho_modelo = os.path.join(NER_DIR, 'crf_model.joblib')

            if not os.path.exists(caminho_modelo):
                raise FileNotFoundError(f'Modelo CRF não encontrado: {caminho_modelo}')

            crf = joblib.load(caminho_modelo)

            def predictor(tokens):
                features = extrair_features_sentenca(tokens)
                return crf.predict([features])[0]

            anon = HybridAnonymizer(ner_predictor=predictor)

            # Test CoNLL para métricas L: upload ou auto-detectado
            arquivo_teste = request.FILES.get('arquivo_teste')
            if arquivo_teste:
                caminho_teste = os.path.join(OUTPUTS_DIR, 'test_anon.conll')
                with open(caminho_teste, 'wb') as f:
                    for chunk in arquivo_teste.chunks():
                        f.write(chunk)
            else:
                caminho_teste = request.POST.get('caminho_conll', '').strip()
                if not caminho_teste:
                    caminho_teste = os.path.join(NER_DIR, 'test.conll')

            if not os.path.exists(caminho_teste):
                raise FileNotFoundError(f'Arquivo test.conll não encontrado: {caminho_teste}')

            metricas_l = anon.calcular_metricas_l(caminho_teste)

            # Corpus a anonimizar (opcional — JSONL do pré-processamento)
            total_docs, total_spans = 0, 0
            distribuicao = {}
            caminho_saida = None

            arquivo_corpus = request.FILES.get('arquivo_corpus')
            if arquivo_corpus:
                textos = []
                for linha in arquivo_corpus:
                    linha_str = linha.decode('utf-8').strip()
                    if linha_str:
                        try:
                            obj = json.loads(linha_str)
                            textos.append(obj.get('texto', ''))
                        except json.JSONDecodeError:
                            pass

                t0 = time.time()
                resultados_anon = anon.anonymize_batch(textos)
                contexto['tempo_anon'] = round(time.time() - t0, 2)

                total_docs  = len(resultados_anon)
                total_spans = sum(r['n_phi_total'] for r in resultados_anon)
                todos_tipos = [s['tipo'] for r in resultados_anon for s in r['spans_ner']]
                distribuicao = dict(Counter(todos_tipos))

                caminho_saida = os.path.join(OUTPUTS_DIR, 'corpus_anonimizado.jsonl')
                with open(caminho_saida, 'w', encoding='utf-8') as f:
                    for r in resultados_anon:
                        f.write(json.dumps({
                            'texto_original':    r['texto_original'],
                            'texto_anonimizado': r['texto_anonimizado'],
                            'n_phi_regex':       r['n_phi_regex'],
                            'n_phi_ner':         r['n_phi_ner'],
                        }, ensure_ascii=False) + '\n')

            execucao = ExecucaoAnonimizacao.objects.create(
                experimento=experimento,
                nome_modelo='CRF',
                total_documentos_anonimizados=total_docs,
                total_spans_substituidos=total_spans,
                distribuicao_marcadores_json=distribuicao or None,
                coverage=metricas_l['coverage'],
                precision_anon=metricas_l['precision_anon'],
                caminho_corpus_anonimizado=caminho_saida,
            )

            contexto['execucao']   = execucao
            contexto['metricas_l'] = metricas_l
            contexto['total_docs'] = total_docs
            contexto['ok']         = True
            contexto['modo_ok']    = 'crf'

        except Exception as exc:
            contexto['erro'] = str(exc)

    # ------------------------------------------------------------------
    # MODO 2 — Importar métricas do Colab (BERT e outros modelos GPU)
    # Registra ExecucaoAnonimizacao com os valores já calculados no Colab.
    # ------------------------------------------------------------------
    elif modo == 'importar':
        try:
            nome_modelo     = request.POST.get('nome_modelo', '').strip()
            coverage_str    = request.POST.get('coverage', '').strip()
            precision_str   = request.POST.get('precision_anon', '').strip()
            delta_f1_str    = request.POST.get('delta_f1', '').strip()
            f1_orig_str     = request.POST.get('f1_downstream_original', '').strip()
            f1_anon_str     = request.POST.get('f1_downstream_anonimizado', '').strip()
            total_docs_str  = request.POST.get('total_documentos', '0').strip()
            obs             = request.POST.get('obs', '').strip()

            def _f(s):
                return float(s.replace(',', '.')) if s else None

            execucao = ExecucaoAnonimizacao.objects.create(
                experimento=experimento,
                nome_modelo=nome_modelo,
                total_documentos_anonimizados=int(total_docs_str) if total_docs_str else 0,
                total_spans_substituidos=0,
                coverage=_f(coverage_str),
                precision_anon=_f(precision_str),
                delta_f1=_f(delta_f1_str),
                f1_downstream_original=_f(f1_orig_str),
                f1_downstream_anonimizado=_f(f1_anon_str),
                obs=obs or None,
            )

            contexto['execucao']  = execucao
            contexto['ok']        = True
            contexto['modo_ok']   = 'importar'
            contexto['nome_modelo'] = nome_modelo

        except Exception as exc:
            contexto['erro'] = str(exc)

    return render(request, 'anonimizacao/index.html', contexto)
# Fim - 3) Anonimização - Interface Django - Executar


# Início - 3) Anonimização - Interface Django - Resultados TILD
def resultados(request):
    contexto = {}

    if request.method == 'POST':
        os.makedirs(OUTPUTS_DIR, exist_ok=True)

        # Coleta métricas das execuções de anonimização do experimento ativo (ou todas)
        exp_id = request.session.get('experimento_ativo_id')
        qs = ExecucaoAnonimizacao.objects.filter(experimento_id=exp_id) if exp_id else ExecucaoAnonimizacao.objects.all()
        execucoes = qs.order_by('-criado_em')

        resultados_modelos = {}
        for e in execucoes:
            if e.experimento and e.experimento.treinamentos.exists():
                treinamento = e.experimento.treinamentos.order_by('-criado_em').first()
                avaliacao   = getattr(treinamento, 'avaliacao', None)
                resultados_modelos[treinamento.nome_modelo] = {
                    'f1_ner':          avaliacao.f1_entity_micro if avaliacao else None,
                    'coverage':        e.coverage,
                    'precision_anon':  e.precision_anon,
                    'levenshtein':     e.levenshtein_ratio,
                    'f1_original':     e.f1_downstream_original,
                    'f1_anonimizado':  e.f1_downstream_anonimizado,
                    'delta_f1':        e.delta_f1,
                }

        if resultados_modelos:
            df_tild = gerar_tabela_tild(resultados_modelos)

            caminho_csv = os.path.join(OUTPUTS_DIR, 'tabela_tild.csv')
            exportar_tabela_tild_csv(df_tild, caminho_csv)
            gerar_graficos_tild(df_tild, OUTPUTS_DIR)

            # Renomeia colunas com espaços/caracteres especiais para evitar
            # TemplateSyntaxError no Django (dot notation não suporta espaços)
            df_template = df_tild.rename(columns={
                'F1 NER':        'F1_NER',
                'F1 Original':   'F1_Original',
                'F1 Anonimizado': 'F1_Anonimizado',
                'ΔF1':           'DeltaF1',
            })
            contexto['tabela']    = df_template.to_dict(orient='records')
            contexto['tem_dados'] = True

    return render(request, 'anonimizacao/resultados.html', contexto)
# Fim - 3) Anonimização - Interface Django - Resultados TILD


def baixar_arquivo(request, arquivo):
    permitidos = ['tabela_tild.csv', 'grafico_f1_ner.png', 'grafico_delta_f1.png',
                  'corpus_anonimizado.jsonl']
    if arquivo not in permitidos:
        raise Http404
    caminho = os.path.join(OUTPUTS_DIR, arquivo)
    if not os.path.exists(caminho):
        raise Http404
    return FileResponse(open(caminho, 'rb'), as_attachment=True, filename=arquivo)
