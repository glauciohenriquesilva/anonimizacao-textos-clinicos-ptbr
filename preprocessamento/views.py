import os
from django.shortcuts import render
from django.http import FileResponse, Http404
from .services.preprocessamento import executar_preprocessamento
from .models import ExecucaoPreprocessamento

OUTPUTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs', 'preprocessamento')

# Início - 1) Pré-processamento - Interface Django
def index(request):
    contexto = {}

    if request.method == 'POST':
        arquivo_prescricoes = request.FILES.get('arquivo_prescricoes')
        arquivo_pareceres   = request.FILES.get('arquivo_pareceres')
        amostra = request.POST.get('amostra')
        amostra = int(amostra) if amostra else None

        os.makedirs(OUTPUTS_DIR, exist_ok=True)
        caminho_conll = os.path.join(OUTPUTS_DIR, 'corpus.conll')
        caminho_jsonl = os.path.join(OUTPUTS_DIR, 'corpus.jsonl')

        resultado = executar_preprocessamento(
            arquivo_prescricoes=arquivo_prescricoes,
            arquivo_pareceres=arquivo_pareceres,
            caminho_conll=caminho_conll,
            caminho_jsonl=caminho_jsonl,
            amostra=amostra,
        )

        # Salva a execução no banco para rastreabilidade
        execucao = ExecucaoPreprocessamento.objects.create(
            amostra_por_tipo=amostra,
            total_documentos=resultado['total_documentos'],
            total_sentencas=resultado['total_sentencas'],
            total_prescricoes=resultado['total_documentos'] // 2,
            total_pareceres=resultado['total_documentos'] // 2,
            caminho_conll=caminho_conll,
            caminho_jsonl=caminho_jsonl,
        )

        contexto['resultado']   = resultado
        contexto['execucao_id'] = execucao.id

    return render(request, 'preprocessamento/index.html', contexto)


def baixar_arquivo(request, formato):
    nomes = {'conll': 'corpus.conll', 'jsonl': 'corpus.jsonl'}
    if formato not in nomes:
        raise Http404
    caminho = os.path.join(OUTPUTS_DIR, nomes[formato])
    if not os.path.exists(caminho):
        raise Http404
    return FileResponse(open(caminho, 'rb'), as_attachment=True, filename=nomes[formato])
# Fim - 1) Pré-processamento - Interface Django