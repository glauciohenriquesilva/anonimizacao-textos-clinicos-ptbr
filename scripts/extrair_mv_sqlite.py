"""
Extração de pareceres e prescrições do banco MV (Oracle) para um arquivo SQLite local.

Roda em blocos (BATCH_SIZE linhas por vez, com pausa entre blocos) para não sobrecarregar
o banco de produção do hospital, e é retomável: se cair a conexão ou você precisar
interromper, rodar de novo continua de onde parou (progresso salvo na própria SQLite,
tabela _progresso).

Requisitos:
    pip install oracledb

Uso:
    1. Exporte as variáveis de ambiente MV_USER, MV_PASSWORD, MV_HOST, MV_PORT, MV_SERVICE
       antes de rodar (mesmo padrão usado nos outros scripts que conectam no MV).
       Alternativa: exportar MV_DSN direto (ex: "servidor:1521/SERVICE_NAME") em vez de
       host/porta/service separados.
    2. Ajuste HOSPITAIS_INCLUIDOS se quiser mudar o filtro de hospitais.
    3. python extrair_mv_sqlite.py

    Nunca deixe credenciais escritas direto neste arquivo — mesmo localmente, é fácil
    esquecer e commitar. Use sempre variável de ambiente (ou um .env fora do git).

Este script deve ser executado localmente, no seu ambiente, nunca em um sandbox
de terceiros — ele lida com dado hospitalar real (PHI) e credenciais de produção.
"""

import os
import re
import sqlite3
import sys
import time

import oracledb

# ============================================================
# CONFIGURAÇÃO — ajuste antes de rodar
# ============================================================

# Modo "thick" do oracledb — necessário quando o servidor Oracle usa um verificador de
# senha antigo (erro DPY-3015 no modo thin puro, comum em contas legadas tipo dbamv que
# nunca tiveram a senha trocada desde versões antigas do Oracle). Pra ativar, baixe o
# Oracle Instant Client (https://www.oracle.com/database/technologies/instant-client/downloads.html),
# descompacte em qualquer pasta e aponte MV_ORACLE_CLIENT_DIR pra ela. Se não precisar
# (conta com verificador moderno), deixe em branco — o script segue no modo thin normal.
ORACLE_CLIENT_DIR = os.environ.get("MV_ORACLE_CLIENT_DIR", "C:\\oracle\\instantclient_23_6")
if ORACLE_CLIENT_DIR:
    oracledb.init_oracle_client(lib_dir=ORACLE_CLIENT_DIR)

DB_USER = os.environ.get("MV_USER", "")
DB_PASSWORD = os.environ.get("MV_PASSWORD", "")

# Duas formas de configurar a conexão — mesmo padrão usado nos outros scripts que conectam
# no MV: host/porta/service (monta o DSN via oracledb.makedsn) ou, se preferir, um DSN pronto.
DB_HOST = os.environ.get("MV_HOST", "")
DB_PORT = os.environ.get("MV_PORT", "1521")
DB_SERVICE = os.environ.get("MV_SERVICE", "")
DB_DSN_DIRETO = os.environ.get("MV_DSN", "")  # ex: "servidor:1521/SERVICE_NAME" — usado se host/service não forem passados

SQLITE_PATH = os.environ.get("MV_SQLITE_PATH", "corpus_mv_exp003.sqlite3")

# Mesmo filtro do Exp002: exclui hospital 1 (pediátrico, LGPD de menores) e 7 (CREFES, não é hospital).
# Pode ser sobrescrito via MV_HOSPITAIS="2,3,4,5,6" (lista separada por vírgula).
HOSPITAIS_INCLUIDOS = tuple(
    int(h) for h in os.environ.get("MV_HOSPITAIS", "2,3,4,5,6").split(",") if h.strip()
)

BATCH_SIZE = int(os.environ.get("MV_BATCH_SIZE", "5000"))            # linhas por bloco extraído do Oracle
SLEEP_ENTRE_BLOCOS = float(os.environ.get("MV_SLEEP_ENTRE_BLOCOS", "1.5"))  # pausa entre blocos (segundos)

TETO_PRESCRICOES = int(os.environ.get("MV_TETO_PRESCRICOES", "500000"))  # teto de prescrições (pareceres: sem teto)

# Palavras usadas para minerar prescrições com maior chance de conter entidades raras.
#
# IMPORTANTE — descoberta em produção: ds_evolucao é coluna Oracle do tipo LONG, e o Oracle
# proíbe QUALQUER referência a coluna LONG na cláusula WHERE, mesmo dentro de SUBSTR/INSTR
# (ORA-00932 "expected CHAR got LONG" acontece nos dois casos, apesar da documentação do
# Oracle citar SUBSTR/INSTR/LENGTH como "compatíveis com LONG" — essa compatibilidade vale
# só pra usar essas funções na lista do SELECT, não em predicados de filtro). Ou seja: não
# existe forma de pedir ao Oracle "só as linhas que contêm X" filtrando por ds_evolucao.
#
# Por isso a mineração é feita em Python: varremos TODAS as prescrições dos hospitais
# incluídos, paginado do jeito de sempre (OFFSET/FETCH, sem filtro de conteúdo — só
# FILTRO_HOSPITAIS), e decidimos linha a linha se o texto bate algum dos padrões abaixo,
# descartando o resto antes de gravar na SQLite. Ver extrair_prescricoes_mineracao_v3().
#
# CORREÇÃO 05/08/2026 (auditoria pós-Exp003): a v1/v2 usavam substring pura (sem \b), o
# que dava ~99% de falso positivo em DOCUMENTO — "RG" batia dentro de ALERGIAS, CIRURGIA,
# URGÊNCIA etc. Todos os padrões abaixo agora exigem \b (delimitador de palavra). Também
# foram descobertos dois padrões novos genuínos (PRONTUÁRIO de outra instituição e
# MATRÍCULA de aluno/estagiário — ambos identificam uma pessoa específica, mesma lógica
# do CRM médico) e uma ambiguidade semântica em "RUA": ~65% dos casos em pareceres são a
# expressão idiomática "morador/situação de rua" (sem-teto), não um endereço — excluída
# explicitamente em RE_ENDERECO_REAL.
RE_DOCUMENTO = re.compile(r'\b(?:RG|CNS|CRM|CNH)\b', re.IGNORECASE)
RE_PRONTUARIO = re.compile(r'(?i)\bpront(?:u[áa]rio)?\.?\s*[:\-]\s*n?[ºo°]?\s*\d{4,10}\b')
RE_MATRICULA = re.compile(r'(?i)\bmatr[íi]cula\s*[:\-]\s*\d{3,10}\b')
_RE_ENDERECO_KW = re.compile(r'\b(RUA|AVENIDA|TRAVESSA|RODOVIA|ALAMEDA|BAIRRO)\b', re.IGNORECASE)
_RE_DE_RUA = re.compile(r'\bDE\s*$', re.IGNORECASE)  # contexto imediatamente antes do match


def endereco_real(texto):
    """True se o texto tem pelo menos um match de ENDERECO que NÃO seja a expressão
    idiomática 'de rua' (morador de rua / situação de rua — sem-teto, não endereço)."""
    for m in _RE_ENDERECO_KW.finditer(texto):
        if m.group(1).upper() != 'RUA':
            return True
        if not _RE_DE_RUA.search(texto[max(0, m.start() - 4):m.start()]):
            return True
    return False


# Tetos de candidatos REAIS (pós-\b) por categoria — bem acima das cotas mínimas do
# design_corpus.md (DOCUMENTO>=250, ENDERECO>=500) pra dar folga de curadoria/seleção,
# sem escanear a tabela inteira desnecessariamente. PRONTUARIO/MATRICULA são padrões
# raros (achados n=95 e n=107 em 554k linhas já extraídas) — teto baixo é suficiente.
TETO_MINERACAO_DOCUMENTO = 3_000
TETO_MINERACAO_ENDERECO = 8_000
TETO_MINERACAO_PRONTUARIO = 500
TETO_MINERACAO_MATRICULA = 500


# ============================================================
# SQL — colunas e joins compartilhados entre pareceres e prescrições
# ============================================================

COLUNAS_COMUNS = """
    ate.cd_paciente                     AS cd_paciente,
    ate.cd_convenio                     AS cd_convenio,
    conv.nm_convenio                    AS nm_convenio,
    ate.dt_atendimento                  AS dt_atendimento,
    ate.tp_atendimento                  AS tp_atendimento,
    ate.cd_ori_ate                      AS cd_ori_ate,
    ori.ds_ori_ate                      AS ds_ori_ate,
    ate.cd_servico                      AS cd_servico,
    ser.ds_servico                      AS ds_servico,
    ate.cd_mot_alt                      AS cd_mot_alt,
    ma.ds_mot_alt                       AS ds_mot_alt,
    ate.cd_cid                          AS cd_cid,
    cid.ds_cid                          AS ds_cid,
    ate.cd_tipo_internacao              AS cd_tipo_internacao,
    ti.ds_tipo_internacao               AS ds_tipo_internacao,
    ate.cd_loc_proced                   AS cd_loc_proced,
    lp.ds_loc_proced                    AS ds_loc_proced,
    ate.cd_multi_empresa                AS cd_multi_empresa,
    me.ds_multi_empresa                 AS ds_multi_empresa,
    ate.cd_especialid                   AS cd_especialid_atendimento,
    esp_ate.ds_especialid               AS ds_especialid_atendimento,
    ate.cd_tip_mar                      AS cd_tip_mar,
    tm.ds_tip_mar                       AS ds_tip_mar
"""

JOINS_COMUNS = """
    FROM {tabela} {alias}
    JOIN dbamv.atendime ate ON ate.cd_atendimento = {alias}.cd_atendimento
    LEFT JOIN dbamv.convenio conv ON conv.cd_convenio = ate.cd_convenio
    LEFT JOIN dbamv.ori_ate ori ON ori.cd_ori_ate = ate.cd_ori_ate
    LEFT JOIN dbamv.servico ser ON ser.cd_servico = ate.cd_servico
    LEFT JOIN dbamv.mot_alt ma ON ma.cd_mot_alt = ate.cd_mot_alt
    LEFT JOIN dbamv.cid cid ON cid.cd_cid = ate.cd_cid
    LEFT JOIN dbamv.tipo_internacao ti ON ti.cd_tipo_internacao = ate.cd_tipo_internacao
    LEFT JOIN dbamv.loc_proced lp ON lp.cd_loc_proced = ate.cd_loc_proced
    LEFT JOIN dbamv.multi_empresas me ON me.cd_multi_empresa = ate.cd_multi_empresa
    LEFT JOIN dbamv.especialid esp_ate ON esp_ate.cd_especialid = ate.cd_especialid
    LEFT JOIN dbamv.tip_mar tm ON tm.cd_tip_mar = ate.cd_tip_mar
"""

FILTRO_HOSPITAIS = "ate.cd_multi_empresa IN ({})".format(
    ", ".join(str(h) for h in HOSPITAIS_INCLUIDOS)
)


# ============================================================
# SQLite — schema e controle de progresso (retomável)
# ============================================================

def preparar_sqlite(caminho):
    con = sqlite3.connect(caminho)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""
        CREATE TABLE IF NOT EXISTS pareceres (
            cd_paciente INTEGER, cd_convenio INTEGER, nm_convenio TEXT,
            dt_atendimento TEXT, tp_atendimento TEXT, cd_ori_ate INTEGER, ds_ori_ate TEXT,
            cd_servico INTEGER, ds_servico TEXT, cd_mot_alt INTEGER, ds_mot_alt TEXT,
            cd_cid TEXT, ds_cid TEXT, cd_tipo_internacao INTEGER, ds_tipo_internacao TEXT,
            cd_loc_proced INTEGER, ds_loc_proced TEXT, cd_multi_empresa INTEGER, ds_multi_empresa TEXT,
            cd_especialid_atendimento INTEGER, ds_especialid_atendimento TEXT,
            cd_tip_mar INTEGER, ds_tip_mar TEXT,
            dt_parecer TEXT, ds_situacao TEXT, ds_parecer TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS prescricoes (
            cd_paciente INTEGER, cd_convenio INTEGER, nm_convenio TEXT,
            dt_atendimento TEXT, tp_atendimento TEXT, cd_ori_ate INTEGER, ds_ori_ate TEXT,
            cd_servico INTEGER, ds_servico TEXT, cd_mot_alt INTEGER, ds_mot_alt TEXT,
            cd_cid TEXT, ds_cid TEXT, cd_tipo_internacao INTEGER, ds_tipo_internacao TEXT,
            cd_loc_proced INTEGER, ds_loc_proced TEXT, cd_multi_empresa INTEGER, ds_multi_empresa TEXT,
            cd_especialid_atendimento INTEGER, ds_especialid_atendimento TEXT,
            cd_tip_mar INTEGER, ds_tip_mar TEXT,
            dt_pre_med TEXT, ds_evolucao TEXT,
            bloco_origem TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS _progresso (
            bloco TEXT PRIMARY KEY,
            offset_atual INTEGER,
            concluido INTEGER DEFAULT 0
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS _metadados (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)
    con.commit()
    return con


def ler_metadado(con, chave):
    row = con.execute("SELECT valor FROM _metadados WHERE chave = ?", (chave,)).fetchone()
    return row[0] if row else None


def salvar_metadado(con, chave, valor):
    con.execute("""
        INSERT INTO _metadados (chave, valor) VALUES (?, ?)
        ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor
    """, (chave, str(valor)))
    con.commit()


def ler_offset(con, bloco):
    row = con.execute("SELECT offset_atual, concluido FROM _progresso WHERE bloco = ?", (bloco,)).fetchone()
    if row is None:
        return 0, False
    return row[0], bool(row[1])


def salvar_offset(con, bloco, offset, concluido=False):
    con.execute("""
        INSERT INTO _progresso (bloco, offset_atual, concluido) VALUES (?, ?, ?)
        ON CONFLICT(bloco) DO UPDATE SET offset_atual = excluded.offset_atual, concluido = excluded.concluido
    """, (bloco, offset, int(concluido)))
    con.commit()


# ============================================================
# Extração em blocos
# ============================================================

def montar_dsn():
    """Monta o DSN via oracledb.makedsn (host/porta/service), mesmo padrão dos outros
    scripts que conectam no MV. Se host/service não vierem, cai pro DSN direto (MV_DSN)."""
    if DB_HOST and DB_SERVICE:
        return oracledb.makedsn(DB_HOST, DB_PORT, service_name=DB_SERVICE)
    if DB_DSN_DIRETO:
        return DB_DSN_DIRETO
    return None


def conectar_oracle():
    dsn = montar_dsn()
    if not (DB_USER and DB_PASSWORD and dsn):
        sys.exit(
            "Faltam credenciais/conexão. Exporte MV_USER, MV_PASSWORD e (MV_HOST + MV_SERVICE, "
            "opcionalmente MV_PORT) ou MV_DSN direto — nunca escreva isso no arquivo."
        )
    try:
        return oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=dsn)
    except oracledb.DatabaseError as e:
        (error,) = e.args
        msg = getattr(error, 'message', str(error))
        if 'DPY-3015' in msg and not ORACLE_CLIENT_DIR:
            msg += (
                "\n-> Essa conta usa um verificador de senha antigo, incompatível com o modo "
                "thin puro do oracledb. Baixe o Oracle Instant Client e configure "
                "MV_ORACLE_CLIENT_DIR apontando pra pasta descompactada (veja o topo do script)."
            )
        sys.exit(f"Erro de conexão com o banco do MV: {msg}")
    except oracledb.InterfaceError as e:
        (error,) = e.args
        sys.exit(f"Erro de interface com o MV: {getattr(error, 'message', str(error))}")
    except Exception as e:
        sys.exit(f"Erro inesperado ao conectar com o MV: {e}")


def extrair_bloco(cursor, sql, params, con_sqlite, tabela_destino, bloco_nome, colunas_extra=None):
    """Executa a extração paginada de uma query, gravando em blocos na SQLite.
    Retomável: começa do offset salvo em _progresso, se houver."""
    offset, concluido = ler_offset(con_sqlite, bloco_nome)
    if concluido:
        print(f"[{bloco_nome}] já concluído anteriormente, pulando.")
        return offset

    while True:
        params_pagina = dict(params)
        params_pagina["offset"] = offset
        params_pagina["batch"] = BATCH_SIZE
        cursor.execute(sql, params_pagina)
        linhas = cursor.fetchall()
        if not linhas:
            salvar_offset(con_sqlite, bloco_nome, offset, concluido=True)
            print(f"[{bloco_nome}] concluído — {offset} linhas no total.")
            break

        nomes_colunas = [d[0].lower() for d in cursor.description]
        if colunas_extra:
            for col, valor in colunas_extra.items():
                nomes_colunas.append(col)
                linhas = [tuple(l) + (valor,) for l in linhas]

        placeholders = ", ".join(["?"] * len(nomes_colunas))
        sql_insert = f"INSERT INTO {tabela_destino} ({', '.join(nomes_colunas)}) VALUES ({placeholders})"
        con_sqlite.executemany(sql_insert, linhas)
        con_sqlite.commit()

        offset += len(linhas)
        salvar_offset(con_sqlite, bloco_nome, offset, concluido=False)
        print(f"[{bloco_nome}] +{len(linhas)} linhas (total: {offset})")

        if len(linhas) < BATCH_SIZE:
            salvar_offset(con_sqlite, bloco_nome, offset, concluido=True)
            print(f"[{bloco_nome}] concluído — {offset} linhas no total.")
            break

        time.sleep(SLEEP_ENTRE_BLOCOS)

    return offset


def extrair_pareceres(cursor, con_sqlite):
    """Extrai TODOS os pareceres dos hospitais incluídos (sem teto — volume é gerenciável, ~426k+)."""
    # Conta o total esperado uma única vez (fica salvo em _metadados) — a interface do AnonClin
    # usa isso pra mostrar "X de Y extraídos". Não reconta em cada retomada (COUNT em ~426k+
    # linhas com join não é instantâneo, e o número não muda durante a extração).
    if ler_metadado(con_sqlite, 'total_pareceres_esperado') is None:
        cursor.execute(f"""
            SELECT COUNT(*)
            FROM dbamv.par_med par
            JOIN dbamv.atendime ate ON ate.cd_atendimento = par.cd_atendimento
            WHERE par.ds_parecer IS NOT NULL AND {FILTRO_HOSPITAIS}
        """)
        total = cursor.fetchone()[0]
        salvar_metadado(con_sqlite, 'total_pareceres_esperado', total)
        print(f"[pareceres] total esperado: {total}")

    sql = f"""
        SELECT {COLUNAS_COMUNS},
               par.dt_parecer AS dt_parecer,
               par.ds_situacao AS ds_situacao,
               par.ds_parecer AS ds_parecer
        {JOINS_COMUNS.format(tabela='dbamv.par_med', alias='par')}
        WHERE par.ds_parecer IS NOT NULL
          AND {FILTRO_HOSPITAIS}
        ORDER BY par.dt_parecer, ate.cd_atendimento
        OFFSET :offset ROWS FETCH NEXT :batch ROWS ONLY
    """
    extrair_bloco(cursor, sql, {}, con_sqlite, "pareceres", "pareceres_completo")


def carregar_chaves_existentes(con_sqlite):
    """Carrega um set de chaves (cd_paciente, dt_pre_med, hash do texto) de tudo que já
    está na tabela prescricoes, pra mineração nova não reinserir o que já foi extraído
    (nem pela sistemática, nem pela mineração v1/v2 antiga)."""
    import hashlib
    chaves = set()
    cur = con_sqlite.execute("SELECT cd_paciente, dt_pre_med, ds_evolucao FROM prescricoes")
    for cd_paciente, dt_pre_med, texto in cur:
        h = hashlib.md5((texto or "").encode("utf-8", "ignore")).hexdigest()
        chaves.add((cd_paciente, dt_pre_med, h))
    return chaves


def extrair_prescricoes_mineracao_v3(cursor, con_sqlite):
    """Mineração CORRIGIDA (05/08/2026) de DOCUMENTO/ENDERECO/PRONTUARIO/MATRICULA nas
    prescrições, varrendo os hospitais incluídos por paginação KEYSET (mesma técnica da
    v2 — ver nota histórica abaixo). Corrige 3 problemas encontrados na auditoria pós-Exp003:

      1. v1/v2 usavam substring sem \\b → ~99% de falso positivo em DOCUMENTO ("RG" batia
         dentro de ALERGIAS/CIRURGIA/URGÊNCIA). Agora todos os padrões exigem \\b.
      2. v1/v2 paravam de TESTAR uma categoria assim que a cota dela enchia (mesmo que a
         cota tivesse enchido só de falso positivo) — podia pular candidatos reais no
         resto da varredura. Agora todas as categorias são testadas em toda linha até
         TODAS as cotas serem atingidas (ou a tabela acabar).
      3. Roda sobre TODA a tabela de novo (não só o que falta) mas pula linhas cuja
         combinação (cd_paciente, dt_pre_med, hash do texto) já existe localmente — evita
         duplicar o que a sistemática ou a mineração v1/v2 antiga já trouxeram.

    Nota histórica (paginação): usa WHERE cd_pre_med > :ultimo ORDER BY cd_pre_med FETCH
    NEXT (keyset), não OFFSET — Oracle reordenaria o resultado inteiro do JOIN a cada
    página com OFFSET sobre uma tabela sem filtro de conteúdo reduzindo o volume.
    """
    bloco_nome = "prescricoes_mineracao_v3"
    chave_doc = "mineracao_v3_documento"
    chave_end = "mineracao_v3_endereco"
    chave_pront = "mineracao_v3_prontuario"
    chave_matr = "mineracao_v3_matricula"

    ultimo_pre_med, concluido = ler_offset(con_sqlite, bloco_nome)
    n_doc = int(ler_metadado(con_sqlite, chave_doc) or 0)
    n_end = int(ler_metadado(con_sqlite, chave_end) or 0)
    n_pront = int(ler_metadado(con_sqlite, chave_pront) or 0)
    n_matr = int(ler_metadado(con_sqlite, chave_matr) or 0)

    if concluido:
        print(f"[{bloco_nome}] já concluído. documento={n_doc} endereco={n_end} prontuario={n_pront} matricula={n_matr}")
        return n_doc, n_end, n_pront, n_matr

    print(f"[{bloco_nome}] carregando chaves já extraídas localmente (dedup)...")
    chaves_existentes = carregar_chaves_existentes(con_sqlite)
    print(f"[{bloco_nome}] {len(chaves_existentes)} chaves carregadas.")

    import hashlib

    sql = f"""
        SELECT pre.cd_pre_med AS cd_pre_med,
               {COLUNAS_COMUNS},
               pre.dt_pre_med AS dt_pre_med,
               pre.ds_evolucao AS ds_evolucao
        {JOINS_COMUNS.format(tabela='dbamv.pre_med', alias='pre')}
        WHERE pre.ds_evolucao IS NOT NULL
          AND {FILTRO_HOSPITAIS}
          AND pre.cd_pre_med > :ultimo
        ORDER BY pre.cd_pre_med
        FETCH NEXT :batch ROWS ONLY
    """

    def cotas_completas():
        return (n_doc >= TETO_MINERACAO_DOCUMENTO and n_end >= TETO_MINERACAO_ENDERECO
                and n_pront >= TETO_MINERACAO_PRONTUARIO and n_matr >= TETO_MINERACAO_MATRICULA)

    while not cotas_completas():
        cursor.execute(sql, {"ultimo": ultimo_pre_med, "batch": BATCH_SIZE})
        linhas = cursor.fetchall()
        if not linhas:
            break

        nomes_colunas = [d[0].lower() for d in cursor.description]
        idx_evolucao = nomes_colunas.index("ds_evolucao")
        idx_pre_med = nomes_colunas.index("cd_pre_med")
        idx_paciente = nomes_colunas.index("cd_paciente")
        idx_dt = nomes_colunas.index("dt_pre_med")

        nomes_insert = [c for c in nomes_colunas if c != "cd_pre_med"] + ["bloco_origem"]
        placeholders = ", ".join(["?"] * len(nomes_insert))
        sql_insert = f"INSERT INTO prescricoes ({', '.join(nomes_insert)}) VALUES ({placeholders})"

        linhas_insert = []
        for linha in linhas:
            texto = linha[idx_evolucao]
            if not texto:
                continue

            chave = (linha[idx_paciente], linha[idx_dt], hashlib.md5(texto.encode("utf-8", "ignore")).hexdigest())
            if chave in chaves_existentes:
                continue  # já temos essa linha localmente (sistemática ou mineração antiga)

            valores = tuple(v for i, v in enumerate(linha) if i != idx_pre_med)
            origem = None
            if n_doc < TETO_MINERACAO_DOCUMENTO and RE_DOCUMENTO.search(texto):
                origem = "mineracao_documento"
                n_doc += 1
            elif n_pront < TETO_MINERACAO_PRONTUARIO and RE_PRONTUARIO.search(texto):
                origem = "mineracao_prontuario"
                n_pront += 1
            elif n_matr < TETO_MINERACAO_MATRICULA and RE_MATRICULA.search(texto):
                origem = "mineracao_matricula"
                n_matr += 1
            elif n_end < TETO_MINERACAO_ENDERECO and endereco_real(texto):
                origem = "mineracao_endereco"
                n_end += 1

            if origem:
                linhas_insert.append(valores + (origem,))
                chaves_existentes.add(chave)

        if linhas_insert:
            con_sqlite.executemany(sql_insert, linhas_insert)

        ultimo_pre_med = linhas[-1][idx_pre_med]
        salvar_offset(con_sqlite, bloco_nome, ultimo_pre_med, concluido=False)
        salvar_metadado(con_sqlite, chave_doc, n_doc)
        salvar_metadado(con_sqlite, chave_end, n_end)
        salvar_metadado(con_sqlite, chave_pront, n_pront)
        salvar_metadado(con_sqlite, chave_matr, n_matr)
        con_sqlite.commit()
        print(
            f"[{bloco_nome}] cursor cd_pre_med={ultimo_pre_med} | "
            f"documento {n_doc}/{TETO_MINERACAO_DOCUMENTO} | endereco {n_end}/{TETO_MINERACAO_ENDERECO} | "
            f"prontuario {n_pront}/{TETO_MINERACAO_PRONTUARIO} | matricula {n_matr}/{TETO_MINERACAO_MATRICULA}"
        )

        if len(linhas) < BATCH_SIZE:
            break

        time.sleep(SLEEP_ENTRE_BLOCOS)

    salvar_offset(con_sqlite, bloco_nome, ultimo_pre_med, concluido=True)
    salvar_metadado(con_sqlite, chave_doc, n_doc)
    salvar_metadado(con_sqlite, chave_end, n_end)
    salvar_metadado(con_sqlite, chave_pront, n_pront)
    salvar_metadado(con_sqlite, chave_matr, n_matr)
    print(f"[{bloco_nome}] concluído — documento={n_doc} endereco={n_end} prontuario={n_pront} matricula={n_matr}")
    return n_doc, n_end, n_pront, n_matr


def extrair_prescricoes_sistematica(cursor, con_sqlite, teto_restante):
    """Preenche o restante do orçamento com amostragem sistemática determinística
    (MOD(cd_atendimento, stride) = 0), espalhada pelos 5 hospitais — evita o viés
    de 'só os mais recentes' da query original, e é resumível (determinística)."""
    alvo_por_hospital = teto_restante // len(HOSPITAIS_INCLUIDOS)

    for hospital in HOSPITAIS_INCLUIDOS:
        cursor.execute(f"""
            SELECT COUNT(*)
            FROM dbamv.pre_med pre
            JOIN dbamv.atendime ate ON ate.cd_atendimento = pre.cd_atendimento
            WHERE pre.ds_evolucao IS NOT NULL AND ate.cd_multi_empresa = :hospital
        """, {"hospital": hospital})
        total_hospital = cursor.fetchone()[0]

        stride = max(1, total_hospital // max(alvo_por_hospital, 1))
        bloco_nome = f"prescricoes_sistematica_h{hospital}"

        sql = f"""
            SELECT {COLUNAS_COMUNS},
                   pre.dt_pre_med AS dt_pre_med,
                   pre.ds_evolucao AS ds_evolucao
            {JOINS_COMUNS.format(tabela='dbamv.pre_med', alias='pre')}
            WHERE pre.ds_evolucao IS NOT NULL
              AND ate.cd_multi_empresa = :hospital
              AND MOD(ate.cd_atendimento, :stride) = 0
            ORDER BY ate.cd_atendimento
            OFFSET :offset ROWS FETCH NEXT :batch ROWS ONLY
        """
        print(f"[{bloco_nome}] total no hospital: {total_hospital}, stride: {stride}, alvo: ~{alvo_por_hospital}")
        extrair_bloco(
            cursor, sql, {"hospital": hospital, "stride": stride}, con_sqlite, "prescricoes", bloco_nome,
            colunas_extra={"bloco_origem": "sistematica"},
        )


# MV_MODO controla o que o script faz:
#   "completo"                 (padrão) — pareceres + mineração + sistemática, do zero
#   "remineracao_prescricoes"  — SÓ a mineração corrigida de prescrições (v3), sem
#                                 re-extrair pareceres (já completos) nem refazer a
#                                 sistemática (sem bug) — usado pra corrigir só a parte
#                                 contaminada de uma extração anterior sem bater o Oracle
#                                 com uma extração completa de novo.
MODO = os.environ.get("MV_MODO", "completo")


def main():
    con_sqlite = preparar_sqlite(SQLITE_PATH)
    conn_oracle = conectar_oracle()
    cursor = conn_oracle.cursor()
    # Por padrão o driver oracledb busca só 100 linhas por vez internamente (arraysize) e
    # pré-busca só 2 (prefetchrows) — mesmo pedindo BATCH_SIZE linhas com fetchall(), isso
    # significa dezenas de idas-e-vindas escondidas por bloco. Igualando os dois ao tamanho
    # do bloco, cada página vira uma única ida-e-volta de rede em vez de ~BATCH_SIZE/100.
    cursor.arraysize = BATCH_SIZE
    cursor.prefetchrows = BATCH_SIZE

    if MODO == "remineracao_prescricoes":
        print("=== MODO remineracao_prescricoes: só mineração corrigida de DOCUMENTO/ENDERECO/")
        print("    PRONTUARIO/MATRICULA em prescrições. Pareceres e amostragem sistemática NÃO")
        print("    são tocados (assume-se que já existem no arquivo SQLite de destino). ===")
        extrair_prescricoes_mineracao_v3(cursor, con_sqlite)
    else:
        print("=== 1/3 — Pareceres (extração completa) ===")
        extrair_pareceres(cursor, con_sqlite)

        print("=== 2/3 — Prescrições: mineração de entidades raras (varredura completa) ===")
        usado_documento, usado_endereco, _, _ = extrair_prescricoes_mineracao_v3(cursor, con_sqlite)

        print("=== 3/3 — Prescrições: amostragem sistemática (preenche o restante do teto) ===")
        teto_restante = max(0, TETO_PRESCRICOES - usado_documento - usado_endereco)
        extrair_prescricoes_sistematica(cursor, con_sqlite, teto_restante)

    cursor.close()
    conn_oracle.close()
    con_sqlite.close()
    print("Extração concluída. Arquivo:", SQLITE_PATH)
    # Marcador lido pela interface do AnonClin (preprocessamento/views.py) para saber
    # que o processo em background terminou com sucesso — não remover nem traduzir.
    print("STATUS: FINALIZADO")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # captura qualquer falha e sinaliza pra interface do AnonClin
        print(f"ERRO: {exc!r}")
        print("STATUS: ERRO")
        raise
