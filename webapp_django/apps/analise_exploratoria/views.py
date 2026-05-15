"""
Views — Análise Exploratória (etapa 0 do pipeline)

Subseções:
    0.1 + 0.2  estatisticas  — leitura do dataset + estatísticas descritivas
    0.3        distribuicao  — distribuição de tokens e caracteres
    0.4        classificacao — detecção texto livre vs. template
    0.5        saidas        — geração da Tabela 1 + gráficos
"""
from django.shortcuts import render


def _load_stats():
    """
    Lê o stats.json pré-computado pela análise exploratória.
    Retorna None se a análise ainda não foi executada.
    """
    from django.conf import settings
    from src.analysis.exploratory import load_stats_json
    output_dir = getattr(settings, "OUTPUTS_PATH", "outputs/") + "exploratory_analysis"
    return load_stats_json(output_dir)


def estatisticas(request):
    """Estatísticas descritivas do dataset (contagens, pacientes únicos, período, especialidades)."""
    payload = _load_stats()
    stats   = payload.get("doc_types", {}) if payload else {}

    # Agrega totais combinados (prescrições + pareceres)
    n_total       = sum(s.get("n_total", 0) for s in stats.values())
    n_prescricoes = stats.get("prescricoes", {}).get("n_total", 0)
    n_pareceres   = stats.get("pareceres",   {}).get("n_total", 0)

    # Pacientes únicos: usa o maior valor (intersecção não disponível sem join)
    n_pacientes = max(
        (s.get("n_pacientes_unicos") or 0 for s in stats.values()), default=None
    ) or None

    # Período: min global / max global
    periodos = [s.get("periodo", {}) for s in stats.values()]
    periodo_min = min((p["min"] for p in periodos if p.get("min")), default=None)
    periodo_max = max((p["max"] for p in periodos if p.get("max")), default=None)
    periodo = f"{periodo_min} — {periodo_max}" if periodo_min else None

    # Hospitais
    n_hospitais = max(
        (s.get("n_hospitais") or 0 for s in stats.values()), default=None
    ) or None

    # Top especialidades (usa prescrições como referência principal)
    top_especialidades = (
        stats.get("prescricoes", {}).get("top_especialidades")
        or stats.get("pareceres", {}).get("top_especialidades")
        or []
    )

    context = {
        "section":    "analise_exploratoria",
        "subsection": "estatisticas",
        # Dados para os cards
        "total_registros":    f"{n_total:,}" if n_total else None,
        "n_docs_prescricoes": f"{n_prescricoes:,}" if n_prescricoes else "0",
        "n_docs_pareceres":   f"{n_pareceres:,}"   if n_pareceres   else "0",
        "pacientes_unicos":   f"{n_pacientes:,}"   if n_pacientes   else None,
        "periodo":            periodo,
        "n_hospitais":        f"{n_hospitais:,}"   if n_hospitais   else None,
        # Top especialidades
        "top_especialidades": top_especialidades,
        # Metadados
        "generated_at": payload.get("generated_at") if payload else None,
        "analise_executada": payload is not None,
    }
    return render(request, "analise_exploratoria/estatisticas.html", context)


def distribuicao(request):
    """Distribuição de tokens, caracteres e sentenças por documento."""
    payload = _load_stats()
    stats   = payload.get("doc_types", {}) if payload else {}

    # Monta dict {doc_type: token_stats} para o template
    dist_stats = {
        dt: s.get("token_stats")
        for dt, s in stats.items()
        if s.get("token_stats")
    }

    context = {
        "section":    "analise_exploratoria",
        "subsection": "distribuicao",
        "stats":      dist_stats,
        "analise_executada": payload is not None,
    }
    return render(request, "analise_exploratoria/distribuicao.html", context)


def classificacao(request):
    """Classificação do tipo de texto: texto livre vs. template estruturado."""
    payload = _load_stats()
    stats   = payload.get("doc_types", {}) if payload else {}

    classificacao_data = {
        dt: {
            "livre_pct":    (s.get("text_types") or {}).get("livre",    {}).get("pct", 0),
            "template_pct": (s.get("text_types") or {}).get("template", {}).get("pct", 0),
            "n_livre":      (s.get("text_types") or {}).get("livre",    {}).get("count", 0),
            "n_template":   (s.get("text_types") or {}).get("template", {}).get("count", 0),
        }
        for dt, s in stats.items()
        if s.get("text_types")
    }

    context = {
        "section":    "analise_exploratoria",
        "subsection": "classificacao",
        "classificacao": classificacao_data,
        "analise_executada": payload is not None,
    }
    return render(request, "analise_exploratoria/classificacao.html", context)


def saidas(request):
    """Geração de saídas: Tabela 1 da dissertação, histogramas e exportação JSON."""
    from django.conf import settings
    from pathlib import Path

    output_dir = Path(getattr(settings, "OUTPUTS_PATH", "outputs/")) / "exploratory_analysis"
    payload    = _load_stats()

    tabela1_csv  = output_dir / "tabela1.csv"
    tabela1_xlsx = output_dir / "tabela1.xlsx"
    hist_png     = output_dir / "figura1_distribuicao_tokens.png"

    context = {
        "section":    "analise_exploratoria",
        "subsection": "saidas",
        "analise_executada":    payload is not None,
        "tabela1_csv_existe":   tabela1_csv.exists(),
        "tabela1_xlsx_existe":  tabela1_xlsx.exists(),
        "histograma_existe":    hist_png.exists(),
        "generated_at":         payload.get("generated_at") if payload else None,
        "output_dir":           str(output_dir),
    }
    return render(request, "analise_exploratoria/saidas.html", context)
