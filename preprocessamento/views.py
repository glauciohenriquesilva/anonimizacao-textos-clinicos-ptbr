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
        arquivo_prescricoes  = request.FILES.get('arquivo_prescricoes')
        arquivo_pareceres    = request.FILES.get('arquivo_pareceres')
        amostra              = request.POST.get('amostra')
        n_total_raw          = request.POST.get('n_total_anotacao', '').strip()
        amostra              = int(amostra) if amostra else None
        n_total_anotacao     = int(n_total_raw) if n_total_raw.isdigit() else None

        os.makedirs(OUTPUTS_DIR, exist_ok=True)
        caminho_conll = os.path.join(OUTPUTS_DIR, 'corpus.conll')
        caminho_jsonl = os.path.join(OUTPUTS_DIR, 'corpus.jsonl')

        resultado = executar_preprocessamento(
            arquivo_prescricoes=arquivo_prescricoes,
            arquivo_pareceres=arquivo_pareceres,
            caminho_conll=caminho_conll,
            caminho_jsonl=caminho_jsonl,
            amostra=amostra,
            n_total_anotacao=n_total_anotacao,
        )

        ExecucaoPreprocessamento.objects.create(
            amostra_por_tipo  = amostra,
            total_documentos  = resultado['total_documentos'],
            total_sentencas   = resultado['total_sentencas'],
            total_prescricoes = resultado['total_prescricoes'],
            total_pareceres   = resultado['total_pareceres'],
            caminho_conll     = caminho_conll,
            caminho_jsonl     = caminho_jsonl,
            caminho_anotacao  = resultado['caminho_anotacao'],
            selecao_phi       = resultado['selecao_phi'],
        )

        contexto['resultado'] = resultado

    return render(request, 'preprocessamento/index.html', contexto)


def baixar_arquivo(request, formato):
    nomes = {
        'conll':    'corpus.conll',
        'jsonl':    'corpus.jsonl',
        'anotacao': 'corpus_anotacao.jsonl',
    }
    if formato not in nomes:
        raise Http404
    caminho = os.path.join(OUTPUTS_DIR, nomes[formato])
    if not os.path.exists(caminho):
        raise Http404
    return FileResponse(open(caminho, 'rb'), as_attachment=True, filename=nomes[formato])
# Fim - 1) Pré-processamento - Interface Django