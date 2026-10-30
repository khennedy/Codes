from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from contas.models import Corretor
from core import regras
from core.auditoria import registrar
from core.choices import APTIDOES
from core.forms import (
    AtribuirLeadForm,
    ConfiguracaoForm,
    LeadCompradorForm,
    LeadProprietarioForm,
    ParametroNivelFormSet,
    SimuladorCenariosForm,
    SimuladorVendaForm,
    ViabilidadeForm,
)
from core.models import Configuracao, LeadPublico, LogAuditoria, ParametroNivel
from core.permissoes import central_required, pode_ver_completo, pode_ver_dossie
from imoveis.models import ContratoRepresentacao, DocumentoChecklist, FotoImovel, Imovel
from negocios import servicos
from negocios.models import Comprador, Conflito, Negociacao


# ---------------------------------------------------------------------------
# Painel
# ---------------------------------------------------------------------------


@login_required
def painel(request):
    user = request.user
    if user.eh_central:
        return _painel_central(request)
    corretor = user.perfil_corretor
    if corretor is None or not corretor.pode_operar:
        return redirect("contas:aguardando")
    return _painel_corretor(request, corretor)


def _painel_central(request):
    hoje = timezone.localdate()
    contexto = {
        "ind": servicos.indicadores(),
        "funil": servicos.funil_por_etapa(Negociacao.objects.all()),
        "em_validacao": Imovel.objects.filter(status=Imovel.Status.EM_VALIDACAO).select_related("captador__usuario"),
        "exclusividades_vencendo": [
            c for c in ContratoRepresentacao.objects.filter(
                status=ContratoRepresentacao.Status.VIGENTE, data_fim__gte=hoje,
                data_fim__lte=hoje + timezone.timedelta(days=30),
            ).select_related("imovel")
        ],
        "revisoes_preco": Imovel.objects.filter(publicado=True, revisar_preco_em__lte=hoje),
        "duplicidades": Comprador.objects.exclude(duplicidade_de=None).select_related(
            "corretor__usuario", "duplicidade_de__corretor__usuario"
        ).filter(conflitos=None),
        "dossies_solicitados": Negociacao.objects.exclude(dossie_solicitado_em=None).filter(
            dossie_liberado_ate=None
        ).select_related("imovel", "corretor_vendedor__usuario"),
        "conflitos": Conflito.objects.exclude(status__in=Conflito.STATUS_ENCERRADOS)[:5],
        "corretores_pendentes": Corretor.objects.filter(
            status__in=[Corretor.Status.INSCRITO, Corretor.Status.EM_ANALISE]
        ).select_related("usuario"),
        "leads": LeadPublico.objects.filter(status=LeadPublico.Status.NOVO)[:5],
    }
    return render(request, "core/painel_central.html", contexto)


def _painel_corretor(request, corretor):
    hoje = timezone.localdate()
    minhas = Negociacao.objects.filter(corretor_vendedor=corretor)
    params = ParametroNivel.como_regras()
    volume = corretor.volume_12_meses()
    contexto = {
        "corretor": corretor,
        "captacoes": corretor.captacoes.all()[:8],
        "negociacoes": minhas.filter(etapa__in=Negociacao.ETAPAS_ABERTAS).select_related("imovel", "comprador")[:8],
        "funil": servicos.funil_por_etapa(minhas),
        "protecao_vencendo": corretor.compradores.filter(
            protecao_ate__gte=hoje, protecao_ate__lte=hoje + timezone.timedelta(days=7)
        ),
        "interesse_nos_meus": Negociacao.objects.filter(imovel__captador=corretor).exclude(
            corretor_vendedor=corretor).filter(etapa__in=Negociacao.ETAPAS_ABERTAS).select_related(
            "imovel", "corretor_vendedor__usuario"),
        "volume_12m": volume,
        "nivel_sugerido": dict(Corretor.Nivel.choices)[regras.nivel_sugerido(volume, params)],
        "mensalidade_pendente": corretor.mensalidades.filter(status="pendente").first(),
        "novidades": servicos.imoveis_catalogo().exclude(captador=corretor)[:4],
    }
    return render(request, "core/painel_corretor.html", contexto)


# ---------------------------------------------------------------------------
# Vitrine pública (teaser com informações mínimas — Estratégia V2, seção 09)
# ---------------------------------------------------------------------------


def vitrine(request):
    imoveis = servicos.imoveis_catalogo().prefetch_related("fotos")
    aptidao = request.GET.get("aptidao", "")
    if aptidao:
        imoveis = imoveis.filter(aptidoes__contains=aptidao)
    imoveis = list(imoveis)
    for imovel in imoveis:
        imovel.capa = next((f for f in imovel.fotos.all() if f.publica and f.autorizada), None)
    return render(request, "core/vitrine.html", {"imoveis": imoveis, "aptidao": aptidao, "aptidoes": APTIDOES})


def vitrine_detalhe(request, codigo):
    imovel = get_object_or_404(servicos.imoveis_catalogo(), codigo=codigo)
    form = LeadCompradorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        lead = form.save(commit=False)
        lead.tipo = LeadPublico.Tipo.COMPRADOR
        lead.imovel = imovel
        lead.save()
        return render(request, "core/obrigado.html", {"lead": lead})
    fotos = imovel.fotos.filter(publica=True, autorizada=True)
    return render(request, "core/vitrine_detalhe.html", {"imovel": imovel, "form": form, "fotos": fotos})


def quero_vender(request):
    form = LeadProprietarioForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        lead = form.save(commit=False)
        lead.tipo = LeadPublico.Tipo.PROPRIETARIO
        lead.save()
        return render(request, "core/obrigado.html", {"lead": lead})
    return render(request, "core/quero_vender.html", {"form": form})


# ---------------------------------------------------------------------------
# Leads, configurações e auditoria (central)
# ---------------------------------------------------------------------------


@central_required
def leads(request):
    return render(request, "core/leads.html", {"leads": LeadPublico.objects.select_related("imovel", "atribuido_a__usuario")})


@central_required
@transaction.atomic
def lead_atribuir(request, pk):
    lead = get_object_or_404(LeadPublico, pk=pk, status=LeadPublico.Status.NOVO)
    form = AtribuirLeadForm(request.POST or None)
    if request.method == "POST":
        if "descartar" in request.POST:
            lead.status = LeadPublico.Status.DESCARTADO
            lead.save()
            registrar(request.user, "lead_descartado", lead)
            return redirect("core:leads")
        if form.is_valid():
            corretor = form.cleaned_data["corretor"]
            lead.status = LeadPublico.Status.ATRIBUIDO
            lead.atribuido_a = corretor
            lead.save()
            if lead.tipo == LeadPublico.Tipo.COMPRADOR:
                comprador = Comprador(
                    nome=lead.nome, telefone=lead.telefone, email=lead.email, municipio=lead.municipio,
                    corretor=corretor, origem=Comprador.Origem.REDE, consentimento_lgpd=lead.consentimento,
                    observacoes=f"Lead da vitrine: {lead.mensagem}",
                    evidencia_relacionamento="Contato recebido pela vitrine pública e distribuído pela central.",
                )
                servicos.registrar_comprador(comprador)
                if lead.imovel:
                    negociacao = Negociacao.objects.create(
                        imovel=lead.imovel, comprador=comprador, corretor_vendedor=corretor,
                        situacao=regras.SITUACAO_B if corretor != lead.imovel.captador else regras.SITUACAO_C,
                    )
                    servicos.registrar_atividade(negociacao, request.user, "registro", "Lead da vitrine atribuído pela central.")
            registrar(request.user, "lead_atribuido", lead, f"Atribuído a {corretor}")
            messages.success(request, f"Lead atribuído a {corretor.nome}.")
            return redirect("core:leads")
    return render(request, "core/lead_atribuir.html", {"lead": lead, "form": form})


@central_required
def configuracoes(request):
    config = Configuracao.atual()
    form = ConfiguracaoForm(request.POST or None, instance=config)
    formset = ParametroNivelFormSet(request.POST or None, queryset=ParametroNivel.objects.all())
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        form.save()
        formset.save()
        registrar(request.user, "configuracao_alterada", config, ", ".join(form.changed_data))
        messages.success(request, "Configurações salvas.")
        return redirect("core:configuracoes")
    return render(request, "core/configuracoes.html", {"form": form, "formset": formset})


@central_required
def auditoria(request):
    logs = LogAuditoria.objects.select_related("usuario")
    acao = request.GET.get("acao")
    if acao:
        logs = logs.filter(acao=acao)
    acoes = LogAuditoria.objects.order_by("acao").values_list("acao", flat=True).distinct()
    return render(request, "core/auditoria.html", {"logs": logs[:300], "acoes": acoes, "acao": acao})


# ---------------------------------------------------------------------------
# Simulador econômico (Estratégia V2, seções 11 e 19)
# ---------------------------------------------------------------------------


@login_required
def simulador(request):
    config = Configuracao.atual()
    params = ParametroNivel.como_regras()
    aba = request.GET.get("aba", "venda")
    dados = request.GET if "simular" in request.GET else None

    venda_form = SimuladorVendaForm(dados if aba == "venda" else None, initial={"modelo": config.modelo_rateio})
    cenarios_form = SimuladorCenariosForm(dados if aba == "cenarios" else None)
    viab_form = ViabilidadeForm(dados if aba == "viabilidade" else None)

    rateio = None
    comparativo = []
    form_venda = venda_form if venda_form.is_bound and venda_form.is_valid() else None
    v = form_venda.cleaned_data if form_venda else {
        f: venda_form.fields[f].initial for f in venda_form.fields
    }
    v["modelo"] = v.get("modelo") or config.modelo_rateio
    rateio = regras.calcular_rateio(
        v["valor_venda"], v["comissao_pct"], captador_id=1, captador_nivel=v["nivel_captador"],
        vendedor_id=2, vendedor_nivel=v["nivel_vendedor"], modelo=v["modelo"], parametros=params,
        pct_regulamento=config.pct_regulamento,
    )
    for nivel in regras.NIVEIS:
        r = regras.calcular_rateio(
            v["valor_venda"], v["comissao_pct"], captador_id=1, captador_nivel=nivel, vendedor_id=2,
            vendedor_nivel=nivel, modelo=regras.MODELO_NIVEL, parametros=params,
        )
        comparativo.append((regras.ROTULO_NIVEL[nivel], r, params[nivel].mensalidade))

    c = cenarios_form.cleaned_data if cenarios_form.is_bound and cenarios_form.is_valid() else {
        f: cenarios_form.fields[f].initial for f in cenarios_form.fields
    }
    cenarios = []
    for nome, chave in (("Piloto", "piloto"), ("Base", "base"), ("Escala", "escala")):
        vgv = Decimal(c[f"vendas_{chave}"]) * Decimal(c[f"ticket_{chave}"])
        comissao = vgv * config.comissao_referencia_pct / 100
        central = comissao * Decimal(c["pct_central"]) / 100
        cenarios.append({"nome": nome, "vendas": c[f"vendas_{chave}"], "ticket": c[f"ticket_{chave}"], "vgv": vgv,
                         "comissao": comissao, "central": central})
    recorrente = Decimal(c["corretores"]) * Decimal(c["mensalidade_media"]) * 12

    viab = viab_form.cleaned_data if viab_form.is_bound and viab_form.is_valid() else {
        f: viab_form.fields[f].initial for f in viab_form.fields
    }
    viabilidade = regras.simular_viabilidade(**viab)

    return render(request, "core/simulador.html", {
        "aba": aba, "venda_form": venda_form, "cenarios_form": cenarios_form, "viab_form": viab_form,
        "rateio": rateio, "comparativo": comparativo, "cenarios": cenarios, "recorrente": recorrente,
        "viabilidade": viabilidade, "params": ParametroNivel.objects.all(), "config": config,
    })


# ---------------------------------------------------------------------------
# Arquivos protegidos e minutas
# ---------------------------------------------------------------------------


def arquivo_foto(request, pk):
    foto = get_object_or_404(FotoImovel.objects.select_related("imovel"), pk=pk)
    publico = foto.publica and foto.autorizada and foto.imovel.publicado
    if not publico:
        if not request.user.is_authenticated:
            raise PermissionDenied
        corretor = request.user.perfil_corretor
        no_catalogo = foto.autorizada and foto.imovel.publicado and corretor is not None and corretor.pode_operar
        if not (no_catalogo or pode_ver_completo(request.user, foto.imovel)):
            raise PermissionDenied
    if not foto.arquivo:
        raise Http404
    return FileResponse(foto.arquivo.open("rb"))


@login_required
def arquivo_documento(request, pk):
    doc = get_object_or_404(DocumentoChecklist.objects.select_related("imovel"), pk=pk)
    if not pode_ver_dossie(request.user, doc.imovel) or not doc.arquivo:
        raise PermissionDenied
    registrar(request.user, "download_documento", doc.imovel, doc.descricao)
    return FileResponse(doc.arquivo.open("rb"), as_attachment=True)


@login_required
def minuta_associacao(request, pk):
    corretor = get_object_or_404(Corretor.objects.select_related("usuario"), pk=pk)
    if not (request.user.eh_central or request.user.perfil_corretor == corretor):
        raise PermissionDenied
    params = ParametroNivel.como_regras()[corretor.nivel]
    return render(request, "documentos/minuta_associacao.html", {
        "corretor": corretor, "config": Configuracao.atual(), "params": params, "hoje": timezone.localdate(),
    })


@login_required
def minuta_representacao(request, pk):
    contrato = get_object_or_404(ContratoRepresentacao.objects.select_related("imovel__proprietario"), pk=pk)
    if not pode_ver_completo(request.user, contrato.imovel):
        raise PermissionDenied
    return render(request, "documentos/minuta_representacao.html", {
        "contrato": contrato, "imovel": contrato.imovel, "proprietario": contrato.imovel.proprietario,
        "config": Configuracao.atual(), "hoje": timezone.localdate(),
    })
