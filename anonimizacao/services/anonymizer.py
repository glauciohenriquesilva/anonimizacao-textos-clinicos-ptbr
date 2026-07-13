"""
Pipeline Híbrido de Anonimização — AnonClin
============================================

Arquitetura em 4 etapas (decisão metodológica jul/2026):

  Etapa 1 — Regex (normalizar_texto):
      Detecta PHI estruturado com precisão 100% determinística.
      Converte para placeholders: __DATA__, __HORA__, __TELEFONE__,
      __CPF__, __CEP__, __EMAIL__.

  Etapa 2 — NER (Transformer ou CRF):
      Detecta PHI contextual que regex não consegue cobrir:
      PESSOA, ENDEREÇO, INSTITUIÇÃO, DOCUMENTO (RG/CNS no texto).

  Etapa 3 — PLACEHOLDER_MAP:
      Converte placeholders (tokens intermediários) para marcadores
      semânticos finais: __DATA__ → [DATA], __TELEFONE__ → [CONTATO], etc.

  Etapa 4 — Substituição NER → marcadores:
      Substitui os spans detectados pelo NER pelos marcadores finais:
      [PESSOA], [ENDEREÇO], [INSTITUIÇÃO], [DOCUMENTO].

Diferencial em relação à literatura (Schiezaro 2026, Almeida 2026):
    Schiezaro e Almeida usam NER puro para todas as entidades, inclusive
    as estruturadas. Esta arquitetura separa as responsabilidades:
    regex garante cobertura 100% para PHI estruturado e libera o NER
    para focar nas entidades genuinamente contextuais.

Uso básico:
    from anonimizacao.services.anonymizer import HybridAnonymizer, criar_predictor_bert

    predictor = criar_predictor_bert('/caminho/para/modelo')
    anon = HybridAnonymizer(ner_predictor=predictor)
    resultado = anon.anonymize("Paciente João Silva, nascido em 01/03/1980...")
    print(resultado['texto_anonimizado'])
"""

import re
import os
import sys

# Adiciona o diretório raiz do projeto ao path para imports Django-independentes
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from preprocessamento.services.preprocessamento import (
    normalizar_texto,
    tokenizar_word_level,
)
from anonimizacao.services.anonimizacao import (
    extrair_spans_phi,
    ordenar_spans_reverso,
    calcular_coverage,
    calcular_precision_anon,
)


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Mapeamento de placeholders (PHI estruturado) para marcadores finais
# Aplicado na Etapa 3, após o NER.
PLACEHOLDER_MAP = {
    '__TELEFONE__': '[CONTATO]',
    '__EMAIL__':    '[CONTATO]',
    '__CPF__':      '[DOCUMENTO]',
    '__CEP__':      '[ENDEREÇO]',
    '__DATA__':     '[DATA]',
    '__HORA__':     '[HORA]',
}

# Mapeamento de tipos de entidade NER para marcadores finais
# Suporta grafias com e sem acento (variação dos modelos treinados).
ENTITY_MARKER_MAP = {
    'PESSOA':      '[PESSOA]',
    'DOCUMENTO':   '[DOCUMENTO]',
    'ENDERECO':    '[ENDEREÇO]',
    'ENDEREÇO':    '[ENDEREÇO]',
    'INSTITUICAO': '[INSTITUIÇÃO]',
    'INSTITUIÇÃO': '[INSTITUIÇÃO]',
    'CONTATO':     '[CONTATO]',
    'DATA':        '[DATA]',
    'HORA':        '[HORA]',
}

# Entidades tratadas por regex — NÃO devem ser consideradas no NER
# (o modelo não deveria predizê-las, mas por segurança filtramos)
ENTIDADES_REGEX = frozenset({
    'DATA', 'HORA', 'CONTATO',
    '__DATA__', '__HORA__', '__TELEFONE__', '__EMAIL__', '__CPF__', '__CEP__',
})


# ---------------------------------------------------------------------------
# Classe principal
# ---------------------------------------------------------------------------

class HybridAnonymizer:
    """
    Anonimizador híbrido: regex para PHI estruturado + NER para PHI contextual.

    Parâmetros:
        ner_predictor   : callable(tokens: list[str]) → labels: list[str]
                          Recebe lista de tokens word-level e retorna lista de
                          labels BIO (ex: ['O', 'B-PESSOA', 'I-PESSOA', 'O']).
                          Se None, aplica apenas o pipeline regex.
        numbered_markers: se True, usa [PESSOA_1], [PESSOA_2] para manter
                          consistência intra-documento (mesma pessoa = mesmo marcador).
                          Se False (padrão), usa [PESSOA] para todos — formato
                          preferido para avaliação seqeval.
    """

    def __init__(self, ner_predictor=None, numbered_markers=False):
        self.ner_predictor = ner_predictor
        self.numbered_markers = numbered_markers

    # -------------------------------------------------------------------
    # Etapa 3 — PLACEHOLDER_MAP
    # -------------------------------------------------------------------
    def _aplicar_placeholder_map(self, tokens):
        """Converte tokens placeholder em marcadores finais."""
        return [PLACEHOLDER_MAP.get(t, t) for t in tokens]

    # -------------------------------------------------------------------
    # Etapa 4 — Substituição dos spans NER por marcadores
    # -------------------------------------------------------------------
    def _aplicar_ner_spans(self, tokens, labels):
        """
        Substitui os spans de entidades detectadas pelo NER pelos marcadores
        semânticos finais.

        Retorna:
            tokens_anon : list[str] — tokens com spans substituídos
            spans       : list[dict] — spans detectados (para métricas)
        """
        spans = extrair_spans_phi(tokens, labels)

        # Filtra entidades que pertencem ao pipeline regex (não NER)
        spans = [s for s in spans if s['tipo'] not in ENTIDADES_REGEX]
        spans_ord = ordenar_spans_reverso(spans)

        tokens_result = list(tokens)

        if self.numbered_markers:
            # Modo numerado: [PESSOA_1], [PESSOA_2]... para consistência
            contadores = {}
            mapeamento = {}
            for span in spans_ord:
                texto = span['texto']
                tipo  = span['tipo']
                if texto not in mapeamento:
                    contadores[tipo] = contadores.get(tipo, 0) + 1
                    base = ENTITY_MARKER_MAP.get(tipo, f'[{tipo}]')
                    # Insere o número antes do ']'
                    marcador = base[:-1] + f'_{contadores[tipo]}]'
                    mapeamento[texto] = marcador
                marcador = mapeamento[texto]
                tokens_result[span['inicio']] = marcador
                for k in range(span['inicio'] + 1, span['fim']):
                    tokens_result[k] = None
        else:
            # Modo simples: [PESSOA], [ENDEREÇO]...
            for span in spans_ord:
                marcador = ENTITY_MARKER_MAP.get(span['tipo'], f"[{span['tipo']}]")
                tokens_result[span['inicio']] = marcador
                for k in range(span['inicio'] + 1, span['fim']):
                    tokens_result[k] = None

        tokens_anon = [t for t in tokens_result if t is not None]
        return tokens_anon, spans

    # -------------------------------------------------------------------
    # Interface pública
    # -------------------------------------------------------------------
    def anonymize(self, texto_bruto):
        """
        Anonimiza um texto clínico bruto.

        Retorna dict com:
            texto_original    : str  — texto de entrada
            texto_normalizado : str  — texto após Etapa 1 (regex + placeholders)
            texto_anonimizado : str  — texto final com marcadores
            tokens_originais  : list — tokens após normalização
            tokens_finais     : list — tokens após todas as substituições
            spans_ner         : list — spans detectados pelo NER
            n_phi_regex       : int  — PHI capturado por regex
            n_phi_ner         : int  — PHI capturado por NER
            n_phi_total       : int  — total de PHI substituído
        """
        # Etapa 1 — Normalização + regex mascaramento
        texto_norm = normalizar_texto(texto_bruto)

        # Tokenização (placeholders ficam como token único)
        tokens = tokenizar_word_level(texto_norm)

        # Conta PHI capturado por regex (placeholders nos tokens)
        n_phi_regex = sum(1 for t in tokens if t in PLACEHOLDER_MAP)

        # Etapa 2 — NER para PHI contextual
        spans_ner = []
        tokens_pos_ner = list(tokens)

        if self.ner_predictor is not None:
            labels = self.ner_predictor(tokens)
            tokens_pos_ner, spans_ner = self._aplicar_ner_spans(tokens, labels)

        # Etapa 3 — PLACEHOLDER_MAP → marcadores finais
        tokens_finais = self._aplicar_placeholder_map(tokens_pos_ner)

        # Reconstrói o texto anonimizado
        texto_anonimizado = ' '.join(tokens_finais)

        return {
            'texto_original':    texto_bruto,
            'texto_normalizado': texto_norm,
            'texto_anonimizado': texto_anonimizado,
            'tokens_originais':  tokens,
            'tokens_finais':     tokens_finais,
            'spans_ner':         spans_ner,
            'n_phi_regex':       n_phi_regex,
            'n_phi_ner':         len(spans_ner),
            'n_phi_total':       n_phi_regex + len(spans_ner),
        }

    def anonymize_batch(self, textos):
        """
        Anonimiza uma lista de textos clínicos.

        Retorna lista de dicts (mesmo formato de anonymize()).
        """
        return [self.anonymize(t) for t in textos]

    def calcular_metricas_l(self, conll_path, entidades_ner=None):
        """
        Calcula as métricas L do framework TILD sobre um conjunto anotado.

        Dimensão L — Privacidade:
            coverage      = Recall  = TP / (TP + FN)  — quantos PHI foram cobertos
            precision_anon = Precision = TP / (TP + FP) — quantas substituições eram PHI real

        Parâmetros:
            conll_path    : caminho para arquivo CoNLL anotado (test.conll)
            entidades_ner : set de tipos a avaliar (padrão: PESSOA, ENDERECO, INSTITUICAO, DOCUMENTO)
                           Entidades tratadas por regex (DATA, HORA, CONTATO) são excluídas
                           porque têm precisão 100% garantida — não precisam ser medidas aqui.

        Retorna dict com: coverage, precision_anon, f1_anon, tp, fp, fn, n_sentencas
        """
        if self.ner_predictor is None:
            raise ValueError(
                "ner_predictor é necessário para calcular métricas L. "
                "Carregue um modelo antes de chamar este método."
            )

        if entidades_ner is None:
            entidades_ner = {'PESSOA', 'ENDERECO', 'ENDEREÇO', 'INSTITUICAO', 'INSTITUIÇÃO', 'DOCUMENTO'}

        # Importa leitor CoNLL do módulo NER existente
        try:
            from ner.services.crf import ler_conll
        except ImportError:
            # Fallback: leitor CoNLL simples inline
            ler_conll = _ler_conll_simples

        todas_tokens, todas_labels = ler_conll(conll_path)

        total_tp, total_fp, total_fn = 0, 0, 0

        for tokens, labels_gold in zip(todas_tokens, todas_labels):
            labels_pred = self.ner_predictor(tokens)

            spans_gold = [s for s in extrair_spans_phi(tokens, labels_gold)
                          if s['tipo'] in entidades_ner]
            spans_pred = [s for s in extrair_spans_phi(tokens, labels_pred)
                          if s['tipo'] in entidades_ner]

            for sg in spans_gold:
                if any(sg['inicio'] == sp['inicio'] and
                       sg['fim']    == sp['fim']    and
                       sg['tipo']   == sp['tipo']
                       for sp in spans_pred):
                    total_tp += 1
                else:
                    total_fn += 1

            for sp in spans_pred:
                if not any(sp['inicio'] == sg['inicio'] and
                           sp['fim']    == sg['fim']    and
                           sp['tipo']   == sg['tipo']
                           for sg in spans_gold):
                    total_fp += 1

        coverage       = round(total_tp / (total_tp + total_fn), 4) if (total_tp + total_fn) > 0 else 0.0
        precision_anon = round(total_tp / (total_tp + total_fp), 4) if (total_tp + total_fp) > 0 else 0.0
        f1_anon        = round(
            2 * coverage * precision_anon / (coverage + precision_anon), 4
        ) if (coverage + precision_anon) > 0 else 0.0

        return {
            'coverage':       coverage,       # Recall — cobertura de PHI
            'precision_anon': precision_anon, # Precision — exatidão das substituições
            'f1_anon':        f1_anon,        # F1 combinado
            'tp':             total_tp,
            'fp':             total_fp,
            'fn':             total_fn,
            'n_sentencas':    len(todas_tokens),
        }


# ---------------------------------------------------------------------------
# Leitor CoNLL fallback (caso o import do módulo NER falhe)
# ---------------------------------------------------------------------------

def _ler_conll_simples(caminho):
    """
    Lê arquivo CoNLL (token\\tlabel por linha, sentenças separadas por linha vazia).
    Retorna (lista_de_tokens, lista_de_labels) onde cada elemento é uma sentença.
    """
    todas_tokens, todas_labels = [], []
    tokens_sent, labels_sent   = [], []

    with open(caminho, encoding='utf-8') as f:
        for linha in f:
            linha = linha.rstrip('\n')
            if linha.strip() == '':
                if tokens_sent:
                    todas_tokens.append(tokens_sent)
                    todas_labels.append(labels_sent)
                    tokens_sent, labels_sent = [], []
            else:
                partes = linha.split('\t')
                if len(partes) >= 2:
                    tokens_sent.append(partes[0])
                    labels_sent.append(partes[1])

    if tokens_sent:
        todas_tokens.append(tokens_sent)
        todas_labels.append(labels_sent)

    return todas_tokens, todas_labels


# ---------------------------------------------------------------------------
# Fábricas de predictors NER
# ---------------------------------------------------------------------------

def criar_predictor_crf(caminho_modelo):
    """
    Carrega um modelo CRF serializado (.pkl) e retorna um predictor compatível
    com HybridAnonymizer.

    Parâmetros:
        caminho_modelo : caminho para o arquivo .pkl do CRF

    Retorna:
        callable(tokens: list[str]) → labels: list[str]
    """
    import pickle
    from preprocessamento.services.preprocessamento import extrair_features_sentenca

    with open(caminho_modelo, 'rb') as f:
        crf = pickle.load(f)

    def predictor(tokens):
        features = extrair_features_sentenca(tokens)
        return crf.predict([features])[0]

    predictor.__doc__ = f"CRF predictor — modelo: {caminho_modelo}"
    return predictor


def criar_predictor_bert(caminho_modelo, device=None):
    """
    Carrega um modelo HuggingFace para Token Classification e retorna um predictor
    compatível com HybridAnonymizer.

    Funciona com qualquer modelo salvo via Trainer.save_model() ou
    model.save_pretrained(): BERTimbau-leNER, BioBERTpt-clin, mmBERT, ModernBERT.

    Parâmetros:
        caminho_modelo : caminho local ou HuggingFace Hub ID do modelo
        device         : 'cpu', 'cuda', 'mps' ou None (auto-detecta)

    Retorna:
        callable(tokens: list[str]) → labels: list[str]

    Exemplo:
        predictor = criar_predictor_bert('/drive/MyDrive/mestrado/modelos/lener-large-best')
        anon = HybridAnonymizer(ner_predictor=predictor)
    """
    import torch
    from transformers import AutoTokenizer, AutoModelForTokenClassification

    # Auto-detecta device se não informado
    if device is None:
        if torch.cuda.is_available():
            device = 'cuda'
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            device = 'mps'
        else:
            device = 'cpu'

    tokenizer = AutoTokenizer.from_pretrained(caminho_modelo)
    model     = AutoModelForTokenClassification.from_pretrained(caminho_modelo)
    model.eval()
    model.to(device)

    id2label = model.config.id2label  # {0: 'O', 1: 'B-PESSOA', ...}

    def predictor(tokens):
        """
        Recebe lista de tokens word-level e retorna lista de labels BIO.
        Usa word_ids() para alinhar subtokens → tokens originais corretamente
        (método correto, consistente com o treinamento).
        """
        # Tokenização subword com alinhamento de palavras
        encoding = tokenizer(
            tokens,
            is_split_into_words=True,
            return_tensors='pt',
            truncation=True,
            max_length=512,
            padding=True,
        )

        # Inferência sem gradiente
        with torch.no_grad():
            outputs = model(**{k: v.to(device) for k, v in encoding.items()})

        pred_ids = torch.argmax(outputs.logits, dim=-1)[0].cpu().tolist()
        word_ids  = encoding.word_ids(batch_index=0)

        # Alinha subtokens → tokens originais via word_ids()
        # Apenas o primeiro subtoken de cada palavra recebe a label.
        labels = ['O'] * len(tokens)
        prev_word_id = None
        for subtoken_idx, word_id in enumerate(word_ids):
            if word_id is None:
                continue  # token especial ([CLS], [SEP], [PAD])
            if word_id != prev_word_id:
                labels[word_id] = id2label.get(pred_ids[subtoken_idx], 'O')
                prev_word_id = word_id
            # subtokens de continuação (##algo) → ignorados

        return labels

    predictor.__doc__ = f"BERT predictor — modelo: {caminho_modelo} | device: {device}"
    return predictor


# ---------------------------------------------------------------------------
# Utilitário: exemplo de uso e teste rápido
# ---------------------------------------------------------------------------

def _demo():
    """Demonstração do pipeline híbrido sem modelo NER (apenas regex)."""
    textos = [
        "Paciente ROSIANE DA SILVA RISO, CPF 123.456.789-00, nascida em 04/07/1980. "
        "Telefone: (27) 99516-5083. Residente na RUA MINAS GERAIS, Nº 20, BAIRRO VILA BETHANIA, VIANA-ES.",

        "PA: 120x80 mmHg. FC: 88 bpm. Prescrito Dipirona 500mg VO 6/6h por 5 dias.",

        "Evolução de 3/30/2026 07:09 — paciente em bom estado geral. "
        "E-mail do responsável: joao.silva@gmail.com",
    ]

    print("=" * 60)
    print("DEMO — Pipeline Híbrido (apenas regex, sem NER)")
    print("=" * 60)

    anon = HybridAnonymizer(ner_predictor=None)

    for texto in textos:
        resultado = anon.anonymize(texto)
        print(f"\n[ORIGINAL]\n{resultado['texto_original']}")
        print(f"\n[ANONIMIZADO]\n{resultado['texto_anonimizado']}")
        print(f"\n[PHI capturado] regex={resultado['n_phi_regex']} | NER={resultado['n_phi_ner']}")
        print("-" * 60)


if __name__ == '__main__':
    _demo()
