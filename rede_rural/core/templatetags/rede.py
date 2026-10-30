from decimal import Decimal, InvalidOperation

from django import template
from django.utils.html import format_html

register = template.Library()


def _formatar(valor, casas: int) -> str:
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


def _decimal(valor):
    if valor in (None, ""):
        return None
    try:
        return Decimal(valor)
    except (InvalidOperation, TypeError, ValueError):
        return None


@register.filter
def brl(valor):
    """R$ 1.234.567,89 — campos vazios aparecem como 'não informado'."""
    numero = _decimal(valor)
    if numero is None:
        return "não informado"
    sinal = "−" if numero < 0 else ""
    return f"{sinal}R$ " + _formatar(abs(numero), 2)


@register.filter
def brl_curto(valor):
    numero = _decimal(valor)
    if numero is None:
        return "—"
    if abs(numero) >= 1_000_000:
        return "R$ " + _formatar(numero / 1_000_000, 1) + " mi"
    if abs(numero) >= 1_000:
        return "R$ " + _formatar(numero / 1_000, 0) + " mil"
    return "R$ " + _formatar(numero, 0)


@register.filter
def numero(valor, casas=0):
    numero_ = _decimal(valor)
    if numero_ is None:
        return "não informado"
    return _formatar(numero_, int(casas))


@register.filter
def ha(valor):
    numero_ = _decimal(valor)
    if numero_ is None:
        return "não informado"
    return _formatar(numero_, 2 if numero_ % 1 else 0) + " ha"


@register.filter
def pct(valor):
    numero_ = _decimal(valor)
    if numero_ is None:
        return "—"
    return _formatar(numero_, 2 if numero_ % 1 else 0) + "%"


@register.filter
def info(valor):
    """Mostra 'não informado' para campos vazios, sem preenchimento inventado (Estratégia V2, seção 08)."""
    if valor in (None, ""):
        return format_html('<span class="nao-informado">não informado</span>')
    if valor is True:
        return "Sim"
    if valor is False:
        return "Não"
    return valor


@register.filter
def unidade(valor, sufixo):
    """'920 m' ou 'não informado' — evita textos como 'não informado m'."""
    if valor in (None, ""):
        return format_html('<span class="nao-informado">não informado</span>')
    numero_ = _decimal(valor)
    texto = _formatar(numero_, 2 if numero_ % 1 else 0) if numero_ is not None else valor
    return f"{texto} {sufixo}"


@register.filter
def selo(texto, classe=""):
    return format_html('<span class="selo selo-{}">{}</span>', classe or texto, texto)


@register.simple_tag
def status_selo(obj, campo="status"):
    valor = getattr(obj, campo)
    rotulo = getattr(obj, f"get_{campo}_display")()
    return format_html('<span class="selo selo-{}">{}</span>', valor, rotulo)


@register.filter
def get(dicionario, chave):
    return dicionario.get(chave) if hasattr(dicionario, "get") else None


@register.simple_tag(takes_context=True)
def ativo(context, nome_url):
    """Classe 'ativo' para o item de menu da página atual."""
    from django.urls import reverse

    request = context.get("request")
    if request is None:
        return ""
    caminho = reverse(nome_url)
    return "ativo" if request.path.startswith(caminho) else ""
