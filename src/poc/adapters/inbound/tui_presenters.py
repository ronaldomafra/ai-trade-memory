"""Read-only presentation of existing API records; no inference or trading rules."""

import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from rich.text import Text

STRATEGIES = {"BASELINE_TECHNICAL": "A", "JEV_STATIC": "B", "JEV_LEARNING": "C"}
NAMES = {"A": "Técnica", "B": "JEV", "C": "JEV + memória"}
ACTION_NAMES = {"BUY": "COMPROU", "SELL": "VENDEU", "HOLD": "AGUARDOU"}
ACTION_COLORS = {"BUY": "#00ff9f", "SELL": "#ff5b6e", "HOLD": "#ffca57"}
REASONS = {
    "JEV_CHOICE": "JEV escolheu esta ação.",
    "TECHNICAL_ENTRY": "Sinal técnico de entrada registrado.",
    "STRATEGY_BUY": "Compra aprovada pela estratégia.",
    "STRATEGY_SELL": "Sinal de saída da estratégia.",
    "STOP_LOSS": "Saída de proteção: stop-loss.",
    "TAKE_PROFIT": "Saída por objetivo de lucro (take-profit).",
    "MAX_HOLDING": "Limite de duração da posição atingido.",
    "DAILY_RISK_GUARD": "Saída de proteção por perda diária.",
    "DAILY_RISK_BLOCKED": "Compras bloqueadas pela proteção diária.",
    "LOW_CONFIDENCE": "Sinal abaixo dos critérios mínimos de probabilidade ou margem.",
    "STALE_QUOTE": "Cotação desatualizada ou indisponível.",
    "STALE_DECISION": "Janela de execução da decisão encerrada.",
    "INVALID_FEATURES": "Indicadores indisponíveis ou inválidos.",
    "QUOTE_NOT_AFTER_DECISION": "Faltou uma cotação posterior à decisão.",
    "EXTERNAL_CONTEXT_UNAVAILABLE": "Sem contexto externo elegível para a entrada.",
    "AI_CIRCUIT_OPEN": "Acesso à IA bloqueado pelo circuito de proteção.",
    "AI_CONTEXT_TOO_LARGE": "Contexto excedeu o limite permitido.",
    "AI_BUDGET_EXCEEDED": "Limite diário de chamadas ou custo da IA atingido.",
    "AI_TIMEOUT": "IA não respondeu dentro do prazo.",
    "AI_FAILURE": "Falha na consulta à IA.",
    "AI_NOT_CONFIGURED": "IA não configurada.",
    "INVALID_AI_RESPONSE": "Resposta da IA inválida.",
    "ENTRIES_DISABLED": "Novas entradas estão desabilitadas.",
    "CLOSED_IN_SAME_CYCLE": "Posição já encerrada neste ciclo.",
    "SERVICE_STOPPING": "Motor em encerramento.",
    "ENTRY_FOUNDATION_UNVERIFIABLE": "Fundamento da entrada não verificável.",
    "ENTRY_FOUNDATION_INSUFFICIENT": "Fundamento insuficiente para a compra.",
    "ENTRY_DEPENDS_ON_UNRESOLVED_CONFLICT": (
        "Entrada depende de informação conflitante não resolvida."
    ),
    "ENTRY_DEPENDS_ON_UNVERIFIABLE_PREMISE": "Entrada depende de uma premissa não verificável.",
}


def plain(value, limit=360):
    return " ".join(str(value or "").split())[:limit]


def object_value(value):
    if isinstance(value, dict):
        return value
    try:
        result = json.loads(value or "{}")
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}


def timestamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.astimezone(UTC) if result.tzinfo else None
    except (ValueError, TypeError):
        return None


def when(value):
    parsed = timestamp(value)
    return parsed.strftime("%d/%m %H:%M:%S UTC") if parsed else "horário não informado"


def numeric(value, digits=2, multiplier=1):
    try:
        number = Decimal(str(value)) * multiplier
        return f"{number:.{digits}f}" if number.is_finite() else "—"
    except (InvalidOperation, TypeError, ValueError):
        return "—"


def cycle_groups(decisions):
    groups = {}
    for row in decisions:
        identity = row.get("cycle_id")
        if identity:
            groups.setdefault(identity, []).append(row)
    return dict(
        sorted(
            groups.items(),
            key=lambda pair: max(
                row.get("decision_started_at", row.get("decision_at", "")) for row in pair[1]
            ),
            reverse=True,
        )
    )


def cycle_time(rows):
    return min((r.get("decision_started_at") or r.get("decision_at", "") for r in rows), default="")


def decision_summary(rows):
    if not rows:
        return Text("Aguardando o primeiro ciclo registrado.", style="dim")
    output = Text()
    output.append(f"Avaliação em {when(cycle_time(rows))}\n", style="bold")
    for identity, letter in STRATEGIES.items():
        row = next((r for r in rows if r.get("portfolio_id") == identity), None)
        output.append(f"{letter} · {NAMES[letter]}  ", style="bold cyan")
        if row is None or row.get("status") != "COMPLETED":
            output.append("Aguardando conclusão desta carteira.\n", style="dim")
            continue
        action = row.get("executed_action", "HOLD")
        output.append(ACTION_NAMES.get(action, plain(action)), style=ACTION_COLORS.get(action))
        proposed = row.get("proposed_action")
        if proposed and proposed != action:
            output.append(f" · proposta {proposed} → executada {action}")
        state = object_value(row.get("state_json"))
        reason = row.get("reason_code", "")
        description = REASONS.get(reason)
        if reason == "JEV_CHOICE":
            verb = {"BUY": "comprar", "SELL": "vender", "HOLD": "aguardar"}.get(action, "esta ação")
            description = f"JEV escolheu {verb}."
        if reason == "HOLD" and letter == "A":
            description = (
                "Sem sinal técnico de saída."
                if state.get("portfolio", {}).get("has_position")
                else "Condições técnicas de entrada não atendidas."
            )
        output.append(
            "\n  " + (description or f"Motivo registrado: {plain(reason) or 'não informado'}.")
        )
        probabilities = object_value(row.get("probabilities_json"))
        if probabilities:
            output.append(
                " · P(ação): "
                + " / ".join(
                    f"{label} {numeric(probabilities.get(key), 1, 100)}%"
                    for key, label in (("buy", "BUY"), ("sell", "SELL"), ("hold", "HOLD"))
                )
            )
        if row.get("confidence") is not None:
            output.append(f" · Confiança JEV: {numeric(row['confidence'], 3)}")
        if letter == "C":
            feedback = state.get("historical_feedback", {})
            status = feedback.get("status")
            label = {
                "available": "disponível",
                "insufficient_samples": "amostras insuficientes",
                "disabled": "desabilitada",
            }.get(status, plain(status) or "não informada")
            output.append(f"\n  Memória neste ciclo: {label}.")
        output.append("\n")
    return output


def technical_summary(rows):
    if not rows:
        return Text("Indicadores do ciclo: aguardando dados.", style="dim")
    market = object_value(rows[0].get("state_json")).get("market", {})
    if not market.get("valid"):
        return Text(
            "Indicadores do ciclo indisponíveis: " + plain(market.get("reason", "sem registro"))
        )
    trend = {"bullish": "alta", "bearish": "baixa", "range": "lateral"}
    direction = trend.get(market.get("trend_direction", market.get("trend_1h")), "indeterminada")
    return Text(
        f"INDICADORES DO CICLO · {when(market.get('as_of'))}\n"
        f"RSI: {numeric(market.get('rsi_14'), 1)} · "
        f"Tendência {market.get('trend_interval', '1h')}: {direction} · "
        f"MACD hist.: {numeric(market.get('macd_histogram'), 4)} · "
        f"Volume relativo: {numeric(market.get('volume_ratio'))}x\n"
        f"EMA curta / média / longa: {numeric(market.get('ema_short'))} / "
        f"{numeric(market.get('ema_mid'))} / {numeric(market.get('ema_long'))} · "
        f"ATR: {numeric(market.get('atr_pct'))}%\n"
        "Valores registrados na avaliação; não são os indicadores da cotação atual."
    )


def source_stamp(item):
    prices = [
        timestamp(change.get("to_source_at"))
        for change in (item.get("probability_changes") or {}).values()
        if isinstance(change, dict)
    ]
    return (
        max((stamp for stamp in prices if stamp), default=None)
        or timestamp(item.get("source_observed_at"))
        or timestamp(item.get("available_at"))
        or timestamp(item.get("evidence", {}).get("published_at"))
        or datetime.min.replace(tzinfo=UTC)
    )


def update_source_records(snapshot, previous):
    """Retain only the last received factor per source, always labelled as history if stale."""
    result = dict(previous)
    external = snapshot.get("external_context") or {}
    for section in ("news", "prediction_markets"):
        items = external.get(section, {}).get("items", [])
        origin = "snapshot atual"
        if not items and section not in result:
            items = [
                item
                for row in snapshot.get("recent_decisions", [])
                for item in object_value(row.get("state_json")).get(section, {}).get("items", [])
            ]
            origin = "histórico recente de decisões"
        if items:
            result[section] = {"item": max(items, key=source_stamp), "origin": origin}
    return result


def source_summary(section, record, current, now=None):
    title = "NOTÍCIA" if section == "news" else "POLYMARKET"
    status = current.get("status", "unavailable")
    output = Text()
    output.append(f"{title} · último registro recebido\n", style="bold cyan")
    output.append(f"Fonte agora: {status} · {len(current.get('items', []))} fatores utilizáveis\n")
    if not record:
        output.append("Nenhum registro disponível nesta conexão.", style="dim")
        return output
    item = record["item"]
    evidence = item.get("evidence") or {}
    output.append(plain(item.get("question") or evidence.get("title") or "Sem título") + "\n")
    output.append(
        ("Observado: " if section == "news" else "Metadados observados: ")
        + when(item.get("source_observed_at") or item.get("available_at"))
        + "\n"
    )
    now = now or datetime.now(UTC)
    expired = timestamp(item.get("valid_until"))
    current_ids = {x.get("factor_id") for x in current.get("items", []) if x.get("factor_id")}
    is_current = bool(item.get("factor_id") and item.get("factor_id") in current_ids)
    if not is_current or (expired and expired < now):
        output.append(
            "REGISTRO ANTERIOR · não apresentado como fator atual elegível.\n", style="yellow"
        )
    if section == "news":
        output.append(
            f"{plain(evidence.get('source')) or 'Origem não informada'} · "
            f"Publicado: {when(evidence.get('published_at'))}\n"
        )
        if evidence.get("excerpt"):
            output.append(plain(evidence["excerpt"], 240) + "\n")
    else:
        prices = [
            timestamp(change.get("to_source_at"))
            for change in (item.get("probability_changes") or {}).values()
            if isinstance(change, dict)
        ]
        price_time = max((stamp for stamp in prices if stamp), default=None)
        output.append("Livro/preço observado: " + when(price_time) + "\n")
        output.append(
            f"Resultado: {plain(item.get('outcome')) or '—'} · "
            f"Prob. implícita: {numeric(item.get('implied_probability'), 1, 100)}% · "
            f"Spread: {numeric(item.get('spread_pp'))} pp\n"
        )
        changes = item.get("probability_changes") or {}
        output.append(
            "Variação: "
            + " · ".join(
                f"{window} {numeric(changes[window].get('change_pp'))} pp"
                if changes.get(window, {}).get("status") == "AVAILABLE"
                else f"{window} indisponível"
                for window in ("5m", "60m")
            )
            + "\n"
        )
        output.append("Resolução: " + when(item.get("end_date")) + "\n")
    direction = {
        "POSITIVE": "favorável",
        "NEGATIVE": "desfavorável",
        "MIXED": "mista",
        "NEUTRAL": "neutra",
        "UNDETERMINED": "indeterminada",
    }
    confidence = {
        "HIGH": "alta",
        "MODERATE": "moderada",
        "LOW": "baixa",
        "UNDETERMINED": "indeterminada",
    }
    classified_confidence = confidence.get(item.get("classification_confidence"), "não informada")
    output.append(
        f"Impacto classificado: {direction.get(item.get('impact_direction'), 'não informado')} · "
        f"Confiança da classificação: {classified_confidence}"
    )
    return output
