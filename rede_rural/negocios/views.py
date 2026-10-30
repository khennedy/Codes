from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core import regras
from core.auditoria import historico, registrar
from core.models import Configuracao
from core.permissoes import (
    central_required,
    operador_required,
    pode_ver_contato_comprador,
    pode_ver_negociacao,
)
from imoveis.models import Imovel
from negocios import servicos
from negocios.forms import (
    ApuracaoStatusForm,
    AtividadeForm,
    CompradorForm,
    ConflitoDecisaoForm,
    ConflitoForm,
    DemandaForm,
    EncaminhamentoForm,
    EncaminhamentoStatusForm,
    EtapaForm,
    NegociacaoForm,
    ParticipacaoFormSet,
    VisitaForm,
)
from negocios.models import (
    ApuracaoComissao,
    Comprador,
    Conflito,
    Demanda,
    EncaminhamentoCredito,
    Negociacao,
    Visita,
)


def _comprador_proprio(request, pk):
    comprador = get_object_or_404(Comprador.objects.select_related("corretor__usuario"), pk=pk)
    if not pode_ver_contato_comprador(request.user, comprador):
        raise PermissionDenied
    return comprador


def _negociacao(request, pk):
    negociacao = get_object_or_404(
        Negociacao.objects.select_related("imovel__captador__usuario", "comprador", "corretor_vendedor__usuario"),
        pk=pk,
    )
    if not pode_ver_negociacao(request.user, negociacao):
        raise PermissionDenied
    return negociacao


# ---------------------------------------------------------------------------
# Compradores e demandas
# ---------------------------------------------------------------------------


@operador_required
def compradores(request):
    lista = Comprador.objects.select_related("corretor__usuario", "duplicidade_de")
    if not request.user.eh_central:
        lista = lista.filter(corretor=request.user.perfil_corretor)
    return render(request, "negocios/compradores.html", {"compradores": lista, "hoje": timezone.localdate()})


@operador_required
def comprador_form(request, pk=None):
    instancia = _comprador_proprio(request, pk) if pk else None
    form = CompradorForm(request.POST or None, instance=instancia, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        comprador = form.save(commit=False)
        if not request.user.eh_central and not pk:
            comprador.corretor = request.user.perfil_corretor
        if pk:
            comprador.save()
        else:
            duplicados = servicos.registrar_comprador(comprador)
            if duplicados:
                primeiro = duplicados[0]
                messages.warning(
                    request,
                    f"Possível duplicidade: este comprador já foi registrado por {primeiro.corretor.nome} em "
                    f"{primeiro.criado_em:%d/%m/%Y}, com prioridade até {primeiro.protecao_ate:%d/%m/%Y}. "
                    "Seu registro foi mantido, sem prioridade, e será analisado pela central "
                    "(Regulamento de Proteção, seção 5).",
                )
            else:
                messages.success(
                    request, f"Comprador registrado com prioridade comercial até {comprador.protecao_ate:%d/%m/%Y}."
                )
        registrar(request.user, "comprador_salvo", comprador)
        return redirect(comprador)
    return render(request, "core/form_pagina.html", {
        "form": form, "titulo": "Editar comprador" if pk else "Registrar comprador", "voltar": "negocios:compradores",
        "aviso": "O registro não significa propriedade sobre o cliente: é evidência de participação comercial. "
                 "Cadastro progressivo — peça só o necessário em cada etapa.",
    })


@operador_required
def comprador_detalhe(request, pk):
    comprador = _comprador_proprio(request, pk)
    demandas = comprador.demandas.all()
    compat = {d.pk: servicos.compatibilidades_da_demanda(d) for d in demandas if d.ativa}
    return render(request, "negocios/comprador.html", {
        "comprador": comprador,
        "demandas": [(d, compat.get(d.pk, [])) for d in demandas],
        "negociacoes": comprador.negociacoes.select_related("imovel"),
        "encaminhamentos": comprador.encaminhamentos.all(),
        "duplicidades": comprador.possiveis_duplicidades().select_related("corretor__usuario"),
        "config": Configuracao.atual(),
    })


@operador_required
def demanda_form(request, comprador_pk, pk=None):
    comprador = _comprador_proprio(request, comprador_pk)
    instancia = get_object_or_404(Demanda, pk=pk, comprador=comprador) if pk else None
    form = DemandaForm(request.POST or None, instance=instancia)
    if request.method == "POST" and form.is_valid():
        demanda = form.save(commit=False)
        demanda.comprador = comprador
        demanda.save()
        if comprador.etapa_cadastro < Comprador.Etapa.PERFIL:
            Comprador.objects.filter(pk=comprador.pk).update(etapa_cadastro=Comprador.Etapa.PERFIL)
        messages.success(request, "Perfil de busca salvo. Veja as compatibilidades abaixo.")
        return redirect(comprador)
    return render(request, "core/form_pagina.html", {
        "form": form, "titulo": f"Perfil de busca — {comprador.nome}", "voltar_obj": comprador,
        "aviso": "Segunda etapa do cadastro: perfil produtivo, região, orçamento, área e horizonte.",
    })


# ---------------------------------------------------------------------------
# Negociações (funil)
# ---------------------------------------------------------------------------


@operador_required
def funil(request):
    negociacoes = Negociacao.objects.select_related("imovel", "comprador", "corretor_vendedor__usuario")
    if not request.user.eh_central:
        corretor = request.user.perfil_corretor
        negociacoes = negociacoes.filter(corretor_vendedor=corretor)
    colunas = [
        (valor, rotulo, [n for n in negociacoes if n.etapa == valor]) for valor, rotulo in Negociacao.Etapa.choices
    ]
    return render(request, "negocios/funil.html", {"colunas": colunas})


@operador_required
def negociacao_nova(request):
    inicial = {k: request.GET[k] for k in ("imovel", "comprador") if request.GET.get(k)}
    form = NegociacaoForm(request.POST or None, usuario=request.user, initial=inicial)
    if request.method == "POST" and form.is_valid():
        negociacao = form.save(commit=False)
        if not request.user.eh_central:
            negociacao.corretor_vendedor = request.user.perfil_corretor
        if negociacao.corretor_vendedor_id == negociacao.imovel.captador_id and negociacao.situacao == regras.SITUACAO_B:
            negociacao.situacao = regras.SITUACAO_C
        negociacao.save()
        servicos.registrar_atividade(
            negociacao, request.user, "registro",
            f"Comprador registrado para o imóvel {negociacao.imovel.codigo} por {negociacao.corretor_vendedor.nome}.",
        )
        registrar(request.user, "negociacao_registrada", negociacao)
        messages.success(request, "Oportunidade registrada. A data e a hora deste registro são a sua evidência de origem.")
        return redirect(negociacao)
    return render(request, "core/form_pagina.html", {
        "form": form, "titulo": "Registrar comprador para um imóvel", "voltar": "negocios:funil",
        "aviso": "Registre a oportunidade antes de visitas, propostas ou pedido de acesso ao dossiê "
                 "(Regulamento de Proteção, seção 4).",
    })


@operador_required
def negociacao_detalhe(request, pk):
    negociacao = _negociacao(request, pk)
    etapa_form = EtapaForm(instance=negociacao)
    return render(request, "negocios/negociacao.html", {
        "n": negociacao,
        "etapa_form": etapa_form,
        "atividade_form": AtividadeForm(),
        "atividades": negociacao.atividades.select_related("autor"),
        "visitas": negociacao.visitas.select_related("corretor__usuario"),
        "apuracao": getattr(negociacao, "apuracao", None),
        "conflitos": negociacao.conflitos.all(),
        "ve_contato": pode_ver_contato_comprador(request.user, negociacao.comprador),
        "eh_vendedor": request.user.perfil_corretor == negociacao.corretor_vendedor,
        "config": Configuracao.atual(),
        "historico": historico(negociacao),
    })


@operador_required
@require_POST
@transaction.atomic
def negociacao_etapa(request, pk):
    negociacao = _negociacao(request, pk)
    etapa_anterior = negociacao.get_etapa_display()
    form = EtapaForm(request.POST, instance=negociacao)
    if not form.is_valid():
        for erros in form.errors.values():
            for erro in erros:
                messages.error(request, erro)
        return redirect(negociacao)
    negociacao = form.save()
    if "etapa" in form.changed_data:
        servicos.registrar_atividade(
            negociacao, request.user, "etapa", f"Etapa: {etapa_anterior} → {negociacao.get_etapa_display()}"
        )
        registrar(request.user, "etapa_alterada", negociacao, negociacao.get_etapa_display())
        if negociacao.etapa == Negociacao.Etapa.CONCLUIDO:
            imovel = negociacao.imovel
            imovel.status = Imovel.Status.VENDIDO
            imovel.publicado = False
            imovel.save(update_fields=["status", "publicado"])
            servicos.gerar_apuracao(negociacao)
            messages.success(request, "Negócio concluído: imóvel retirado do catálogo e comissão apurada.")
    return redirect(negociacao)


@operador_required
@require_POST
def negociacao_atividade(request, pk):
    negociacao = _negociacao(request, pk)
    form = AtividadeForm(request.POST)
    if form.is_valid():
        atividade = servicos.registrar_atividade(
            negociacao, request.user, form.cleaned_data["tipo"], form.cleaned_data["descricao"]
        )
        if atividade.renova_protecao:
            messages.success(request, "Atividade registrada; a prioridade comercial do comprador foi renovada.")
    return redirect(negociacao)


@operador_required
@require_POST
def dossie_solicitar(request, pk):
    negociacao = _negociacao(request, pk)
    if request.user.perfil_corretor != negociacao.corretor_vendedor:
        raise PermissionDenied
    negociacao.dossie_solicitado_em = timezone.now()
    negociacao.save(update_fields=["dossie_solicitado_em"])
    registrar(request.user, "dossie_solicitado", negociacao)
    messages.success(request, "Pedido de acesso ao data room enviado à central.")
    return redirect(negociacao)


@central_required
@require_POST
def dossie_liberar(request, pk):
    negociacao = get_object_or_404(Negociacao, pk=pk)
    if request.POST.get("acao") == "revogar":
        negociacao.dossie_liberado_ate = None
        negociacao.dossie_solicitado_em = None
        registrar(request.user, "dossie_revogado", negociacao)
    else:
        dias = Configuracao.atual().dias_acesso_dossie
        negociacao.dossie_liberado_ate = timezone.now() + timezone.timedelta(days=dias)
        registrar(request.user, "dossie_liberado", negociacao, f"{dias} dias")
        messages.success(request, f"Data room liberado por {dias} dias para {negociacao.corretor_vendedor.nome}.")
    negociacao.save(update_fields=["dossie_liberado_ate", "dossie_solicitado_em"])
    voltar = request.POST.get("voltar")
    if not url_has_allowed_host_and_scheme(voltar, allowed_hosts={request.get_host()}):
        voltar = negociacao.get_absolute_url()
    return redirect(voltar)


@operador_required
def visita_form(request, pk, visita_pk=None):
    negociacao = _negociacao(request, pk)
    visita = get_object_or_404(Visita, pk=visita_pk, negociacao=negociacao) if visita_pk else None
    form = VisitaForm(request.POST or None, instance=visita)
    if request.method == "POST" and form.is_valid():
        visita = form.save(commit=False)
        visita.negociacao = negociacao
        if not visita_pk:
            visita.corretor = request.user.perfil_corretor or negociacao.corretor_vendedor
        visita.save()
        tipo = "visita" if visita.realizada else "visita_agendada"
        servicos.registrar_atividade(negociacao, request.user, tipo,
                                     f"{'Visita realizada' if visita.realizada else 'Visita agendada'} em "
                                     f"{timezone.localtime(visita.data_hora):%d/%m/%Y %H:%M}: {visita.objetivo}")
        if negociacao.etapa in (Negociacao.Etapa.NOVO, Negociacao.Etapa.QUALIFICADO, Negociacao.Etapa.VISITA_AGENDADA):
            negociacao.etapa = Negociacao.Etapa.VISITADO if visita.realizada else Negociacao.Etapa.VISITA_AGENDADA
            negociacao.save(update_fields=["etapa"])
        messages.success(request, "Visita registrada.")
        return redirect(negociacao)
    return render(request, "core/form_pagina.html", {
        "form": form, "titulo": f"Visita — {negociacao}", "voltar_obj": negociacao,
        "aviso": "Relatório de visita comercial (Anexo II). Não misture com o dossiê do imóvel.",
    })


@operador_required
def visita_relatorio(request, pk):
    visita = get_object_or_404(Visita.objects.select_related("negociacao__imovel", "negociacao__comprador"), pk=pk)
    if not pode_ver_negociacao(request.user, visita.negociacao):
        raise PermissionDenied
    return render(request, "documentos/relatorio_visita.html", {"v": visita, "n": visita.negociacao})


@central_required
def apuracao(request, pk):
    negociacao = get_object_or_404(Negociacao, pk=pk)
    if request.method == "POST" and request.POST.get("acao") == "recalcular":
        servicos.gerar_apuracao(negociacao)
        registrar(request.user, "apuracao_recalculada", negociacao)
        return redirect("negocios:apuracao", pk=pk)
    apuracao = getattr(negociacao, "apuracao", None) or servicos.gerar_apuracao(negociacao)
    status_form = ApuracaoStatusForm(request.POST or None, instance=apuracao)
    formset = ParticipacaoFormSet(request.POST or None, instance=apuracao)
    if request.method == "POST" and status_form.is_valid() and formset.is_valid():
        total_pct = sum(
            f.cleaned_data.get("percentual") or 0
            for f in formset.forms if f.cleaned_data and not f.cleaned_data.get("DELETE")
        )
        if total_pct != 100:
            messages.error(request, f"Os percentuais somam {total_pct}%; o rateio precisa fechar em 100%.")
        elif status_form.cleaned_data["status"] in (ApuracaoComissao.Status.APROVADA,) and negociacao.em_disputa:
            messages.error(request, "Há conflito em análise: o rateio fica suspenso até a decisão.")
        else:
            with transaction.atomic():
                status_form.save()
                participacoes = formset.save(commit=False)
                for p in participacoes:
                    p.valor = regras.dinheiro(apuracao.comissao_total * p.percentual / 100)
                    p.save()
                for p in formset.deleted_objects:
                    p.delete()
                # Ajuste de centavos na central para fechar exatamente o total
                diferenca = apuracao.comissao_total - apuracao.soma_participacoes
                central = apuracao.participacoes.filter(papel="central").first()
                if diferenca and central:
                    central.valor += diferenca
                    central.save()
            registrar(request.user, "apuracao_atualizada", negociacao, apuracao.get_status_display())
            messages.success(request, "Rateio salvo.")
            return redirect("negocios:apuracao", pk=pk)
    return render(request, "negocios/apuracao.html", {
        "n": negociacao, "apuracao": apuracao, "status_form": status_form, "formset": formset,
        "situacao": regras.DESCRICAO_SITUACAO.get(negociacao.situacao),
    })


# ---------------------------------------------------------------------------
# Conflitos
# ---------------------------------------------------------------------------


@operador_required
def conflitos(request):
    lista = Conflito.objects.select_related("reclamante").prefetch_related("envolvidos__usuario")
    if not request.user.eh_central:
        corretor = request.user.perfil_corretor
        lista = (lista.filter(reclamante=request.user) | lista.filter(envolvidos=corretor)).distinct()
    return render(request, "negocios/conflitos.html", {"conflitos": lista})


@operador_required
def conflito_novo(request):
    inicial = {k: request.GET[k] for k in ("negociacao", "comprador", "imovel", "tipo") if request.GET.get(k)}
    form = ConflitoForm(request.POST or None, usuario=request.user, initial=inicial)
    if request.method == "POST" and form.is_valid():
        conflito = form.save(commit=False)
        conflito.reclamante = request.user
        conflito.save()
        form.save_m2m()
        if conflito.negociacao and hasattr(conflito.negociacao, "apuracao"):
            ApuracaoComissao.objects.filter(negociacao=conflito.negociacao).exclude(
                status__in=[ApuracaoComissao.Status.RECEBIDA, ApuracaoComissao.Status.REPASSADA]
            ).update(status=ApuracaoComissao.Status.SUSPENSA)
        registrar(request.user, "conflito_registrado", conflito)
        messages.success(request, "Reclamação registrada. A negociação segue; o rateio fica suspenso até a decisão.")
        return redirect("negocios:conflito", pk=conflito.pk)
    return render(request, "core/form_pagina.html", {
        "form": form, "titulo": "Registrar divergência", "voltar": "negocios:conflitos",
        "aviso": "Análise com provas, contraditório e critérios prévios. Quem é parte não decide sozinho o resultado.",
    })


@operador_required
def conflito_detalhe(request, pk):
    conflito = get_object_or_404(Conflito.objects.select_related("reclamante", "negociacao", "comprador", "imovel"), pk=pk)
    corretor = request.user.perfil_corretor
    if not (request.user.eh_central or conflito.reclamante == request.user
            or (corretor and conflito.envolvidos.filter(pk=corretor.pk).exists())):
        raise PermissionDenied
    pode_decidir = request.user.eh_central and not conflito.interessado(request.user)
    form = ConflitoDecisaoForm(request.POST or None, instance=conflito) if pode_decidir else None
    if form and request.method == "POST" and form.is_valid():
        conflito = form.save(commit=False)
        conflito.decidido_por = request.user
        if conflito.status in Conflito.STATUS_ENCERRADOS and not conflito.encerrado_em:
            conflito.encerrado_em = timezone.now()
        conflito.save()
        registrar(request.user, "conflito_atualizado", conflito, conflito.get_status_display())
        messages.success(request, "Conflito atualizado.")
        return redirect("negocios:conflito", pk=pk)
    return render(request, "negocios/conflito.html", {
        "c": conflito, "form": form, "interessado": conflito.interessado(request.user), "historico": historico(conflito),
    })


# ---------------------------------------------------------------------------
# Encaminhamento ao parceiro de crédito (fluxo separado)
# ---------------------------------------------------------------------------


@operador_required
def credito(request):
    lista = EncaminhamentoCredito.objects.select_related("comprador__corretor__usuario", "negociacao__imovel")
    if not request.user.eh_central:
        lista = lista.filter(comprador__corretor=request.user.perfil_corretor)
    return render(request, "negocios/credito.html", {"encaminhamentos": lista, "config": Configuracao.atual()})


@operador_required
def credito_novo(request, comprador_pk):
    comprador = _comprador_proprio(request, comprador_pk)
    config = Configuracao.atual()
    form = EncaminhamentoForm(request.POST or None, comprador=comprador)
    if request.method == "POST" and form.is_valid():
        enc = form.save(commit=False)
        enc.comprador = comprador
        enc.solicitado_por = request.user
        enc.dados_compartilhados = "nome, telefone, e-mail, município, produto de interesse e valor estimado"
        enc.save()
        registrar(request.user, "credito_encaminhado", comprador, f"{enc.get_produto_display()} → {config.parceiro_credito}")
        messages.success(request, f"Encaminhamento registrado para {config.parceiro_credito}.")
        return redirect(comprador)
    return render(request, "core/form_pagina.html", {
        "form": form, "titulo": f"Encaminhar ao parceiro de crédito — {comprador.nome}", "voltar_obj": comprador,
        "aviso": f"A plataforma envia a {config.parceiro_credito} apenas nome, contato, município e a necessidade "
                 "informada. Análise de endividamento, garantias e crédito acontece fora da plataforma, sob "
                 "contrato próprio do parceiro. Nunca prometa aprovação de crédito.",
    })


@central_required
def credito_status(request, pk):
    enc = get_object_or_404(EncaminhamentoCredito, pk=pk)
    form = EncaminhamentoStatusForm(request.POST or None, instance=enc)
    if request.method == "POST" and form.is_valid():
        form.save()
        registrar(request.user, "credito_status", enc.comprador, enc.get_status_display())
        return redirect("negocios:credito")
    return render(request, "core/form_pagina.html", {
        "form": form, "titulo": f"Status do encaminhamento — {enc.comprador.nome}", "voltar": "negocios:credito",
        "aviso": "Registre apenas o status do atendimento. Dados financeiros pertencem ao parceiro.",
    })
