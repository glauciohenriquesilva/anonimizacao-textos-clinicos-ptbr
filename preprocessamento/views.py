import ctypes
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime

from django.contrib import messages
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .services.preprocessamento import executar_preprocessamento
from .models import ExecucaoExtracaoMV, ExecucaoPreprocessamento
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


# Início - 1) Pré-processamento - Extração MV (dispara scripts/extrair_mv_sqlite.py em background)

SCRIPT_EXTRACAO_MV = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), 'scripts', 'extrair_mv_sqlite.py'
)
LOGS_EXTRACAO_MV_DIR = os.path.join(OUTPUTS_DIR, 'extracao_mv_logs')

HOSPITAIS_MV = [
    (1, 'Hospital Infantil Nossa Senhora Glória (pediátrico — excluído por padrão)'),
    (2, 'Hospital Estadual de Vila Velha'),
    (3, 'Hospital Estadual Urgência e Emergência'),
    (4, 'Hospital Estadual Silvio Avidos'),
    (5, 'Hospital Dr. Roberto Arnizaut Silvares'),
    (6, 'Hospital Estadual de Atenção Clínica'),
    (7, 'CREFES — Centro Reabilitação Física ES (excluído por padrão)'),
]
HOSPITAIS_PADRAO = [2, 3, 4, 5, 6]  # mesmo filtro do Exp002


def _processo_vivo(pid):
    """Checagem best-effort de processo vivo, multiplataforma (Windows e POSIX)."""
    if not pid:
        return False
    if sys.platform == 'win32':
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def extracao_mv(request):
    exp_id      = request.session.get('experimento_ativo_id')
    experimento = Experimento.objects.filter(pk=exp_id).first() if exp_id else None

    if request.method == 'POST':
        db_user     = request.POST.get('db_user', '').strip()
        db_password = request.POST.get('db_password', '')  # nunca persistido no banco do AnonClin
        db_host     = request.POST.get('db_host', '').strip()
        db_port     = request.POST.get('db_port', '1521').strip()
        db_service  = request.POST.get('db_service', '').strip()
        hospitais   = request.POST.getlist('hospitais') or [str(h) for h in HOSPITAIS_PADRAO]
        teto        = request.POST.get('teto_prescricoes', '500000').strip()
        batch_size  = request.POST.get('batch_size', '5000').strip()
        pausa       = request.POST.get('sleep_entre_blocos', '1.5').strip()
        comecar_do_zero = request.POST.get('comecar_do_zero') == 'on'
        modo        = request.POST.get('modo', 'completo').strip()  # 'completo' ou 'remineracao_prescricoes'

        if not (db_user and db_password and db_host and db_service):
            messages.error(request, 'Preencha usuário, senha, host e service name do banco Oracle.')
            return redirect('preprocessamento:extracao_mv')

        os.makedirs(LOGS_EXTRACAO_MV_DIR, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        prefixo   = _slug_experimento(experimento) or 'sem_experimento_'
        # Nome fixo por experimento (sem timestamp) — assim, rodar de novo depois de um erro
        # RETOMA a extração (usa a tabela _progresso já salva no arquivo), em vez de começar
        # do zero. O log de cada tentativa continua separado, só pra facilitar debug.
        caminho_sqlite = os.path.join(OUTPUTS_DIR, f'{prefixo}corpus_mv.sqlite3')
        caminho_log    = os.path.join(LOGS_EXTRACAO_MV_DIR, f'{prefixo}extracao_mv_{timestamp}.log')

        if modo == 'remineracao_prescricoes':
            # Modo cirúrgico: precisa que já exista um arquivo extraído pra esse experimento
            # (pareceres + sistemática já lá) — a remineração só ADICIONA candidatos novos
            # de DOCUMENTO/ENDERECO/PRONTUARIO/MATRICULA em cima do que já existe, sem tocar
            # pareceres nem refazer a amostragem sistemática. "Começar do zero" não se aplica
            # aqui (apagaria os dados que a remineração precisa preservar).
            if not os.path.exists(caminho_sqlite):
                messages.error(
                    request,
                    f'Modo remineração cirúrgica precisa de uma extração completa já existente '
                    f'para este experimento — não encontrei {os.path.basename(caminho_sqlite)}. '
                    f'Rode a extração completa primeiro, ou troque para esse modo.',
                )
                return redirect('preprocessamento:extracao_mv')
            comecar_do_zero = False
        elif comecar_do_zero:
            for sufixo in ('', '-shm', '-wal', '-journal'):
                caminho_antigo = caminho_sqlite + sufixo
                if os.path.exists(caminho_antigo):
                    os.remove(caminho_antigo)

        env = os.environ.copy()
        env.update({
            'MV_USER': db_user,
            'MV_PASSWORD': db_password,
            'MV_HOST': db_host,
            'MV_PORT': db_port,
            'MV_SERVICE': db_service,
            'MV_SQLITE_PATH': caminho_sqlite,
            'MV_HOSPITAIS': ','.join(hospitais),
            'MV_BATCH_SIZE': batch_size,
            'MV_TETO_PRESCRICOES': teto,
            'MV_SLEEP_ENTRE_BLOCOS': pausa,
            'MV_MODO': modo,
            'PYTHONUNBUFFERED': '1',  # log em tempo real, sem buffer de saída
        })

        log_fh = open(caminho_log, 'w', encoding='utf-8')
        try:
            proc = subprocess.Popen(
                [sys.executable, SCRIPT_EXTRACAO_MV],
                cwd=os.path.dirname(SCRIPT_EXTRACAO_MV),
                env=env,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
            )
        except OSError as exc:
            messages.error(request, f'Não foi possível iniciar o script: {exc}')
            return redirect('preprocessamento:extracao_mv')

        execucao = ExecucaoExtracaoMV.objects.create(
            experimento=experimento,
            status='em_execucao',
            pid=proc.pid,
            hospitais_incluidos=','.join(hospitais),
            teto_prescricoes=int(teto) if teto.isdigit() else None,
            batch_size=int(batch_size) if batch_size.isdigit() else None,
            caminho_sqlite=caminho_sqlite,
            caminho_log=caminho_log,
            obs=f'modo={modo}',
        )
        messages.success(request, 'Extração iniciada em segundo plano. Acompanhe o progresso abaixo.')
        return redirect('preprocessamento:extracao_mv_detalhe', execucao_id=execucao.pk)

    execucoes = ExecucaoExtracaoMV.objects.all()[:20]
    return render(request, 'preprocessamento/extracao_mv.html', {
        'hospitais_mv': HOSPITAIS_MV,
        'hospitais_padrao': HOSPITAIS_PADRAO,
        'execucoes': execucoes,
    })


def extracao_mv_detalhe(request, execucao_id):
    execucao  = get_object_or_404(ExecucaoExtracaoMV, pk=execucao_id)
    execucoes = ExecucaoExtracaoMV.objects.all()[:20]
    return render(request, 'preprocessamento/extracao_mv.html', {
        'hospitais_mv': HOSPITAIS_MV,
        'hospitais_padrao': HOSPITAIS_PADRAO,
        'execucoes': execucoes,
        'execucao_atual': execucao,
    })


def extracao_mv_status(request, execucao_id):
    """Endpoint de polling (JS) — devolve as últimas linhas do log e o progresso lido
    direto da SQLite de destino (tabela _progresso), sem travar a extração em andamento."""
    execucao = get_object_or_404(ExecucaoExtracaoMV, pk=execucao_id)

    linhas_log = []
    if execucao.caminho_log and os.path.exists(execucao.caminho_log):
        with open(execucao.caminho_log, encoding='utf-8', errors='replace') as f:
            linhas_log = f.readlines()[-200:]
    texto_log = ''.join(linhas_log)

    if 'STATUS: FINALIZADO' in texto_log and execucao.status != 'concluido':
        execucao.status = 'concluido'
        execucao.finalizado_em = timezone.now()
        execucao.save(update_fields=['status', 'finalizado_em'])
    elif 'STATUS: ERRO' in texto_log and execucao.status != 'erro':
        execucao.status = 'erro'
        execucao.finalizado_em = timezone.now()
        execucao.save(update_fields=['status', 'finalizado_em'])
    elif execucao.status == 'em_execucao' and not _processo_vivo(execucao.pid):
        # processo sumiu sem deixar marcador de conclusão — provavelmente caiu/foi morto
        execucao.status = 'erro'
        execucao.finalizado_em = timezone.now()
        execucao.save(update_fields=['status', 'finalizado_em'])

    progresso = []
    total_pareceres = total_prescricoes = total_pareceres_esperado = None
    if execucao.caminho_sqlite and os.path.exists(execucao.caminho_sqlite):
        try:
            con = sqlite3.connect(f'file:{execucao.caminho_sqlite}?mode=ro', uri=True, timeout=5)
            cur = con.cursor()
            cur.execute('SELECT bloco, offset_atual, concluido FROM _progresso ORDER BY bloco')
            progresso = [
                {'bloco': b, 'offset': o, 'concluido': bool(c)}
                for b, o, c in cur.fetchall()
            ]
            cur.execute('SELECT COUNT(*) FROM pareceres')
            total_pareceres = cur.fetchone()[0]
            cur.execute('SELECT COUNT(*) FROM prescricoes')
            total_prescricoes = cur.fetchone()[0]
            try:
                cur.execute("SELECT valor FROM _metadados WHERE chave = 'total_pareceres_esperado'")
                row = cur.fetchone()
                total_pareceres_esperado = int(row[0]) if row else None
            except sqlite3.OperationalError:
                pass  # tabela _metadados pode não existir ainda no primeiro instante
            con.close()
        except sqlite3.Error:
            pass  # SQLite pode estar no meio de um commit; tenta de novo no próximo polling

    # Blocos esperados dependem do modo: no modo cirúrgico (remineracao_prescricoes) só roda
    # 1 bloco (mineração v3); no modo completo é pareceres (1) + mineração (1) + 1 por hospital
    # incluído na amostragem sistemática.
    if (execucao.obs or '') == 'modo=remineracao_prescricoes':
        total_blocos = 1
        # O arquivo sqlite reaproveitado carrega o histórico de _progresso da extração completa
        # anterior (pareceres + mineração antiga + 1 por hospital da amostragem sistemática).
        # Contar só o bloco desta execução evita "N de 1" com N > 1.
        blocos_concluidos = sum(
            1 for p in progresso if p['bloco'] == 'prescricoes_mineracao_v3' and p['concluido']
        )
    else:
        n_hospitais = len([h for h in (execucao.hospitais_incluidos or '').split(',') if h.strip()])
        total_blocos = 2 + n_hospitais if n_hospitais else None
        blocos_concluidos = sum(1 for p in progresso if p['concluido'])

    return JsonResponse({
        'status': execucao.status,
        'log_tail': texto_log,
        'progresso': progresso,
        'total_pareceres': total_pareceres,
        'total_pareceres_esperado': total_pareceres_esperado,
        'total_prescricoes': total_prescricoes,
        'total_prescricoes_teto': execucao.teto_prescricoes,
        'blocos_concluidos': blocos_concluidos,
        'total_blocos': total_blocos,
    })
# Fim - 1) Pré-processamento - Extração MV