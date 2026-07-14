import os
import re
from django.shortcuts import render
from django.http import FileResponse, Http404
from .services.preprocessamento import executar_preprocessamento
from .models import ExecucaoPreprocessamento
from analise_exploratoria.models import Experimento


def _slug_experimento(experimento):
    """Converte o nome do experimento em slug seguro para nome de arquivo.
    Ex: 'Experimento 002' → 'Experimento_002'
    """
    if not experimento:
        return ''
    slug = re.sub(r'[^\w\s-]', '', experimento.nome)   # remove caracteres especiais
    slug = re.sub(r'[\s]+', '_', slug.strip())          # espaços → underscore
    return slug + '_'

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
        # Usa experimento ativo da sessão
        exp_id      = request.session.get('experimento_ativo_id')
        experimento = Experimento.objects.filter(pk=exp_id).first() if exp_id else None

        os.makedirs(OUTPUTS_DIR, exist_ok=True)
        # Prefixo com nome do experimento para não sobrescrever outros experimentos
        prefixo = _slug_experimento(experimento)
        caminho_conll = os.path.join(OUTPUTS_DIR, f'{prefixo}corpus.conll')
        caminho_jsonl = os.path.join(OUTPUTS_DIR, f'{prefixo}corpus.jsonl')

        resultado = executar_preprocessamento(
            arquivo_prescricoes=arquivo_prescricoes,
            arquivo_pareceres=arquivo_pareceres,
            caminho_conll=caminho_conll,
            caminho_jsonl=caminho_jsonl,
            amostra=amostra,
            n_total_anotacao=n_total_anotacao,
        )

        defaults = dict(
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
        # OneToOne → atualiza se já existir execução para este experimento
        ExecucaoPreprocessamento.objects.update_or_create(
            experimento=experimento,
            defaults=defaults,
        )

        contexto['resultado'] = resultado

    return render(request, 'preprocessamento/index.html', contexto)


def baixar_arquivo(request, formato):
    from analise_exploratoria.models import Experimento
    exp_id      = request.session.get('experimento_ativo_id')
    experimento = Experimento.objects.filter(pk=exp_id).first() if exp_id else None
    prefixo     = _slug_experimento(experimento)

    nomes = {
        'conll':    f'{prefixo}corpus.conll',
        'jsonl':    f'{prefixo}corpus.jsonl',
        'anotacao': f'{prefixo}corpus_anotacao.jsonl',
    }
    if formato not in nomes:
        raise Http404
    caminho = os.path.join(OUTPUTS_DIR, nomes[formato])
    if not os.path.exists(caminho):
        raise Http404
    return FileResponse(open(caminho, 'rb'), as_attachment=True, filename=nomes[formato])
# Fim - 1) Pré-processamento - Interface Django