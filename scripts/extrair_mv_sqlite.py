"""
Extração de pareceres e prescrições do banco MV (Oracle) para um arquivo SQLite local.

Roda em blocos (BATCH_SIZE linhas por vez, com pausa entre blocos) para não sobrecarregar
o banco de produção do hospital, e é retomável: se cair a conexão ou você precisar
interromper, rodar de novo continua de onde parou (progresso salvo na própria SQLite,
tabela _progresso).

Requisitos:
    pip install oracledb

Uso:
    1. Preencha as credenciais abaixo (ou exporte como variáveis de ambiente
       MV_DB_USER, MV_DB_PASSWORD, MV_DB_DSN antes de rodar).
    2. Ajuste HOSPITAIS_INCLUIDOS se quiser mudar o filtro de hospitais.
    3. python extrair_mv_sqlite.py

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

DB_USER = os.environ.get("MV_DB_USER", "")
DB_PASSWORD = os.environ.get("MV_DB_PASSWORD", "")
DB_DSN = os.environ.get("MV_DB_DSN", "")  # ex: "servidor:1521/SERVICE_NAME"

SQLITE_PATH = "corpus_mv_exp003.sqlite3"

# Mesmo filtro do Exp002: exclui hospital 1 (pediátrico, LGPD de menores) e 7 (CREFES, não é hospital)
HOSPITAIS_INCLUIDOS = (2, 3, 4, 5, 6)

BATCH_SIZE = 5000          # linhas por bloco extraído do Oracle
SLEEP_ENTRE_BLOCOS = 1.5   # segundos de pausa entre blocos, pra não travar o banco de produção

TETO_PRESCRICOES = 500_000  # teto total de prescrições a extrair (pareceres: extrai tudo, sem teto)

# Padrões usados para minerar prescrições com maior chance de conter entidades raras.
# Sintaxe REGEXP_LIKE do Oracle (POSIX), case-insensitive via flag 'i'.
PADRAO_DOCUMENTO = r'(RG|CNS|CRM|CNH)[[:space:]:.\-]{0,3}[0-9]{3,}'
PADRAO_ENDERECO = r'(RUA|AVENIDA|TRAVESSA|RODOVIA|ALAMEDA|BAIRRO)[[:space:]]'

# Tetos de segurança pros blocos minerados — não devem nem chegar perto na prática,
# mas evitam que um padrão mais frequente do que o esperado estoure o orçamento de 500k.
TETO_MINERACAO_DOCUMENTO = 5_000
TETO_MINERACAO_ENDERECO = 30_000


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
    con.commit()
    return con


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

def conectar_oracle():
    if not (DB_USER and DB_PASSWORD and DB_DSN):
        sys.exit(
            "Faltam credenciais. Preencha DB_USER/DB_PASSWORD/DB_DSN no topo do script, "
            "ou exporte as variáveis de ambiente MV_DB_USER, MV_DB_PASSWORD, MV_DB_DSN."
        )
    return oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN)


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


def extrair_prescricoes_mineracao(cursor, con_sqlite, padrao, bloco_nome, teto):
    """Extrai prescrições cujo texto bate com um padrão regex (mira em entidade rara),
    priorizando essas antes da amostra sistemática, até um teto de segurança."""
    sql = f"""
        SELECT {COLUNAS_COMUNS},
               pre.dt_pre_med AS dt_pre_med,
               pre.ds_evolucao AS ds_evolucao
        {JOINS_COMUNS.format(tabela='dbamv.pre_med', alias='pre')}
        WHERE pre.ds_evolucao IS NOT NULL
          AND {FILTRO_HOSPITAIS}
          AND REGEXP_LIKE(pre.ds_evolucao, :padrao, 'i')
        ORDER BY ate.cd_atendimento
        OFFSET :offset ROWS FETCH NEXT :batch ROWS ONLY
    """
    total = extrair_bloco(
        cursor, sql, {"padrao": padrao}, con_sqlite, "prescricoes", bloco_nome,
        colunas_extra={"bloco_origem": bloco_nome},
    )
    return min(total, teto)


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


def main():
    con_sqlite = preparar_sqlite(SQLITE_PATH)
    conn_oracle = conectar_oracle()
    cursor = conn_oracle.cursor()

    print("=== 1/3 — Pareceres (extração completa) ===")
    extrair_pareceres(cursor, con_sqlite)

    print("=== 2/3 — Prescrições: mineração de entidades raras ===")
    usado_documento = extrair_prescricoes_mineracao(
        cursor, con_sqlite, PADRAO_DOCUMENTO, "prescricoes_mineracao_documento", TETO_MINERACAO_DOCUMENTO
    )
    usado_endereco = extrair_prescricoes_mineracao(
        cursor, con_sqlite, PADRAO_ENDERECO, "prescricoes_mineracao_endereco", TETO_MINERACAO_ENDERECO
    )

    print("=== 3/3 — Prescrições: amostragem sistemática (preenche o restante do teto) ===")
    teto_restante = max(0, TETO_PRESCRICOES - usado_documento - usado_endereco)
    extrair_prescricoes_sistematica(cursor, con_sqlite, teto_restante)

    cursor.close()
    conn_oracle.close()
    con_sqlite.close()
    print("Extração concluída. Arquivo:", SQLITE_PATH)


if __name__ == "__main__":
    main()
