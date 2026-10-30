from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from contas.forms import CorretorCentralForm, InscricaoForm, PerfilForm
from contas.models import Corretor, Mensalidade, ProgressoTrilha, Trilha
from core import regras
from core.auditoria import historico, registrar
from core.models import Configuracao, ParametroNivel
from core.permissoes import central_required, operador_required
from negocios.models import Negociacao


def inscricao(request):
    if request.user.is_authenticated:
        return redirect("core:painel")
    form = InscricaoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.save()
        registrar(usuario, "inscricao_corretor", usuario.corretor)
        login(request, usuario)
        messages.success(request, "Inscrição recebida. A central vai verificar seu CRECI e entrar em contato.")
        return redirect("contas:aguardando")
    return render(request, "contas/inscricao.html", {"form": form})


@login_required
def aguardando(request):
    corretor = request.user.perfil_corretor
    if request.user.eh_central or (corretor and corretor.pode_operar):
        return redirect("core:painel")
    obrigatorias = Trilha.objects.filter(obrigatoria_ingresso=True)
    return render(request, "contas/aguardando.html", {"corretor": corretor, "obrigatorias": obrigatorias})


@central_required
def corretores(request):
    lista = Corretor.objects.select_related("usuario").annotate(
        n_captacoes=Count("captacoes", distinct=True),
        n_negociacoes=Count("vendas", filter=Q(vendas__etapa__in=Negociacao.ETAPAS_ABERTAS), distinct=True),
    )
    status = request.GET.get("status")
    if status:
        lista = lista.filter(status=status)
    return render(request, "contas/corretores.html", {
        "corretores": lista, "status": status, "status_choices": Corretor.Status.choices,
    })


@operador_required
def corretor_detalhe(request, pk=None):
    if pk is None:
        corretor = request.user.perfil_corretor
        if corretor is None:
            return redirect("contas:corretores")
    else:
        corretor = get_object_or_404(Corretor.objects.select_related("usuario"), pk=pk)
        if not request.user.eh_central and corretor != request.user.perfil_corretor:
            return redirect("contas:meu_perfil")
    params = ParametroNivel.como_regras()
    volume = corretor.volume_12_meses()
    sugerido = regras.nivel_sugerido(volume, params)
    form = None
    if request.user.eh_central:
        form = CorretorCentralForm(request.POST or None, instance=corretor)
        if request.method == "POST" and form.is_valid():
            antes = Corretor.objects.get(pk=corretor.pk)
            corretor = form.save()
            if corretor.status in Corretor.STATUS_OPERANTES and not corretor.data_adesao:
                corretor.data_adesao = timezone.localdate()
                corretor.save(update_fields=["data_adesao"])
            mudancas = [f"{c}: {getattr(antes, c)} → {getattr(corretor, c)}" for c in form.changed_data]
            registrar(request.user, "corretor_atualizado", corretor, "; ".join(mudancas))
            messages.success(request, "Credenciamento atualizado.")
            return redirect("contas:corretor", pk=corretor.pk)
    else:
        form = PerfilForm(request.POST or None, instance=corretor)
        if request.method == "POST" and form.is_valid():
            form.save()
            messages.success(request, "Perfil atualizado.")
            return redirect("contas:meu_perfil")
    return render(request, "contas/corretor.html", {
        "corretor": corretor,
        "form": form,
        "volume": volume,
        "nivel_sugerido": dict(Corretor.Nivel.choices)[sugerido],
        "params": params[corretor.nivel],
        "progresso": corretor.trilhas.select_related("trilha"),
        "mensalidades": corretor.mensalidades.all()[:6],
        "historico": historico(corretor),
    })


@operador_required
def universidade(request):
    corretor = request.user.perfil_corretor
    progresso = {}
    if corretor:
        progresso = {p.trilha_id: p for p in corretor.trilhas.all()}
    pendentes = ProgressoTrilha.objects.none()
    if request.user.eh_central:
        pendentes = ProgressoTrilha.objects.filter(status=ProgressoTrilha.Status.AGUARDANDO).select_related(
            "corretor__usuario", "trilha")
    trilhas = [(t, progresso.get(t.pk)) for t in Trilha.objects.all()]
    return render(request, "contas/universidade.html", {"trilhas": trilhas, "pendentes": pendentes})


@operador_required
@require_POST
def trilha_acao(request, pk):
    trilha = get_object_or_404(Trilha, pk=pk)
    acao = request.POST.get("acao")
    if acao == "validar" and request.user.eh_central:
        progresso = get_object_or_404(ProgressoTrilha, pk=request.POST.get("progresso"))
        progresso.status = ProgressoTrilha.Status.CONCLUIDO
        progresso.validado_por = request.user
        progresso.save()
        registrar(request.user, "trilha_validada", progresso.corretor, trilha.nome)
    elif request.user.perfil_corretor:
        progresso, _ = ProgressoTrilha.objects.get_or_create(corretor=request.user.perfil_corretor, trilha=trilha)
        if acao == "concluir":
            progresso.status = ProgressoTrilha.Status.AGUARDANDO
            progresso.concluido_em = timezone.localdate()
            progresso.save()
    return redirect("contas:universidade")


@operador_required
def mensalidades(request):
    if request.user.eh_central:
        lista = Mensalidade.objects.select_related("corretor__usuario")
    else:
        lista = request.user.perfil_corretor.mensalidades.all()
    return render(request, "contas/mensalidades.html", {"mensalidades": lista[:200]})


@central_required
@require_POST
def gerar_mensalidades(request):
    """Gera a mensalidade do mês para corretores ativos, conforme o valor do nível."""
    config = Configuracao.atual()
    params = ParametroNivel.como_regras()
    hoje = timezone.localdate()
    competencia = hoje.replace(day=1)
    vencimento = competencia.replace(day=min(config.dia_vencimento_mensalidade, 28))
    criadas = 0
    for corretor in Corretor.objects.filter(status__in=Corretor.STATUS_OPERANTES):
        _, nova = Mensalidade.objects.get_or_create(
            corretor=corretor, competencia=competencia,
            defaults={"valor": params[corretor.nivel].mensalidade, "vencimento": vencimento},
        )
        criadas += nova
    registrar(request.user, "mensalidades_geradas", None, f"{criadas} mensalidades de {competencia:%m/%Y}")
    messages.success(request, f"{criadas} mensalidade(s) gerada(s) para {competencia:%m/%Y}.")
    return redirect("contas:mensalidades")


@central_required
@require_POST
def mensalidade_status(request, pk):
    mensalidade = get_object_or_404(Mensalidade, pk=pk)
    novo = request.POST.get("status")
    if novo in Mensalidade.Status.values:
        mensalidade.status = novo
        mensalidade.paga_em = timezone.localdate() if novo == Mensalidade.Status.PAGA else None
        mensalidade.save()
        registrar(request.user, "mensalidade_" + novo, mensalidade.corretor, f"{mensalidade.competencia:%m/%Y}")
    return redirect("contas:mensalidades")
