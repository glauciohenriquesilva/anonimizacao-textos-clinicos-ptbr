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
    df.columns = df.columns.str.lower().str.strip()  # Oracle exporta colunas em uppercase
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
    df.columns = df.columns.str.lower().str.strip()  # Oracle exporta colunas em uppercase
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
    col = 'ds_especialid_atendimento'
    series = []
    if col in df_prescricoes.columns:
        series.append(df_prescricoes[col])
    if col in df_pareceres.columns:
        series.append(df_pareceres[col])
    if not series:
        return pd.Series(dtype=str)
    especialidades = pd.concat(series)
    return especialidades.value_counts().head(n)
# Fim - 0) Análise Exploratória - 0.2) Estatísticas Descritivas - 0.2.4) Top especialidades médicas

# Início - 0) Análise Exploratória - 0.2) Estatísticas Descritivas - 0.2.5) Contagem de hospitais
def contar_hospitais(df_prescricoes, df_pareceres):
    # Prefere ds_multi_empresa (nome); fallback para cd_multi_empresa (código)
    col = 'ds_multi_empresa'
    if col not in df_prescricoes.columns and col not in df_pareceres.columns:
        col = 'cd_multi_empresa'
    series = []
    if col in df_prescricoes.columns:
        series.append(df_prescricoes[col])
    if col in df_pareceres.columns:
        series.append(df_pareceres[col])
    if not series:
        return 0
    return pd.concat(series).nunique()
# Fim - 0) Análise Exploratória - 0.2) Estatísticas Descritivas - 0.2.5) Contagem de hospitais

# Início - 0) Análise Exploratória - 0.3) Distribuição de Tokens - 0.3.1) Tokenização simples (split por espaço)
def tokenizar(texto):
    # Verifica se o valor é uma string, pois algumas células do CSV podem estar vazias (NaN)
    if not isinstance(texto, str):
        return []
    return texto.split() # Divide o texto por espaços, retornando uma lista de palavras

    # Exemplo de uso:
    # texto = "Paciente apresenta dor abdominal"
    # texto.split()
    # resultado: ['Paciente', 'apresenta', 'dor', 'abdominal']
# Fim - 0) Análise Exploratória - 0.3) Distribuição de Tokens - 0.3.1) Tokenização simples (split por espaço)

# Início - 0) Análise Exploratória - 0.3) Distribuição de Tokens - 0.3.2) Cálculo min / mediana / média / máx / p25 / p75
def calcular_distribuicao_tokens(df, coluna_texto):
    # Aplica a função de tokenização em cada texto da coluna, e conta quantos tokens cada texto possui (len da lista de tokens)
    contagens = df[coluna_texto].apply(lambda texto: len(tokenizar(texto)))

    # Calcula as estatísticas descritivas: mínimo, média, mediana, máximo, percentil 25 e percentil 75
    return {
        'min': int(contagens.min()),
        'media': round(float(contagens.mean()), 1),
        'mediana': int(contagens.median()),
        'max': int(contagens.max()),
        'p25': int(contagens.quantile(0.25)),
        'p75': int(contagens.quantile(0.75)),
    }
# Fim - 0) Análise Exploratória - 0.3) Distribuição de Tokens - 0.3.2) Cálculo min / mediana / média / máx / p25 / p75

# Início - 0) Análise Exploratória - 0.3) Distribuição de Tokens - 0.3.3) Distribuição de caracteres por doc
def calcular_distribuicao_caracteres(df, coluna_texto):

    # Aplica uma função lambda que conta o número de caracteres em cada texto da coluna. Se o valor não for uma string (por exemplo, NaN), conta como 0 caracteres.
    contagens = df[coluna_texto].apply(lambda texto: len(texto) if isinstance(texto, str) else 0)

    # Calcula as estatísticas descritivas: mínimo, média, mediana, máximo, percentil 25 e percentil 75
    return {
        'min': int(contagens.min()),
        'media': round(float(contagens.mean()), 1),
        'mediana': int(contagens.median()),
        'max': int(contagens.max()),
        'p25': int(contagens.quantile(0.25)),
        'p75': int(contagens.quantile(0.75)),
    }
# Fim - 0) Análise Exploratória - 0.3) Distribuição de Tokens - 0.3.3) Distribuição de caracteres por doc

# Início - 0) Análise Exploratória - 0.3) Distribuição de Tokens - 0.3.4) Distribuição de sentenças por doc
def calcular_distribuicao_sentencas(df, coluna_texto):
    # Para contar o número de sentenças, podemos usar uma abordagem simples de dividir o texto por pontos ('.'). 
    # Isso é uma aproximação comum, embora não seja perfeita, pois pode haver casos em que um ponto não indica o final de uma sentença (como em abreviações). 
    # No entanto, para uma análise exploratória inicial, essa abordagem é suficiente.
    # É uma aproximação simples — não é perfeita porque abreviações como "Dr." também contêm ponto, mas para análise exploratória é suficiente

    # Aplica uma função lambda que conta o número de sentenças em cada texto da coluna. Considera que as sentenças são separadas por pontos ('.'). Se o valor não for uma string, conta como 0 sentenças.
    contagens = df[coluna_texto].apply(lambda texto: len(texto.split('.')) if isinstance(texto, str) else 0)

    # Calcula as estatísticas descritivas: mínimo, média, mediana, máximo, percentil 25 e percentil 75
    return {
        'min': int(contagens.min()),
        'media': round(float(contagens.mean()), 1),
        'mediana': int(contagens.median()),
        'max': int(contagens.max()),
        'p25': int(contagens.quantile(0.25)),
        'p75': int(contagens.quantile(0.75)),
    }

    # Exemplo de uso:
    # texto = "Paciente apresenta dor abdominal. Prescrito dipirona 500mg. Retorno em 7 dias."
    # texto.split('.')
    # resultado: ['Paciente apresenta dor abdominal', ' Prescrito dipirona 500mg', ' Retorno em 7 dias', '']
# Fim - 0) Análise Exploratória - 0.3) Distribuição de Tokens - 0.3.4) Distribuição de sentenças por doc

# Início - 0) Análise Exploratória - 0.4) Classificação do Tipo de Texto - 0.4.1) Detecção texto livre vs. template estruturado
def classificar_tipo_texto(texto):
    if not isinstance(texto, str):
        return 'desconhecido'
    
    # Para detectar se um texto é um template estruturado, podemos procurar por padrões comuns que indicam a presença de campos pré-definidos.
    # lista com padrões que identificam formulários estruturados de UTI/enfermagem, onde médicos marcam checkboxes
    marcadores_template = ['( X )', '[ X ]', '(X)', '[X]', 'SINAIS VITAIS:']

    # Se algum desses marcadores estiver presente no texto, classificamos como 'template_estruturado'. Caso contrário, classificamos como 'texto_livre'.
    for marcador in marcadores_template:
        if marcador in texto:
            return 'template_estruturado'
    return 'texto_livre'
# Fim - 0) Análise Exploratória - 0.4) Classificação do Tipo de Texto - 0.4.1) Detecção texto livre vs. template estruturado

# Início - 0) Análise Exploratória - 0.4) Classificação do Tipo de Texto - 0.4.2) Cálculo da proporção texto livre / template por tipo de doc
def calcular_proporcao_tipos(df, coluna_texto):
    # Aplica a função de classificação de tipo de texto em cada registro da coluna, e conta quantos registros caem em cada categoria (texto livre, template estruturado, desconhecido)
    tipos = df[coluna_texto].apply(classificar_tipo_texto)
    contagem = tipos.value_counts() # conta quantos documentos são de cada tipo
    total = len(df)

    # Calcula a proporção de cada tipo em relação ao total, e retorna um dicionário com os resultados. 
    # A função get é usada para evitar erros caso alguma categoria não esteja presente (por exemplo, se não houver nenhum template estruturado, contagem.get('template_estruturado', 0) retornará 0 em vez de causar um erro)
    return {
        'texto_livre': int(contagem.get('texto_livre', 0)),
        'template_estruturado': int(contagem.get('template_estruturado', 0)),
        'desconhecido': int(contagem.get('desconhecido', 0)),
        'pct_texto_livre': round(contagem.get('texto_livre', 0) / total * 100, 1),
        'pct_template': round(contagem.get('template_estruturado', 0) / total * 100, 1),
    }
# Fim - 0) Análise Exploratória - 0.4) Classificação do Tipo de Texto - 0.4.2) Cálculo da proporção texto livre / template por tipo de doc

# Início - 0) Análise Exploratória - 0.5) Geração de Saídas - 0.5.1) Tabela 1 da dissertação (CSV + Excel)
def gerar_tabela1(registros, pacientes, periodo, hospitais,
                  tokens_presc, tokens_par,
                  caracteres_presc, caracteres_par,
                  sentencas_presc, sentencas_par,
                  tipos_presc, tipos_par):

    # Cria uma lista de tuplas, onde cada tupla representa uma linha da tabela, com a característica analisada e os valores correspondentes para prescrições e pareceres.
    linhas = [
        # 0.2 Estatísticas Descritivas
        ('Total de registros',           registros['prescricoes'],                registros['pareceres']),
        ('Pacientes únicos (combinado)',  pacientes,                               '—'),
        ('Período — início',             periodo['inicio'],                       periodo['inicio']),
        ('Período — fim',                periodo['fim'],                          periodo['fim']),
        ('Total de hospitais',           hospitais,                               '—'),
        # 0.3 Tokens
        ('Tokens — mínimo',              tokens_presc['min'],                     tokens_par['min']),
        ('Tokens — média',               tokens_presc['media'],                   tokens_par['media']),
        ('Tokens — mediana',             tokens_presc['mediana'],                 tokens_par['mediana']),
        ('Tokens — máximo',              tokens_presc['max'],                     tokens_par['max']),
        ('Tokens — P25',                 tokens_presc['p25'],                     tokens_par['p25']),
        ('Tokens — P75',                 tokens_presc['p75'],                     tokens_par['p75']),
        # 0.3 Caracteres
        ('Caracteres — média',           caracteres_presc['media'],               caracteres_par['media']),
        ('Caracteres — mediana',         caracteres_presc['mediana'],             caracteres_par['mediana']),
        ('Caracteres — máximo',          caracteres_presc['max'],                 caracteres_par['max']),
        # 0.3 Sentenças
        ('Sentenças — média',            sentencas_presc['media'],                sentencas_par['media']),
        ('Sentenças — mediana',          sentencas_presc['mediana'],              sentencas_par['mediana']),
        # 0.4 Tipo de Texto
        ('Texto livre — qtd',            tipos_presc['texto_livre'],              tipos_par['texto_livre']),
        ('Texto livre — %',              tipos_presc['pct_texto_livre'],          tipos_par['pct_texto_livre']),
        ('Template estruturado — qtd',   tipos_presc['template_estruturado'],     tipos_par['template_estruturado']),
        ('Template estruturado — %',     tipos_presc['pct_template'],             tipos_par['pct_template']),
    ]

    df = pd.DataFrame(linhas, columns=['Característica', 'Prescrições', 'Pareceres'])
    return df
# Fim - 0) Análise Exploratória - 0.5) Geração de Saídas - 0.5.1) Tabela 1 da dissertação (CSV + Excel)

# Início - 0) Análise Exploratória - 0.5) Geração de Saídas - 0.5.2) Histograma de distribuição de tokens
def calcular_histograma_tokens(df, coluna_texto, n_bins=10):
    # Conta quantos tokens cada documento tem
    contagens = df[coluna_texto].apply(lambda texto: len(tokenizar(texto)))

    # pd.cut divide os valores em n_bins faixas (bins) de tamanho igual
    # Por exemplo: [0, 50), [50, 100), [100, 200), ...
    bins = pd.cut(contagens, bins=n_bins)

    # Conta quantos documentos caem em cada faixa
    frequencias = bins.value_counts().sort_index()

    # Retorna duas listas paralelas: os rótulos das faixas e as contagens
    return {
        'rotulos': [str(intervalo) for intervalo in frequencias.index],
        'valores': [int(v) for v in frequencias.values],
    }
# Fim - 0) Análise Exploratória - 0.5) Geração de Saídas - 0.5.2) Histograma de distribuição de tokens