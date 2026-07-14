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
    # o campo de texto para 'texto', assim os dois ficam com a mesma estrutura
    presc = df_prescricoes[['cd_paciente', 'dt_atendimento', 'ds_evolucao']].copy()
    presc = presc.rename(columns={'ds_evolucao': 'texto'})
    presc['doc_type'] = 'prescricao'

    par = df_pareceres[['cd_paciente', 'dt_atendimento', 'ds_parecer']].copy()
    par = par.rename(columns={'ds_parecer': 'texto'})
    par['doc_type'] = 'parecer'

    # Junta os dois em um único DataFrame e reseta o índice
    df = pd.concat([presc, par], ignore_index=True)
    return df
# Fim - 1) Pré-processamento - 1.1) Leitura do DataSet - 1.1.3

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
def normalizar_datas_no_texto(texto):
    if not isinstance(texto, str):
        return ''
    # Grupo 4 captura o horário opcional para preservá-lo após a conversão da data
    padrao = re.compile(r'\b(\d{1,2})/(\d{1,2})/(\d{2,4})(?:\s+(\d{2}:\d{2}))?\b')

    def substituir(match):
        p1, p2, p3 = match.group(1), match.group(2), match.group(3)
        hora = match.group(4)  # None se não houver horário
        n1, n2, n3 = int(p1), int(p2), int(p3)
        if len(p3) == 4:
            ano = n3
            if n2 > 12:
                dia, mes = n2, n1
            else:
                dia, mes = n1, n2
        else:
            ano = 2000 + n3
            dia, mes = n1, n2
        try:
            data_iso = f'{ano:04d}-{mes:02d}-{dia:02d}'
            return f'{data_iso} {hora}' if hora else data_iso
        except (ValueError, OverflowError):
            return match.group(0)

    return padrao.sub(substituir, texto)

def mascarar_datas_horas(texto):
    """
    Substitui datas ISO por __DATA__ e datetime ISO por __DATA__ __HORA__.
    Deve ser chamada DEPOIS de normalizar_datas_no_texto().
    Horas isoladas são tratadas por mascarar_horas(), chamada a seguir no pipeline.
    """
    if not isinstance(texto, str):
        return ''
    # Data+hora com segundos: "2026-08-04 07:09:30" → "__DATA__ __HORA__"
    texto = re.sub(r'\b\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\b', '__DATA__ __HORA__', texto)
    # Data+hora: "2026-08-04 07:09" → "__DATA__ __HORA__"
    texto = re.sub(r'\b\d{4}-\d{2}-\d{2} \d{2}:\d{2}\b', '__DATA__ __HORA__', texto)
    # Data isolada: "2026-08-04" → "__DATA__"
    texto = re.sub(r'\b\d{4}-\d{2}-\d{2}\b', '__DATA__', texto)
    return texto
# Fim - 1) Pré-processamento - 1.2) Normalização Textual - 1.2.4) Normalização de datas → ISO 8601

# Início - 1) Pré-processamento - 1.2) Normalização Textual - 1.2.4b) Mascaramento horas → __HORA__
def mascarar_horas(texto):
    """
    Substitui formatos de hora isolados por __HORA__.
    Deve ser chamada DEPOIS de mascarar_datas_horas() para não conflitar com
    datetime ISO (ex: "2026-08-04 07:09" já virou "__DATA__ __HORA__").

    Formatos cobertos (do mais para o menos específico):
      Grupo 1  - milissegundos: "07:09:30.123" / "07:09:30,123"
      Grupo 2  - com segundos: "07:09:30", "7:9:30"
      Grupo 3  - AM/PM: "07:30 AM", "7:30pm", "07:30 a.m.", "07:30 p.m."
      Grupo 4  - sufixo h: "14:30h", "9:30h"
      Grupo 5  - HH:MM simples: "07:09", "7:9", "07:9"
      Grupo 6  - hXXmin/s: "14h30min45", "9h30m45" (com segundos)
      Grupo 7  - hXXmin/m: "14h30min", "9h 30m", "14h 30min" (com espaco)
      Grupo 8  - hXX: "14h30", "9h05" (sem sufixo)
      Grupo 9  - Xh: "14h", "9h" (hora com h)
      Grupo 10 - "as ## horas": horario especifico por extenso

    NAO cobre (ambiguos sem contexto - risco de falso positivo clinico):
      ##.##  - confunde com decimais e dosagens (36.5C, 2.5mg)
      ##-##  - confunde com faixas de PA e laboratorio (120-80)
      ##/##  - confunde com PA (120/80), fracoes e datas parciais
      ## horas / # hora  - confunde com duracao clinica ("ha 3 horas",
                           "de 4 em 4 horas") que e informacao de utilidade
    """
    if not isinstance(texto, str):
        return ''

    # Grupo 1: milissegundos - "07:09:30.123" / "07:09:30,123"
    texto = re.sub(r'\b\d{1,2}:\d{1,2}:\d{1,2}[.,]\d{1,3}\b', '__HORA__', texto)

    # Grupo 2: com segundos - "07:09:30", "7:9:30", "07:9:30"
    texto = re.sub(r'\b\d{1,2}:\d{1,2}:\d{1,2}\b', '__HORA__', texto)

    # Grupo 3: AM/PM - "07:30 AM", "7:30PM", "07:30 a.m.", "07:30 p.m."
    texto = re.sub(
        r'\b\d{1,2}:\d{1,2}\s*(?:AM|PM|a\.m\.|p\.m\.)\b',
        '__HORA__', texto, flags=re.IGNORECASE,
    )

    # Grupo 4: sufixo h - "14:30h", "9:30h"
    texto = re.sub(r'\b\d{1,2}:\d{1,2}h\b', '__HORA__', texto, flags=re.IGNORECASE)

    # Grupo 5: HH:MM simples - "07:09", "7:9", "07:9", "7:09", "15:30HS", "__DATA__07:09"
    # Usa lookahead/lookbehind em vez de \b para capturar hora colada (15:30HS, 23:21hMOTIVO, __DATA__07:44)
    texto = re.sub(r'(?<!\d)\d{1,2}:\d{1,2}(?!\d)', '__HORA__', texto)

    # Grupo 6: com segundos e min/m - "14h30min45", "9h30m45", "14h 30min 45"
    texto = re.sub(
        r'\b\d{1,2}h\s*\d{1,2}\s*(?:min|m)\s*\d{1,2}\b',
        '__HORA__', texto, flags=re.IGNORECASE,
    )

    # Grupo 7: com min/m (com ou sem espaco) - "14h30min", "9h 30m", "14h 30min"
    texto = re.sub(
        r'\b\d{1,2}h\s*\d{1,2}\s*(?:min|m)\b',
        '__HORA__', texto, flags=re.IGNORECASE,
    )

    # Grupo 8: HHhMM - "14h30", "9h05"
    texto = re.sub(r'\b\d{1,2}h\d{1,2}\b', '__HORA__', texto, flags=re.IGNORECASE)

    # Grupo 9: HHh / Hh - "14h", "9h"
    texto = re.sub(r'\b\d{1,2}h\b', '__HORA__', texto, flags=re.IGNORECASE)

    # Grupo 10: "as ## horas" - horario especifico por extenso
    texto = re.sub(
        r'\b\xE0s\s+\d{1,2}\s+horas?\b',
        '__HORA__', texto, flags=re.IGNORECASE,
    )

    return texto
# Fim - 1) Pré-processamento - 1.2) Normalização Textual - 1.2.4b) Mascaramento horas → __HORA__

# Início - 1) Pré-processamento - 1.2) Normalização Textual - 1.2.5) Mascaramento CPF → __CPF__
def mascarar_cpf(texto):
    # O CPF é um identificador pessoal sensível, e deve ser mascarado para proteger a privacidade dos pacientes. 
    # O mascaramento não anonimiza definitivamente o CPF, mas reduz o risco de exposição acidental e protege esses padrões 
    # de serem fragmentados pela tokenização ou confundidos com outros PHI. 
    # O CPF tem três formatos observados no corpus:
    # - Formato padrão com hífen:  000.000.000-00
    # - Formato com ponto no lugar do hífen: 000.000.000.00
    # - Formato sem pontuação (11 dígitos), apenas quando precedido do rótulo "CPF"
    if not isinstance(texto, str):
        return ''
    # Formatos com pontuação: 000.000.000-00 e 000.000.000.00
    texto = re.sub(r'\b\d{3}\.\d{3}\.\d{3}[-\.]\d{2}\b', '__CPF__', texto)
    # Formato sem pontuação: apenas quando precedido do rótulo "CPF" (evita falsos positivos com CNS e prontuários)
    texto = re.sub(
        r'(?i)\bCPF\s*[:\-]?\s*(\b\d{11}\b)',
        lambda m: m.group(0).replace(m.group(1), '__CPF__'),
        texto,
    )
    return texto
# Fim - 1) Pré-processamento - 1.2) Normalização Textual - 1.2.5) Mascaramento CPF → __CPF__

# Início - 1) Pré-processamento - 1.2) Normalização Textual - 1.2.6) Mascaramento telefone → __TELEFONE__
def mascarar_telefone(texto):
    # Telefones aparecem em múltiplos formatos no texto clínico.
    # O mascaramento evita que o tokenizador fragmente o número em vários tokens
    # e protege esse PHI de ser ignorado pelo modelo NER.
    # Formatos cobertos:
    # - (27) 99999-9999          → celular com DDD formatado
    # - (27) 9999-9999           → fixo com DDD formatado
    # - (27) 999826676           → DDD entre parênteses + 9 dígitos sem hífen
    # - (27) 99706.2830          → DDD entre parênteses + número com ponto como separador
    # - (27) 99807 9300          → DDD entre parênteses + 5 dígitos + espaço + 4 dígitos
    # - 27999999999              → sem formatação, 11 dígitos
    # - 9999-9999                → fixo sem DDD
    # - 99874.5657               → número com ponto como separador, sem DDD
    #   ATENÇÃO: risco baixo de conflito com valores clínicos — exige 4 dígitos após o ponto
    # - 27 9 9722 3137           → DDD + dígito 9 + número com espaços (formato fragmentado)
    # - TEL 27 33767-7523        → prefixo TEL + DDD + número com hífen
    # - TEL 27 33767 - 7523      → prefixo TEL + DDD + número com espaços ao redor do hífen
    # - 27 992867927             → DDD + espaço + 9 dígitos sem hífen
    # - 27 99612 - 0360          → DDD + espaço + 5 dígitos + espaço + hífen + espaço + 4 dígitos
    # - 998387639                → celular sem DDD, 9 dígitos começando com 9
    #   ATENÇÃO: pode conflitar com RG de 9 dígitos — risco baixo pois RG
    #   geralmente aparece precedido do rótulo "RG" no texto clínico
    # - NETA 27 - 9.99773 - 0641 → rótulo de parentesco/contato + DDD + número com ponto como separador
    #   ATENÇÃO: o ponto é separador do sistema MV, não decimal — exige rótulo antes para não
    #   conflitar com valores clínicos numéricos

    if not isinstance(texto, str):
        return ''
    # Com DDD entre parênteses e hífen: (dd) 9999-9999 ou (dd) 99999-9999
    texto = re.sub(r'\(\d{2}\)\s*\d{4,5}\s*-\s*\d{4}', '__TELEFONE__', texto)
    # Com DDD entre parênteses e ponto como separador: (dd) 99999.9999
    # Ex: (27) 99706.2830
    texto = re.sub(r'\(\d{2}\)\s*\d{4,5}\.\d{4}', '__TELEFONE__', texto)
    # Com DDD entre parênteses + espaço entre os grupos: (dd) 99999 9999
    # Ex: (27) 99807 9300
    texto = re.sub(r'\(\d{2}\)\s*\d{4,5}\s+\d{4}', '__TELEFONE__', texto)
    # Com DDD entre parênteses sem separador: (dd) 999999999 ou (dd) 99999999
    # Ex: (27) 999826676
    texto = re.sub(r'\(\d{2}\)\s*\d{8,9}', '__TELEFONE__', texto)
    # Formato fragmentado: DDD + espaço + 9 + espaço + 4 dígitos + espaço + 4 dígitos
    # Ex: 27 9 9722 3137
    texto = re.sub(r'\b\d{2}\s+9\s+\d{4}\s+\d{4}\b', '__TELEFONE__', texto)
    # DDD + espaço + 5 dígitos + espaço + hífen + espaço + 4 dígitos
    # Ex: 27 99612 - 0360
    texto = re.sub(r'\b\d{2}\s+\d{4,5}\s+-\s+\d{4}\b', '__TELEFONE__', texto)
    # Com DDD sem parênteses e hífen: dd 9999-9999 ou dd 99999-9999
    # Ex: 27 33767-7523, 27 33767 - 7523
    texto = re.sub(r'\b\d{2}\s*\d{4,5}\s*-\s*\d{4}\b', '__TELEFONE__', texto)
    # DDD + espaço + 9 dígitos sem hífen: 27 992867927
    texto = re.sub(r'\b\d{2}\s+\d{9}\b', '__TELEFONE__', texto)
    # Sem formatação: 10 ou 11 dígitos seguidos (DDD + número)
    texto = re.sub(r'\b\d{10,11}\b', '__TELEFONE__', texto)
    # Número com ponto como separador, sem DDD: 99999.9999 ou 9999.9999
    # Ex: 99874.5657 — ponto é separador do sistema MV, não decimal
    texto = re.sub(r'\b\d{4,5}\.\d{4}\b', '__TELEFONE__', texto)
    # Celular sem DDD: 9 dígitos começando com 9 (ex: 998387639)
    texto = re.sub(r'\b9\d{8}\b', '__TELEFONE__', texto)
    # Fixo sem DDD: 9999-9999
    texto = re.sub(r'\b\d{4}\s*-\s*\d{4}\b', '__TELEFONE__', texto)
    # Formato com ponto como separador, precedido de rótulo de parentesco/contato
    # Ex: NETA 27 - 9.99773 - 0641 (ponto é separador do sistema MV, não decimal)
    texto = re.sub(
        r'(?i)(?:NETA|NETO|FILHA|FILHO|MAE|MÃE|PAI|IRMAO|IRMÃO|IRMA|IRMÃ|ESPOSO|ESPOSA'
        r'|CONJUGE|CÔNJUGE|FAMILIAR|RESPONSAVEL|RESPONSÁVEL|TEL|FONE|CELULAR|CEL|CONTATO)'
        r'\s+(\d{2}\s*-\s*\d+\.\d+\s*-\s*\d{4})',
        lambda m: m.group(0).replace(m.group(1), '__TELEFONE__'),
        texto,
    )
    return texto
# Fim - 1) Pré-processamento - 1.2) Normalização Textual - 1.2.6) Mascaramento telefone → __TELEFONE__

# Início - 1) Pré-processamento - 1.2) Normalização Textual - 1.2.7) Mascaramento CEP → __CEP__
def mascarar_cep(texto):
    # CEP identifica endereço do paciente, um PHI sensível.
    # Formatos cobertos:
    # - 12345-678  → formato padrão com hífen (mascarado sempre)
    # - 12345678   → sem hífen, apenas quando precedido de contexto de endereço
    #                (CEP, ENDEREÇO, RUA, AV, BAIRRO, etc.) para evitar falsos
    #                positivos com números de prontuário, CRM, matrícula, etc.

    if not isinstance(texto, str):
        return ''

    # Formato com hífen: 00000-000 — suficientemente específico, mascarar sempre
    texto = re.sub(r'\b\d{5}-\d{3}\b', '__CEP__', texto)

    # Formato sem hífen: 00000000 — só mascarar quando há contexto de endereço próximo
    texto = re.sub(
        r'(?i)(?:CEP|ENDERE[CÇ]O|END\.?|RUA|AV\.?|AVENIDA|BAIRRO|LOGRADOURO)'
        r'\s*[:\-]?\s*'
        r'(\b\d{8}\b)',
        lambda m: m.group(0).replace(m.group(1), '__CEP__'),
        texto
    )

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

    # Substitui datas ISO (YYYY-MM-DD) e datetime ISO por __DATA__ / __DATA__ __HORA__
    texto = mascarar_datas_horas(texto)

    # Substitui horas isoladas (todos os formatos) por __HORA__
    texto = mascarar_horas(texto)

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

# Início - 1) Pré-processamento - 1.4) Tokenização - 1.4.1) Tokenização word-level (para CRF)
def tokenizar_word_level(sentenca):
    # Tokenização simples por regex para o modelo CRF.
    # Critérios de design:
    #   - Placeholders (__CPF__, __TELEFONE__ etc.) ficam como token único
    #   - Compostos com hífen (anti-inflamatório, pós-operatório) ficam unidos
    #   - Números decimais (1,5 / 37.8) ficam unidos com sua unidade (1,5mg / 37.8°C)
    #   - Pontuação solta (vírgulas, parênteses, dois-pontos) é separada em token próprio

    padrao = re.compile(
        r'__\w+__'              # placeholders: __CPF__, __TELEFONE__, etc.
        r'|\d{4}-\d{2}-\d{2}'  # datas ISO 8601: 2026-08-04 (token único)
        r'|\d{2}:\d{2}'         # horários: 07:09 (token único)
        r'|\w+(?:[.,]\w+)*'     # palavras, decimais (1,5 / 37.8) e compostos
        r'|[^\w\s]'             # pontuação avulsa
    )
    return padrao.findall(sentenca)
# Fim - 1) Pré-processamento - 1.4) Tokenização - 1.4.1) Tokenização word-level (para CRF)

# Início - 1) Pré-processamento - 1.4) Tokenização - 1.4.2) Extração de features por token (para CRF)
def extrair_features_token(tokens, i):
    # Extração de features por token — cada token recebe um dicionário de features que o CRF usa para classificar.
    # As features capturam características léxicas e contextuais: caixa alta (nomes de pacientes/medicamentos), 
    # sufixos (indicam tipo da palavra), se é número/pontuação, se está na lista de abreviações, e os tokens 
    # vizinhos (janela de contexto ±2).

    # Gera o dicionário de features do token na posição i dentro da lista de tokens.
    # O CRF usa esses features para decidir a label BIO de cada token.
    token = tokens[i]

    features = {
        # O token em minúsculas — normaliza caixa para comparação
        'token.lower': token.lower(),

        # Sufixo de 2 e 3 caracteres — útil para detectar terminações (ex: -ção, -ite, -oma)
        'token.suffix2': token[-2:],
        'token.suffix3': token[-3:],

        # Prefixo de 2 e 3 caracteres — útil para detectar inícios (ex: anti-, pós-)
        'token.prefix2': token[:2],
        'token.prefix3': token[:3],

        # Se o token está totalmente em caixa alta (ex: DIPIRONA, ROSIANE)
        'token.isupper': token.isupper(),

        # Se o token começa com letra maiúscula (ex: João, Hospital)
        'token.istitle': token.istitle(),

        # Se o token é composto só de dígitos (ex: 120, 80)
        'token.isdigit': token.isdigit(),

        # Se o token está na lista de abreviações médicas conhecidas
        'token.is_abrev': token.rstrip('.') in ABREVIACOES_MEDICAS,

        # Se o token é um placeholder de PHI estruturado (__CPF__, __TELEFONE__, etc.)
        'token.is_placeholder': token.startswith('__') and token.endswith('__'),

        # Posição no documento: token é o primeiro da sentença?
        'token.is_first': i == 0,

        # Posição no documento: token é o último da sentença?
        'token.is_last': i == len(tokens) - 1,
    }

    # Adiciona features do token anterior (contexto esquerdo)
    if i > 0:
        prev_token = tokens[i - 1]
        features['prev.token.lower'] = prev_token.lower()
        features['prev.token.isupper'] = prev_token.isupper()
        features['prev.token.istitle'] = prev_token.istitle()
    else:
        # Marca o início de sentença com feature especial
        features['BOS'] = True  # Beginning Of Sentence

    # Adiciona features do token dois posições atrás (contexto esquerdo amplo)
    if i > 1:
        features['prev2.token.lower'] = tokens[i - 2].lower()

    # Adiciona features do token seguinte (contexto direito)
    if i < len(tokens) - 1:
        next_token = tokens[i + 1]
        features['next.token.lower'] = next_token.lower()
        features['next.token.isupper'] = next_token.isupper()
        features['next.token.istitle'] = next_token.istitle()
    else:
        # Marca o fim de sentença com feature especial
        features['EOS'] = True  # End Of Sentence

    # Adiciona features do token dois posições à frente (contexto direito amplo)
    if i < len(tokens) - 2:
        features['next2.token.lower'] = tokens[i + 2].lower()

    return features


def extrair_features_sentenca(tokens):
    # Aplica extrair_features_token para cada posição da lista de tokens.
    # Retorna uma lista de dicionários — formato esperado pelo sklearn-crfsuite.
    return [extrair_features_token(tokens, i) for i in range(len(tokens))]
# Fim - 1) Pré-processamento - 1.4) Tokenização - 1.4.2) Extração de features por token (para CRF)

# Início - 1) Pré-processamento - 1.4) Tokenização - 1.4.3) Tokenização subword + alinhamento BIO (para BERT)
def tokenizar_e_alinhar_bert(sentenca, labels_bio, tokenizer, max_length=512, stride=64):
    # Tokeniza uma sentença com o tokenizer do HuggingFace e alinha as labels BIO
    # com os subtokens gerados pelo WordPiece.
    #
    # Tokenização subword — usada pelos modelos BERT (BERTimbau, BioBERTpt, etc.).
    # O BERT usa tokenização subword (WordPiece): uma palavra como "anticoagulante" pode virar ['anti', '##coag', '##ulante']. 
    # Isso cria um problema para o formato BIO — é necessário alinhar as labels dos tokens word-level com os subword tokens, 
    # atribuindo a label correta ao primeiro subtoken e O (ou -100 para ignorar na loss) para os demais.

    # Parâmetros:
    #   sentenca    : lista de tokens word-level (saída de tokenizar_word_level)
    #   labels_bio  : lista de labels BIO alinhadas com sentenca (ex: ['O','B-PESSOA','I-PESSOA'])
    #                 Pode ser None durante inferência (não há labels ainda)
    #   tokenizer   : instância de AutoTokenizer do HuggingFace já carregada
    #   max_length  : limite de tokens do modelo (512 para BERT clássico)
    #   stride      : sobreposição entre janelas para documentos longos

    # Tokeniza com alinhamento de palavras (is_split_into_words=True)
    # truncation + stride garante que documentos > 512 tokens sejam cobertos por janelas sobrepostas
    encoding = tokenizer(
        sentenca,
        is_split_into_words=True,       # entrada já é lista de tokens word-level
        return_offsets_mapping=False,   # não precisamos dos offsets de caractere
        truncation=True,
        max_length=max_length,
        stride=stride,
        return_overflowing_tokens=True, # gera múltiplas janelas se o texto for longo
        padding='max_length',           # preenche com [PAD] até max_length
        return_tensors=None,            # retorna listas Python, não tensores
    )

    # Para cada janela gerada (chunk), alinha as labels com os subtokens
    todas_labels = []
    for chunk_idx in range(len(encoding['input_ids'])):
        # word_ids() mapeia cada subtoken ao índice do token word-level original
        # Retorna None para tokens especiais ([CLS], [SEP], [PAD])
        word_ids = encoding.word_ids(batch_index=chunk_idx)

        labels_alinhadas = []
        palavra_anterior = None
        for word_id in word_ids:
            if word_id is None:
                # Token especial ([CLS], [SEP], [PAD]) → -100 é ignorado na loss
                labels_alinhadas.append(-100)
            elif word_id != palavra_anterior:
                # Primeiro subtoken da palavra → recebe a label real
                if labels_bio is not None:
                    labels_alinhadas.append(labels_bio[word_id])
                else:
                    labels_alinhadas.append(None)  # modo inferência: sem label
                palavra_anterior = word_id
            else:
                # Subtoken continuação (##algo) → -100 para ignorar na loss
                labels_alinhadas.append(-100)

        todas_labels.append(labels_alinhadas)

    return encoding, todas_labels
# Fim - 1) Pré-processamento - 1.4) Tokenização - 1.4.3) Tokenização subword + alinhamento BIO (para BERT)

# Início - 1) Pré-processamento - 1.5) Exportação do Corpus Pré-processado - 1.5.1) Exportação CoNLL
def exportar_conll(lista_sentencas_tokens, caminho_saida):
    # Exporta o corpus tokenizado no formato CoNLL para anotação no Doccano.
    # Cada linha: token\tO  (label inicial O — sem entidade)
    # Sentenças separadas por linha em branco.
    #
    # lista_sentencas_tokens: lista de listas de tokens
    #   ex: [['Paciente', 'João', 'Silva', ',', '45', 'anos'], ['PA', ':', '120x80']]

    with open(caminho_saida, 'w', encoding='utf-8') as f:
        for tokens in lista_sentencas_tokens:
            for token in tokens:
                # Escreve token e label padrão O (Outside — nenhuma entidade)
                f.write(f'{token}\tO\n')
            # Linha em branco separa sentenças (padrão CoNLL)
            f.write('\n')
# Fim - 1) Pré-processamento - 1.5) Exportação do Corpus Pré-processado - 1.5.1) Exportação CoNLL

# Início - 1) Pré-processamento - 1.5) Exportação do Corpus Pré-processado - 1.5.2) Exportação JSONL
def exportar_jsonl(lista_documentos, caminho_saida):
    # Exportação do Corpus Pré-processado — dois formatos de saída. Dois destinos:
    #   - CoNLL → cada linha é token\tO (tab separado), sentenças separadas por linha em branco. 
    #     Formato padrão para importar no Doccano e anotar manualmente.
    #
    #   - JSONL → cada linha é um JSON {doc_id, doc_type, tokens, labels}. 
    #     Formato usado para treinar os modelos BERT diretamente.

    # Exporta o corpus no formato JSONL para treinamento dos modelos BERT.
    # Cada linha do arquivo é um JSON com os campos:
    #   doc_id   : identificador único do documento
    #   doc_type : 'prescricao' ou 'parecer'
    #   tokens   : lista de tokens word-level da sentença
    #   labels   : lista de labels BIO alinhadas (mesmo comprimento de tokens)
    #              Inicialmente preenchida com 'O' — será substituída após anotação
    #
    # lista_documentos: lista de dicts com chaves doc_id, doc_type, sentencas_tokens
    #   ex: [{'doc_id': 0, 'doc_type': 'prescricao', 'sentencas_tokens': [['Paciente', ...], ...]}]

    import json

    with open(caminho_saida, 'w', encoding='utf-8') as f:
        for doc in lista_documentos:
            for sentenca_tokens in doc['sentencas_tokens']:
                registro = {
                    'doc_id':   doc['doc_id'],
                    'doc_type': doc['doc_type'],
                    'tokens':   sentenca_tokens,
                    # Labels inicialmente todas O — serão atualizadas após anotação no Doccano
                    'labels':   ['O'] * len(sentenca_tokens),
                }
                # ensure_ascii=False preserva acentos no arquivo de saída
                f.write(json.dumps(registro, ensure_ascii=False) + '\n')
# Fim - 1) Pré-processamento - 1.5) Exportação do Corpus Pré-processado - 1.5.2) Exportação JSONL

# Início - 1) Pré-processamento - 1.5) Exportação - 1.5.3) Seleção Estratificada por PHI
def selecionar_estratificado_por_phi(caminho_jsonl, caminho_saida, cotas_por_entidade=None, n_total=None):
    # Lê o corpus.jsonl completo, classifica cada sentença pelos tipos de PHI
    # que provavelmente contém (via regex) e gera um subconjunto balanceado
    # para anotação — corpus_anotacao.jsonl.
    #
    # cotas_por_entidade: dict com a quantidade mínima desejada por tipo de PHI.
    #   Ex: {'CONTATO': 300, 'DOCUMENTO': 300, 'ENDERECO': 300,
    #        'PESSOA': 300, 'INSTITUICAO': 300, 'DATA': 200, 'HORA': 100}
    # Uma sentença pode cobrir múltiplas cotas simultaneamente.
    #
    # n_total: se informado, preenche o restante (após atingir as cotas PHI)
    #   com sentenças aleatórias do corpus até atingir esse total.
    #   Ex: n_total=5000 → ~1800 PHI-estratificadas + ~3200 aleatórias.

    import json
    import random

    if cotas_por_entidade is None:
        cotas_por_entidade = {
            'CONTATO':     300,
            'DOCUMENTO':   300,
            'ENDERECO':    300,
            'PESSOA':      300,
            'INSTITUICAO': 300,
            'DATA':        200,
            'HORA':        100,
        }

    # Regex para detectar PHI provável em texto reconstruído dos tokens.
    # Nota: o texto já passou pela normalização — datas estão em ISO 8601,
    # telefones/CPF/CEP/e-mail já estão como placeholders (__TELEFONE__ etc.)
    detectores = {
        'CONTATO':    re.compile(
            r'__TELEFONE__|__EMAIL__', re.IGNORECASE
        ),
        'DOCUMENTO':  re.compile(
            # RG: padrões como 1.234.567, 1.234.567-8 ou MG-12.345.678
            r'\b[A-Z]{0,2}\d{1,2}[\.\-]\d{3}[\.\-]\d{3}[\-\.]?\w{0,2}\b'
            # CNS: 15 dígitos seguidos
            r'|\b\d{15}\b'
            # CNH: padrão numérico de 11 dígitos (distinto de CPF por contexto)
            r'|CNH|RG\s*:?\s*\d|CNS\s*:?\s*\d'
        ),
        'ENDERECO':   re.compile(
            r'\b(RUA|AV\.?|AVENIDA|BAIRRO|TRAVESSA|ALAMEDA|RODOVIA|ESTRADA'
            r'|VILA|DISTRITO|LOTEAMENTO)\b'
            r'|__CEP__|[Nn][°º]\.?\s*\d+',
            re.IGNORECASE
        ),
        'PESSOA':     re.compile(
            # Títulos médicos/pessoais seguidos de nome
            r'\b(DR\.?|DRA\.?|SR\.?|SRA\.?|PACIENTE|PT\.?|FAMILIAR|RESPONSAVEL'
            r'|ACOMPANHANTE|FILHO|FILHA|ESPOSO|ESPOSA|MAE|PAI)\b'
            # Sequência de 2+ palavras totalmente em maiúsculas (nomes em caixa alta)
            r'|(?<!\w)[A-ZÁÉÍÓÚÂÊÎÔÛÃÕÀÇ]{3,}(?:\s+[A-ZÁÉÍÓÚÂÊÎÔÛÃÕÀÇ]{2,}){1,}',
            re.IGNORECASE
        ),
        'INSTITUICAO': re.compile(
            r'\b(HOSPITAL|UPA|UPINHA|CLINICA|CLÍNICA|SANTA\s+CASA|UBS|CAPS'
            r'|PRONTO.SOCORRO|MATERNIDADE|HEMOCENTRO|SAMU|CACON|HINSG|HESVV'
            r'|HUCAM|HMRP|HMS|HRAS)\b',
            re.IGNORECASE
        ),
        'DATA':       re.compile(
            # Datas normalizadas para ISO 8601: YYYY-MM-DD
            r'\b\d{4}-\d{2}-\d{2}\b'
        ),
        'HORA':       re.compile(
            r'\b\d{2}:\d{2}\b'
        ),
    }

    # Lê todas as sentenças do JSONL e classifica por PHI
    registros = []
    with open(caminho_jsonl, encoding='utf-8') as f:
        for linha in f:
            registro = json.loads(linha)
            texto = ' '.join(registro['tokens'])
            phi_detectados = set()
            for tipo, regex in detectores.items():
                if regex.search(texto):
                    phi_detectados.add(tipo)
            registro['_phi_detectados'] = list(phi_detectados)
            registros.append(registro)

    # Remove duplicatas por conteúdo de texto — sentenças idênticas em doc_ids
    # diferentes são comuns no corpus clínico (templates repetidos entre documentos)
    vistos = set()
    registros_unicos = []
    for r in registros:
        texto = ' '.join(r['tokens'])
        if texto not in vistos:
            vistos.add(texto)
            registros_unicos.append(r)
    registros = registros_unicos

    # Entidades tratadas integralmente por regex no normalizador — não são alvo do NER.
    # Aparecem no relatório mas com badge "Tratado por Regex" em vez de "Insuficiente".
    ENTIDADES_REGEX = {'DATA', 'HORA', 'CONTATO'}

    # Amostragem estratificada: para cada entidade, coleta até a cota mínima.
    # Registra também quantos candidatos foram encontrados para alertar
    # quando o corpus não tem sentenças suficientes para uma entidade.
    selecionados_ids = set()
    relatorio_cotas = {}
    random.seed(42)

    for entidade, cota in cotas_por_entidade.items():
        candidatos = [
            i for i, r in enumerate(registros)
            if entidade in r['_phi_detectados']
        ]
        random.shuffle(candidatos)
        selecionados_entidade = candidatos[:cota]
        for i in selecionados_entidade:
            selecionados_ids.add(i)

        relatorio_cotas[entidade] = {
            'candidatos':    len(candidatos),
            'cota':          cota,
            'selecionadas':  len(selecionados_entidade),
            'cota_atingida': len(candidatos) >= cota,
            'regex_tratado': entidade in ENTIDADES_REGEX,
        }

    # Se n_total informado, preenche o restante com sentenças aleatórias
    # que ainda não foram selecionadas (independentemente de ter PHI ou não)
    if n_total and len(selecionados_ids) < n_total:
        restantes = [i for i in range(len(registros)) if i not in selecionados_ids]
        random.shuffle(restantes)
        faltam = n_total - len(selecionados_ids)
        for i in restantes[:faltam]:
            selecionados_ids.add(i)

    # Exporta o subconjunto balanceado (sem o campo auxiliar _phi_detectados)
    selecionados = [registros[i] for i in sorted(selecionados_ids)]
    random.shuffle(selecionados)

    with open(caminho_saida, 'w', encoding='utf-8') as f:
        for registro in selecionados:
            registro.pop('_phi_detectados', None)
            f.write(json.dumps(registro, ensure_ascii=False) + '\n')

    # Monta resumo da distribuição de PHI no corpus gerado
    resumo_phi = {entidade: 0 for entidade in cotas_por_entidade}
    for registro in selecionados:
        texto = ' '.join(registro['tokens'])
        for entidade, regex in detectores.items():
            if regex.search(texto):
                resumo_phi[entidade] += 1

    return {
        'total_selecionadas': len(selecionados),
        'caminho_saida':      caminho_saida,
        'distribuicao_phi':   resumo_phi,
        'relatorio_cotas':    relatorio_cotas,
    }
# Fim - 1) Pré-processamento - 1.5) Exportação - 1.5.3) Seleção Estratificada por PHI

# Início - 1) Pré-processamento - Pipeline completo
def executar_preprocessamento(arquivo_prescricoes, arquivo_pareceres,
                               caminho_conll, caminho_jsonl, amostra=None, n_total_anotacao=None):
    # Orquestra todas as etapas do pré-processamento sobre os dois arquivos CSV.
    # Parâmetros:
    #   arquivo_prescricoes   : caminho ou objeto de arquivo do CSV de prescrições
    #   arquivo_pareceres     : caminho ou objeto de arquivo do CSV de pareceres
    #   caminho_conll         : caminho do arquivo .conll de saída
    #   caminho_jsonl         : caminho do arquivo .jsonl de saída (corpus completo)
    #   amostra               : se informado, limita registros por tipo (dev)
    #   n_total_anotacao      : total de sentenças para corpus_anotacao.jsonl
    #                           (PHI-estratificadas + complemento aleatório)

    # 1.1 — Leitura e seleção de colunas
    df_prescricoes = ler_prescricoes(arquivo_prescricoes)
    df_pareceres   = ler_pareceres(arquivo_pareceres)
    df = selecionar_colunas(df_prescricoes, df_pareceres)

    # Aplica amostragem se solicitado (útil no desenvolvimento com 1.000+1.000)
    if amostra:
        presc = df[df['doc_type'] == 'prescricao'].sample(
            min(amostra, (df['doc_type'] == 'prescricao').sum()), random_state=42
        )
        par = df[df['doc_type'] == 'parecer'].sample(
            min(amostra, (df['doc_type'] == 'parecer').sum()), random_state=42
        )
        df = pd.concat([presc, par], ignore_index=True)

    # 1.2 + 1.3 + 1.4 — Normaliza, segmenta e tokeniza cada documento
    lista_sentencas_tokens = []  # para exportar CoNLL (lista plana de sentenças)
    lista_documentos = []        # para exportar JSONL (agrupado por documento)

    for idx, linha in df.iterrows():
        # 1.2 — Normalização textual
        texto_normalizado = normalizar_texto(linha['texto'])

        # 1.3 — Segmentação em sentenças
        sentencas = segmentar_documento(texto_normalizado)

        # 1.4.1 — Tokenização word-level de cada sentença
        sentencas_tokens = [tokenizar_word_level(s) for s in sentencas]

        # Descarta sentenças que ficaram vazias após tokenização
        sentencas_tokens = [t for t in sentencas_tokens if t]

        # Acumula para exportação CoNLL (todas as sentenças de todos os docs)
        lista_sentencas_tokens.extend(sentencas_tokens)

        # Acumula para exportação JSONL (um registro por documento com todas as sentenças)
        lista_documentos.append({
            'doc_id':          idx,
            'doc_type':        linha['doc_type'],
            'sentencas_tokens': sentencas_tokens,
        })

    # 1.5.1 — Exporta corpus completo no formato CoNLL (para Doccano)
    exportar_conll(lista_sentencas_tokens, caminho_conll)

    # 1.5.2 — Exporta corpus completo no formato JSONL (para BERT)
    exportar_jsonl(lista_documentos, caminho_jsonl)

    # 1.5.3 — Gera corpus_anotacao.jsonl com seleção estratificada por PHI
    caminho_anotacao = caminho_jsonl.replace('corpus.jsonl', 'corpus_anotacao.jsonl')
    selecao_phi = selecionar_estratificado_por_phi(
        caminho_jsonl=caminho_jsonl,
        caminho_saida=caminho_anotacao,
        n_total=n_total_anotacao,
    )

    total_sentencas = sum(len(doc['sentencas_tokens']) for doc in lista_documentos)

    return {
        'total_documentos':    len(df),
        'total_sentencas':     total_sentencas,
        'total_prescricoes':   int((df['doc_type'] == 'prescricao').sum()),
        'total_pareceres':     int((df['doc_type'] == 'parecer').sum()),
        'caminho_conll':       caminho_conll,
        'caminho_jsonl':       caminho_jsonl,
        'caminho_anotacao':    caminho_anotacao,
        'selecao_phi':         selecao_phi,
    }
# Fim - 1) Pré-processamento - Pipeline completo
