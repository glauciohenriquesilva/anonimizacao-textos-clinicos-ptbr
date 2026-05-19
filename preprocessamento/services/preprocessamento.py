import re
import unicodedata
import pandas as pd

from analise_exploratoria.services.exploracao import (
    ler_prescricoes, 
    ler_pareceres,
    classificar_tipo_texto
)

# Início - 1) Pré-processamento - 1.1) Leitura do DataSet - 1.1.3) Seleção das colunas-alvo
def selecionar_colunas(df_prescricoes, df_pareceres):
    # Seleciona apenas as colunas necessárias de cada DataFrame e renomeia
    # o campo de texto para 'texto' e o campo de data do documento para 'dt_documento',
    # assim os dois DataFrames ficam com a mesma estrutura e podem ser concatenados
    presc = df_prescricoes[['cd_paciente', 'dt_atendimento', 'dt_pre_med', 'ds_evolucao']].copy()
    presc = presc.rename(columns={'dt_pre_med': 'dt_documento', 'ds_evolucao': 'texto'})
    presc['doc_type'] = 'prescricao'

    par = df_pareceres[['cd_paciente', 'dt_atendimento', 'dt_parecer', 'ds_parecer']].copy()
    par = par.rename(columns={'dt_parecer': 'dt_documento', 'ds_parecer': 'texto'})
    par['doc_type'] = 'parecer'

    # Junta os dois em um único DataFrame e reseta o índice
    df = pd.concat([presc, par], ignore_index=True)
    return df
# Fim - 1) Pré-processamento - 1.1) Leitura do DataSet - 1.1.3) Seleção das colunas-alvo

# Início - 1) Pré-processamento - 1.2) Normalização Textual - 1.2.1) Normalização Unicode NFC
def normalizar_unicode(texto):
    # Normaliza o texto usando a forma de normalização Unicode NFC (Normalization Form C)
    # A normalização Unicode é um processo que transforma caracteres acentuados e outros caracteres especiais em uma forma canônica, 
    # garantindo que diferentes representações de um mesmo caractere sejam tratadas como iguais. A forma NFC é uma das formas de 
    # normalização que combina caracteres acentuados em um único caractere composto, o que é útil para garantir a consistência dos dados textuais.

    if not isinstance(texto, str):
        return ''
    return unicodedata.normalize('NFC', texto)
# Fim - 1) Pré-processamento - 1.2) Normalização Textual - 1.2.1) Normalização Unicode NFC

# Início - 1) Pré-processamento - 1.2) Normalização Textual - 1.2.2) Remoção de caracteres de controle
def remover_caracteres_controle(texto):
    # Caracteres de controle são caracteres invisíveis herdados de sistemas antigos: \r (carriage return do Windows), \x00 (null byte), 
    # \x0b (vertical tab), \x0c (form feed), entre outros. O sistema MV, sendo um sistema hospitalar legado, frequentemente os embute nos 
    # textos exportados. Eles não aparecem na tela mas quebram regex, tokenização e até a leitura do CSV em alguns casos.

    if not isinstance(texto, str):
        return ''
    # Mantém \n (nova linha) pois é estruturalmente importante nos templates
    # Remove todos os outros caracteres de controle (categoria Unicode 'Cc')
    return ''.join(
        ch for ch in texto
        if ch == '\n' or not unicodedata.category(ch).startswith('C')
    )
# Fim - 1) Pré-processamento - 1.2) Normalização Textual - 1.2.2) Remoção de caracteres de controle

# Início - 1) Pré-processamento - 1.2) Normalização Textual - 1.2.3) Colapso de espaços múltiplos e tabs
def colapsar_espacos(texto):
    # Textos clínicos frequentemente têm espaços extras, tabs e combinações de espaços+tabs usados para alinhar visualmente campos nos 
    # templates. Para o pipeline de NER isso é ruído — um token não deve ser "" (string vazia) por causa de espaço duplo.
    
    if not isinstance(texto, str):
        return ''
    # Substitui tabs por espaço simples
    texto = texto.replace('\t', ' ')
    # Colapsa múltiplos espaços em um único, mas preserva \n
    linhas = texto.split('\n')
    linhas = [re.sub(r' {2,}', ' ', linha).strip() for linha in linhas]
    return '\n'.join(linhas)
# Fim - 1) Pré-processamento - 1.2) Normalização Textual - 1.2.3) Colapso de espaços múltiplos e tabs

# Início - 1) Pré-processamento - 1.2) Normalização Textual - 1.2.4) Normalização de datas → ISO 8601
def normalizar_data(match):
    """Recebe um match de regex e retorna a data no formato ISO 8601 (YYYY-MM-DD)."""
    p1, p2, p3 = match.group(1), match.group(2), match.group(3)
    n1, n2, n3 = int(p1), int(p2), int(p3)

    # Detecta o ano: campo com 4 dígitos ou campo com 2 dígitos (adiciona 2000)
    if len(p3) == 4:
        ano = n3
        # Distingue dd/mm vs m/dd: se n2 > 12, é dia (formato americano m/dd/yyyy)
        if n2 > 12:
            dia, mes = n2, n1   # formato americano: m/dd/yyyy
        else:
            dia, mes = n1, n2   # formato brasileiro: dd/mm/yyyy
    else:
        # Formato dd/mm/yy
        ano = 2000 + n3
        dia, mes = n1, n2

    try:
        return f'{ano:04d}-{mes:02d}-{dia:02d}'
    except ValueError:
        return match.group(0)  # se a data for inválida, mantém o original

def normalizar_datas_no_texto(texto):
    if not isinstance(texto, str):
        return ''
    # Regex captura datas no formato d+/d+/dd ou d+/d+/dddd, com ou sem horário
    padrao = re.compile(r'\b(\d{1,2})/(\d{1,2})/(\d{2,4})(?:\s+\d{2}:\d{2})?\b')
    return padrao.sub(normalizar_data, texto)
# Fim - 1) Pré-processamento - 1.2) Normalização Textual - 1.2.4) Normalização de datas → ISO 8601

# Início - 1) Pré-processamento - 1.2) Normalização Textual - 1.2.5) Mascaramento CPF → __CPF__
def mascarar_cpf(texto):
    # O CPF é um identificador pessoal sensível, e deve ser mascarado para proteger a privacidade dos pacientes. 
    # O mascaramento não anonimiza definitivamente o CPF, mas reduz o risco de exposição acidental e protege esses padrões 
    # de serem fragmentados pela tokenização ou confundidos com outros PHI. 
    # O formato do CPF é bem definido, o que facilita a identificação e substituição por um token genérico como __CPF__.
    # O CPF tem dois formatos comuns:
    # - Formato com pontuação: 000.000.000-00
    # - Formato sem pontuação: 11 dígitos seguidos (evita falsos positivos com números menores)

    if not isinstance(texto, str):
        return ''
    # Formato com pontuação: 000.000.000-00
    texto = re.sub(r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b', '__CPF__', texto)
    # Formato sem pontuação: 11 dígitos seguidos (evita falsos positivos com números menores)
    texto = re.sub(r'\b\d{11}\b', '__CPF__', texto)
    return texto
# Fim - 1) Pré-processamento - 1.2) Normalização Textual - 1.2.5) Mascaramento CPF → __CPF__

# Início - 1) Pré-processamento - 1.2) Normalização Textual - 1.2.6) Mascaramento telefone → __TELEFONE__
def mascarar_telefone(texto):
    # Telefones aparecem em múltiplos formatos no texto clínico.
    # O mascaramento evita que o tokenizador fragmente o número em vários tokens
    # e protege esse PHI de ser ignorado pelo modelo NER.
    # Formatos cobertos:
    # - (27) 99999-9999  → celular com DDD formatado
    # - (27) 9999-9999   → fixo com DDD formatado
    # - 27999999999      → sem formatação, 11 dígitos
    # - 9999-9999        → fixo sem DDD

    if not isinstance(texto, str):
        return ''
    # Com DDD entre parênteses: (dd) 9999-9999 ou (dd) 99999-9999
    texto = re.sub(r'\(\d{2}\)\s*\d{4,5}-\d{4}', '__TELEFONE__', texto)
    # Com DDD sem parênteses: dd9999-9999 ou dd99999-9999
    texto = re.sub(r'\b\d{2}\s*\d{4,5}-\d{4}\b', '__TELEFONE__', texto)
    # Sem formatação: 10 ou 11 dígitos seguidos (DDD + número)
    texto = re.sub(r'\b\d{10,11}\b', '__TELEFONE__', texto)
    # Fixo sem DDD: 9999-9999
    texto = re.sub(r'\b\d{4}-\d{4}\b', '__TELEFONE__', texto)
    return texto
# Fim - 1) Pré-processamento - 1.2) Normalização Textual - 1.2.6) Mascaramento telefone → __TELEFONE__

# Início - 1) Pré-processamento - 1.2) Normalização Textual - 1.2.7) Mascaramento CEP → __CEP__
def mascarar_cep(texto):
    # CEP identifica endereço do paciente, um PHI sensível.
    # Formatos cobertos:
    # - 12345-678  → formato padrão com hífen
    # - 12345678   → sem hífen (comum em formulários digitais)
    # O \b evita falsos positivos dentro de números maiores.

    if not isinstance(texto, str):
        return ''
    # Formato com hífen: 00000-000
    texto = re.sub(r'\b\d{5}-\d{3}\b', '__CEP__', texto)
    # Formato sem hífen: 00000000 (8 dígitos exatos)
    texto = re.sub(r'\b\d{8}\b', '__CEP__', texto)
    return texto
# Fim - 1) Pré-processamento - 1.2) Normalização Textual - 1.2.7) Mascaramento CEP → __CEP__

# Início - 1) Pré-processamento - 1.2) Normalização Textual - 1.2.8) Mascaramento e-mail → __EMAIL__
def mascarar_email(texto):
    # E-mail é PHI direto — identifica o paciente ou familiar.
    # A regex cobre o formato padrão: usuario@dominio.extensao
    # Não tenta cobrir todos os casos da RFC 5322 — apenas os formatos
    # realistas que aparecem em texto clínico digitado por humanos.

    if not isinstance(texto, str):
        return ''
    texto = re.sub(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', '__EMAIL__', texto)
    return texto
# Fim - 1) Pré-processamento - 1.2) Normalização Textual - 1.2.8) Mascaramento e-mail → __EMAIL__

# Início - 1) Pré-processamento - 1.2) Normalização Textual - Pipeline completo
def normalizar_texto(texto):
    # Aplica todas as normalizações em sequência sobre um texto clínico bruto.
    # A ordem é intencional: limpeza de base → estrutura → padrões numéricos → padrões alfanuméricos.

    # Garante que todos os caracteres acentuados estejam na forma composta (1 caractere por acento)
    texto = normalizar_unicode(texto)

    # Remove caracteres invisíveis de controle (ex: \r, \x00) preservando \n (estrutura dos templates)
    texto = remover_caracteres_controle(texto)

    # Substitui tabs por espaço e colapsa múltiplos espaços em um único, linha a linha
    texto = colapsar_espacos(texto)

    # Detecta datas nos 4 formatos encontrados no dataset e converte para ISO 8601 (YYYY-MM-DD)
    texto = normalizar_datas_no_texto(texto)

    # Substitui CPF (com ou sem pontuação) por __CPF__
    texto = mascarar_cpf(texto)

    # Substitui telefones (com/sem DDD, com/sem formatação) por __TELEFONE__
    texto = mascarar_telefone(texto)

    # Substitui CEP (com ou sem hífen) por __CEP__
    texto = mascarar_cep(texto)

    # Substitui endereços de e-mail por __EMAIL__
    texto = mascarar_email(texto)

    return texto
# Fim - 1) Pré-processamento - 1.2) Normalização Textual - Pipeline completo

# Início - 1) Pré-processamento - 1.3) Segmentação em Sentenças - 1.3.2) Proteção de abreviações médicas
ABREVIACOES_MEDICAS = [
    'Dr', 'Dra', 'Prof', 'Sr', 'Sra',
    'LPP', 'SVD', 'AVP', 'SNE', 'SNG', 'BIC', 'BH', 'HTX', 'NPT',
    'TOT', 'TQT', 'GTT', 'VNI', 'UTI', 'PA', 'FC', 'FR', 'TAX', 'SAT',
    'CN', 'VM', 'ABD', 'RH', 'SIC', 'HDA', 'HPP', 'MID',
]

def proteger_abreviacoes(texto):
    # Substitui o ponto de cada abreviação médica conhecida por § para que o
    # segmentador não interprete a abreviação como fim de sentença.
    # Exemplo: "FC. 88bpm" → "FC§ 88bpm" → após segmentação → "FC. 88bpm"
    for abrev in ABREVIACOES_MEDICAS:
        # \b garante que só casa a palavra exata, não prefixos de palavras maiores
        texto = re.sub(rf'\b{abrev}\.', f'{abrev}§', texto)
    return texto

def restaurar_abreviacoes(texto):
    # Restaura o § de volta para ponto após a segmentação
    return texto.replace('§', '.')
# Fim - 1) Pré-processamento - 1.3) Segmentação em Sentenças - 1.3.2) Proteção de abreviações médicas

# Início - 1) Pré-processamento - 1.3) Segmentação em Sentenças - 1.3.3) Segmentação por pontuação (texto livre)
def segmentar_texto_livre(texto):
    # Divide o texto por pontuação de fim de sentença: . ! ?
    # O lookbehind (?<=[.!?]) mantém o delimitador na sentença anterior.
    # Exemplo: "Paciente estável. Prescrito repouso." → ["Paciente estável.", "Prescrito repouso."]
    sentencas = re.split(r'(?<=[.!?])\s+', texto)
    return [s.strip() for s in sentencas if s.strip()]
# Fim - 1) Pré-processamento - 1.3) Segmentação em Sentenças - 1.3.3) Segmentação por pontuação (texto livre)

# Início - 1) Pré-processamento - 1.3) Segmentação em Sentenças - 1.3.4) Segmentação por linha/campo (template)
def segmentar_template(texto):
    # Em templates estruturados cada linha é um campo independente.
    # Divide por \n e descarta linhas vazias.
    # Exemplo: "SINAIS VITAIS:\nPA: 120x80\nFC: 88bpm" → ["SINAIS VITAIS:", "PA: 120x80", "FC: 88bpm"]
    linhas = texto.split('\n')
    return [linha.strip() for linha in linhas if linha.strip()]
# Fim - 1) Pré-processamento - 1.3) Segmentação em Sentenças - 1.3.4) Segmentação por linha/campo (template)

# Início - 1) Pré-processamento - 1.3) Segmentação em Sentenças - 1.3.5) Filtro de sentenças muito curtas
def filtrar_sentencas_curtas(sentencas, min_tokens=3):
    # Remove sentenças com menos de min_tokens tokens (padrão: 3).
    # Sentenças muito curtas não têm contexto suficiente para NER e geram ruído no treinamento.
    # Exemplo removido: ["(  )", "---", "PA:"] → descartados
    # Exemplo mantido: ["PA: 120x80 mmHg"] → mantido (3 tokens)
    return [s for s in sentencas if len(s.split()) >= min_tokens]
# Fim - 1) Pré-processamento - 1.3) Segmentação em Sentenças - 1.3.5) Filtro de sentenças muito curtas

# Início - 1) Pré-processamento - 1.3) Segmentação em Sentenças - Pipeline completo
def segmentar_documento(texto):
    # Orquestra a segmentação completa de um documento clínico.
    # Detecta o tipo de texto e aplica a estratégia adequada.

    # Detecta se é texto livre ou template estruturado
    tipo = classificar_tipo_texto(texto)

    # Protege abreviações médicas antes de segmentar (evita falsos fins de sentença)
    texto_protegido = proteger_abreviacoes(texto)

    # Aplica a segmentação adequada ao tipo de texto
    if tipo == 'template_estruturado':
        sentencas = segmentar_template(texto_protegido)
    else:
        sentencas = segmentar_texto_livre(texto_protegido)

    # Restaura os pontos das abreviações que foram temporariamente substituídos
    sentencas = [restaurar_abreviacoes(s) for s in sentencas]

    # Remove sentenças com menos de 3 tokens
    sentencas = filtrar_sentencas_curtas(sentencas)

    return sentencas
# Fim - 1) Pré-processamento - 1.3) Segmentação em Sentenças - Pipeline completo