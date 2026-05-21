import re
import hashlib
import os
from Levenshtein import ratio as levenshtein_ratio

# Início - 3) Anonimização - 3.1) Substituição por Marcadores - 3.1.1) Extração dos spans PHI
def extrair_spans_phi(tokens, labels):
    # Extrai os spans PHI a partir das listas de tokens e labels BIO.
    # Retorna lista de dicts com início, fim (índices de token) e tipo da entidade.
    # Exemplo: [{'inicio': 2, 'fim': 4, 'tipo': 'PESSOA', 'texto': 'João Silva'}]

    spans = []
    i = 0
    while i < len(labels):
        if labels[i].startswith('B-'):
            tipo  = labels[i][2:]  # extrai o tipo: B-PESSOA → PESSOA
            inicio = i
            j = i + 1
            # Avança enquanto houver continuação I- da mesma entidade
            while j < len(labels) and labels[j] == f'I-{tipo}':
                j += 1
            texto = ' '.join(tokens[inicio:j])
            spans.append({'inicio': inicio, 'fim': j, 'tipo': tipo, 'texto': texto})
            i = j
        else:
            i += 1
    return spans
# Fim - 3) Anonimização - 3.1) Substituição por Marcadores - 3.1.1) Extração dos spans PHI


# Início - 3) Anonimização - 3.1) Substituição por Marcadores - 3.1.2) Ordenação reversa dos spans
def ordenar_spans_reverso(spans):
    # Ordena os spans do fim para o início do texto.
    # Isso garante que ao substituir um span, os índices dos spans anteriores
    # não sejam deslocados — substituição de trás para frente é a estratégia segura.
    return sorted(spans, key=lambda s: s['inicio'], reverse=True)
# Fim - 3) Anonimização - 3.1) Substituição por Marcadores - 3.1.2) Ordenação reversa dos spans


# Início - 3) Anonimização - 3.1) Substituição por Marcadores - 3.1.3) Substituição consistente
def substituir_spans(tokens, spans_ordenados):
    # Substitui cada span PHI pelo marcador [TIPO_N], onde N é um contador por tipo.
    # A mesma entidade (mesmo texto) sempre recebe o mesmo marcador — consistência
    # dentro do documento (ex: "João Silva" → sempre [PESSOA_1]).
    #
    # Retorna:
    #   tokens_anonimizados : lista de tokens com PHI substituído
    #   mapeamento          : dict texto_original → marcador usado

    tokens_result = list(tokens)  # cópia para não alterar o original
    contadores    = {}            # tipo → contador sequencial
    mapeamento    = {}            # texto → marcador (para consistência)

    for span in spans_ordenados:
        texto = span['texto']
        tipo  = span['tipo']

        # Reutiliza o marcador se a mesma entidade já apareceu no documento
        if texto not in mapeamento:
            contadores[tipo] = contadores.get(tipo, 0) + 1
            mapeamento[texto] = f'[{tipo}_{contadores[tipo]}]'

        marcador = mapeamento[texto]

        # Substitui os tokens do span pelo marcador e remove os demais
        tokens_result[span['inicio']] = marcador
        for k in range(span['inicio'] + 1, span['fim']):
            tokens_result[k] = None  # tokens continuação marcados para remoção

    # Remove os tokens marcados como None (continuações substituídas)
    tokens_result = [t for t in tokens_result if t is not None]
    return tokens_result, mapeamento
# Fim - 3) Anonimização - 3.1) Substituição por Marcadores - 3.1.3) Substituição consistente


# Início - 3) Anonimização - 3.1) Substituição por Marcadores - 3.1.4) Pseudonimização cd_paciente → SHA-256
def pseudonimizar_paciente(cd_paciente):
    # Substitui o identificador do paciente por um hash SHA-256 com salt.
    # O salt é lido do arquivo .env para garantir que o hash seja reproduzível
    # mas não reversível sem o salt.
    salt = os.environ.get('ANON_SALT', 'anonclin_default_salt')
    valor = f'{salt}{cd_paciente}'.encode('utf-8')
    return hashlib.sha256(valor).hexdigest()
# Fim - 3) Anonimização - 3.1) Substituição por Marcadores - 3.1.4) Pseudonimização cd_paciente → SHA-256


# Início - 3) Anonimização - 3.2) Avaliação de Privacidade — Dimensão L do TILD - 3.2.1) Coverage
def calcular_coverage(spans_gold, spans_pred):
    # Coverage = Recall de PHI anonimizado = TP / (TP + FN)
    # Mede quantos spans PHI reais foram de fato anonimizados.
    # Um FN é um span PHI que o modelo não detectou e portanto não anonimizou.
    tp = sum(1 for s in spans_gold if any(
        s['inicio'] == p['inicio'] and s['fim'] == p['fim'] and s['tipo'] == p['tipo']
        for p in spans_pred
    ))
    fn = len(spans_gold) - tp
    return round(tp / (tp + fn), 4) if (tp + fn) > 0 else 0.0
# Fim - 3) Anonimização - 3.2) Avaliação de Privacidade — Dimensão L - 3.2.1) Coverage


# Início - 3) Anonimização - 3.2) Avaliação de Privacidade — Dimensão L do TILD - 3.2.2) Precision_anon
def calcular_precision_anon(spans_gold, spans_pred):
    # Precision_anon = TP / (TP + FP)
    # Mede quantas das substituições feitas eram de fato PHI.
    # Um FP é um span não-PHI que foi anonimizado incorretamente.
    tp = sum(1 for p in spans_pred if any(
        p['inicio'] == s['inicio'] and p['fim'] == s['fim'] and p['tipo'] == s['tipo']
        for s in spans_gold
    ))
    fp = len(spans_pred) - tp
    return round(tp / (tp + fp), 4) if (tp + fp) > 0 else 0.0
# Fim - 3) Anonimização - 3.2) Avaliação de Privacidade — Dimensão L - 3.2.2) Precision_anon


# Início - 3) Anonimização - 3.2) Avaliação de Privacidade — Dimensão L do TILD - 3.2.3) Levenshtein Ratio
def calcular_levenshtein(texto_original, texto_anonimizado):
    # Mede o grau de alteração entre o texto original e o anonimizado.
    # Levenshtein Ratio próximo de 0 = textos muito diferentes (muita anonimização)
    # Levenshtein Ratio próximo de 1 = textos quase iguais (pouca anonimização)
    return round(1 - levenshtein_ratio(texto_original, texto_anonimizado), 4)
# Fim - 3) Anonimização - 3.2) Avaliação de Privacidade — Dimensão L - 3.2.3) Levenshtein Ratio

# Início - 3) Anonimização - 3.3) Avaliação de Utilidade — Dimensão I do TILD - 3.3.3) Cálculo ΔF1
def calcular_delta_f1(f1_original, f1_anonimizado):
    # Calcula o ΔF1 = F1_anonimizado − F1_original por entidade clínica e geral.
    # Um ΔF1 próximo de 0 indica que a anonimização preservou a utilidade clínica do texto.
    # Um ΔF1 muito negativo indica perda de informação clínica relevante.
    #
    # Parâmetros:
    #   f1_original    : dict {entidade → f1} do modelo treinado no corpus original
    #   f1_anonimizado : dict {entidade → f1} do modelo treinado no corpus anonimizado

    delta = {}
    todas_entidades = set(f1_original) | set(f1_anonimizado)

    for entidade in todas_entidades:
        orig = f1_original.get(entidade, 0.0)
        anon = f1_anonimizado.get(entidade, 0.0)
        delta[entidade] = round(anon - orig, 4)

    # ΔF1 geral: média dos deltas por entidade
    delta['_geral'] = round(sum(delta.values()) / len(delta), 4)

    return delta
# Fim - 3) Anonimização - 3.3) Avaliação de Utilidade — Dimensão I do TILD - 3.3.3) Cálculo ΔF1

# Início - 3) Anonimização - 3.4) Consolidação dos Resultados - 3.4.1) Tabela TILD comparativa
def gerar_tabela_tild(resultados_modelos):
    # Monta DataFrame com as 3 dimensões do TILD para todos os modelos.
    # resultados_modelos: dict com nome do modelo → dict de métricas
    # Exemplo:
    # {
    #   'CRF': {
    #       'coverage': 0.82, 'precision_anon': 0.91, 'levenshtein': 0.34,
    #       'f1_original': 0.74, 'f1_anonimizado': 0.71, 'delta_f1': -0.03
    #   }, ...
    # }
    import pandas as pd

    linhas = []
    for modelo, m in resultados_modelos.items():
        linhas.append({
            'Modelo':           modelo,
            # T — Desempenho NER
            'F1 NER':           m.get('f1_ner', '-'),
            # L — Privacidade
            'Coverage':         m.get('coverage', '-'),
            'Precision_anon':   m.get('precision_anon', '-'),
            'Levenshtein':      m.get('levenshtein', '-'),
            # I — Utilidade
            'F1 Original':      m.get('f1_original', '-'),
            'F1 Anonimizado':   m.get('f1_anonimizado', '-'),
            'ΔF1':              m.get('delta_f1', '-'),
        })

    df = pd.DataFrame(linhas)
    df = df.sort_values('F1 NER', ascending=False).reset_index(drop=True)
    return df
# Fim - 3) Anonimização - 3.4) Consolidação dos Resultados - 3.4.1) Tabela TILD comparativa


# Início - 3) Anonimização - 3.4) Consolidação dos Resultados - 3.4.2) Exportação CSV para dissertação
def exportar_tabela_tild_csv(df_tild, caminho_saida):
    # Exporta a tabela TILD completa em CSV com BOM para abertura correta no Excel.
    with open(caminho_saida, 'w', encoding='utf-8-sig', newline='') as f:
        df_tild.to_csv(f, index=False, sep=';')
# Fim - 3) Anonimização - 3.4) Consolidação dos Resultados - 3.4.2) Exportação CSV para dissertação


# Início - 3) Anonimização - 3.4) Consolidação dos Resultados - 3.4.3) Geração de gráficos
def gerar_graficos_tild(df_tild, diretorio_saida):
    # Gera dois gráficos de barras para a dissertação:
    #   1) F1 NER × modelo (Dimensão T)
    #   2) ΔF1 × modelo (Dimensão I)
    # Salva em PNG no diretório informado.
    import os
    import matplotlib.pyplot as plt

    os.makedirs(diretorio_saida, exist_ok=True)

    # Gráfico 1 — F1 NER por modelo
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(df_tild['Modelo'], df_tild['F1 NER'], color='steelblue')
    ax.set_title('F1 NER por Modelo (Dimensão T do TILD)')
    ax.set_ylabel('F1 entity-level (micro)')
    ax.set_ylim(0, 1)
    ax.axhline(y=0.80, color='red', linestyle='--', label='Meta 0.80')
    ax.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(diretorio_saida, 'grafico_f1_ner.png'), dpi=150)
    plt.close()

    # Gráfico 2 — ΔF1 por modelo
    fig, ax = plt.subplots(figsize=(8, 4))
    cores = ['green' if v >= 0 else 'red' for v in df_tild['ΔF1']]
    ax.bar(df_tild['Modelo'], df_tild['ΔF1'], color=cores)
    ax.set_title('ΔF1 por Modelo (Dimensão I do TILD — Utilidade)')
    ax.set_ylabel('ΔF1 = F1_anon − F1_orig')
    ax.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
    plt.tight_layout()
    plt.savefig(os.path.join(diretorio_saida, 'grafico_delta_f1.png'), dpi=150)
    plt.close()
# Fim - 3) Anonimização - 3.4) Consolidação dos Resultados - 3.4.3) Geração de gráficos

