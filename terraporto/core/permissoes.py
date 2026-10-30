"""Controle de acesso por papel e por camada de informação (Estratégia V2, seção 09)."""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.utils import timezone


def eh_central(user) -> bool:
    return user.is_authenticated and user.eh_central


def central_required(view):
    @login_required
    @wraps(view)
    def _view(request, *args, **kwargs):
        if not eh_central(request.user):
            raise PermissionDenied("Acesso restrito à central.")
        return view(request, *args, **kwargs)

    return _view


def operador_required(view):
    """Central ou corretor credenciado (ativo/aprovado condicionado e com CRECI verificado)."""

    @login_required
    @wraps(view)
    def _view(request, *args, **kwargs):
        user = request.user
        if user.eh_central:
            return view(request, *args, **kwargs)
        corretor = user.perfil_corretor
        if corretor is None or not corretor.pode_operar:
            messages.info(request, "Seu credenciamento ainda não foi aprovado pela central.")
            return redirect("contas:aguardando")
        return view(request, *args, **kwargs)

    return _view


def pode_ver_completo(user, imovel) -> bool:
    """Central e captador veem o cadastro completo, inclusive dados do proprietário."""
    if user.eh_central:
        return True
    corretor = user.perfil_corretor
    return bool(corretor and imovel.captador_id == corretor.pk)


def negociacao_com_dossie(user, imovel):
    corretor = user.perfil_corretor
    if not corretor:
        return None
    return (
        imovel.negociacoes.filter(corretor_vendedor=corretor, dossie_liberado_ate__gte=timezone.now())
        .order_by("-dossie_liberado_ate")
        .first()
    )


def pode_ver_dossie(user, imovel) -> bool:
    return pode_ver_completo(user, imovel) or negociacao_com_dossie(user, imovel) is not None


def pode_ver_negociacao(user, negociacao) -> bool:
    if user.eh_central:
        return True
    corretor = user.perfil_corretor
    return bool(
        corretor and corretor.pk in (negociacao.corretor_vendedor_id, negociacao.imovel.captador_id)
    )


def pode_ver_contato_comprador(user, comprador) -> bool:
    """O contato do comprador fica com quem o registrou e com a central (Projeto, seção 11)."""
    if user.eh_central:
        return True
    corretor = user.perfil_corretor
    return bool(corretor and comprador.corretor_id == corretor.pk)
