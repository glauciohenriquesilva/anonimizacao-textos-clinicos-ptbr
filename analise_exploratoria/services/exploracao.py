import pandas as pd

# Início - 0) Análise Exploratória - 0.1) Leitura do DataSet - 0.1.1) Leitura CSV prescrições (sep=";", UTF-8)
def ler_prescricoes(caminho):
    df = pd.read_csv(
        caminho,
        sep=';',
        encoding='utf-8',       # garante que acentos e caracteres especiais sejam lidos corretamente
        dtype=str,
        on_bad_lines='warn',    # se houver uma linha mal formatada no CSV, apenas avisa no terminal em vez de travar a leitura
    )
    return df
# Fim - 0) Análise Exploratória - 0.1) Leitura do DataSet - 0.1.1) Leitura CSV prescrições (sep=";", UTF-8)

# Início - 0) Análise Exploratória - 0.1) Leitura do DataSet - 0.1.2) Leitura CSV pareceres (sep=";", UTF-8)
def ler_pareceres(caminho):
    df = pd.read_csv(
        caminho,
        sep=';',
        encoding='utf-8',
        dtype=str,
        on_bad_lines='warn',
    )
    return df
# Fim - 0) Análise Exploratória - 0.1) Leitura do DataSet - 0.1.2) Leitura CSV pareceres (sep=";", UTF-8)

# Início - 0) Análise Exploratória - 0.2) Estatísticas Descritivas - 0.2.1) Contagem total de registros por tipo
def contar_registros(df_prescricoes, df_pareceres):
    return {
        'total': len(df_prescricoes) + len(df_pareceres),
        'prescricoes': len(df_prescricoes),
        'pareceres': len(df_pareceres),
    }
# Fim - 0) Análise Exploratória - 0.2) Estatísticas Descritivas - 0.2.1) Contagem total de registros por tipo

# Início - 0) Análise Exploratória - 0.2) Estatísticas Descritivas - 0.2.2) Pacientes únicos (cd_paciente)
def contar_pacientes_unicos(df_prescricoes, df_pareceres):
    #junta as duas colunas cd_paciente (prescrições + pareceres) em uma única série, e depois conta os valores únicos (nunique)
    pacientes = pd.concat(
        [df_prescricoes['cd_paciente'], df_pareceres['cd_paciente']]
    ).nunique()
    return pacientes
# Fim - 0) Análise Exploratória - 0.2) Estatísticas Descritivas - 0.2.2) Pacientes únicos (cd_paciente)

# Início - 0) Análise Exploratória - 0.2) Estatísticas Descritivas - 0.2.3) Período coberto (dt_atendimento min/max)
def periodo_coberto(df_prescricoes, df_pareceres):
    #junta as datas dos dois DataFrames em uma única série
    datas = pd.concat(
        [df_prescricoes['dt_atendimento'], df_pareceres['dt_atendimento']]
    )

    #converte os valores para o tipo data
    datas = pd.to_datetime(datas, errors='coerce')
    
    return {
        'inicio': datas.min(),
        'fim': datas.max(),
    }
# Fim - 0) Análise Exploratória - 0.2) Estatísticas Descritivas - 0.2.3) Período coberto (dt_atendimento min/max)

# Início - 0) Análise Exploratória - 0.2) Estatísticas Descritivas - 0.2.4) Top especialidades médicas
def top_especialidades(df_prescricoes, df_pareceres, n=10):
    especialidades = pd.concat(
        [df_prescricoes['ds_especialid_atendimento'], df_pareceres['ds_especialid_atendimento']]
    )
    contagem = especialidades.value_counts().head(n)
    return contagem
# Fim - 0) Análise Exploratória - 0.2) Estatísticas Descritivas - 0.2.4) Top especialidades médicas

# Início - 0) Análise Exploratória - 0.2) Estatísticas Descritivas - 0.2.5) Contagem de hospitais
def contar_hospitais(df_prescricoes, df_pareceres):
    hospitais = pd.concat(
        [df_prescricoes['ds_multi_empresa'], df_pareceres['ds_multi_empresa']]
    ).nunique()
    return hospitais
# Fim - 0) Análise Exploratória - 0.2) Estatísticas Descritivas - 0.2.5) Contagem de hospitais
