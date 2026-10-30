from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.auditoria import historico, registrar
from core.models import Configuracao
from core.permissoes import (
    negociacao_com_dossie,
    operador_required,
    pode_ver_completo,
    pode_ver_dossie,
)
from imoveis.checklist import CATEGORIAS
from imoveis.forms import (
    AvaliacaoForm,
    ContratoForm,
    DocumentoForm,
    FiltroCatalogoForm,
    FotoForm,
    ImovelForm,
    ProprietarioForm,
    VerificacaoFormSet,
)
from imoveis.models import ContratoRepresentacao, DocumentoChecklist, FotoImovel, Imovel, Proprietario, VerificacaoBloco
from negocios import servicos
from negocios.models import Negociacao

CAMPOS_SENSIVEIS_PRECO = {"preco_pretendido", "comissao_pct", "area_registral_ha", "area_medida_ha", "matricula"}


def _imovel_completo(request, pk):
    imovel = get_object_or_404(Imovel.objects.select_related("proprietario", "captador__usuario"), pk=pk)
    if not pode_ver_completo(request.user, imovel):
        raise PermissionDenied
    return imovel


# ---------------------------------------------------------------------------
# Proprietários
# ---------------------------------------------------------------------------


@operador_required
def proprietarios(request):
    lista = Proprietario.objects.select_related("captado_por__usuario")
    if not request.user.eh_central:
        lista = lista.filter(captado_por=request.user.perfil_corretor)
    return render(request, "imoveis/proprietarios.html", {"proprietarios": lista})


@operador_required
def proprietario_form(request, pk=None):
    instancia = None
    if pk:
        instancia = get_object_or_404(Proprietario, pk=pk)
        if not request.user.eh_central and instancia.captado_por != request.user.perfil_corretor:
            raise PermissionDenied
    form = ProprietarioForm(request.POST or None, instance=instancia)
    if request.method == "POST" and form.is_valid():
        proprietario = form.save(commit=False)
        if not pk:
            proprietario.captado_por = request.user.perfil_corretor
        proprietario.save()
        registrar(request.user, "proprietario_salvo", proprietario)
        messages.success(request, "Proprietário salvo.")
        destino = request.GET.get("proximo")
        if destino == "imovel":
            return redirect(reverse("imoveis:novo") + f"?proprietario={proprietario.pk}")
        return redirect("imoveis:proprietarios")
    return render(request, "core/form_pagina.html", {
        "form": form, "titulo": "Editar proprietário" if pk else "Novo proprietário",
        "aviso": "Dados pessoais ficam restritos ao captador e à central (LGPD). Registre o consentimento.",
        "voltar": "imoveis:proprietarios",
    })


# ---------------------------------------------------------------------------
# Imóveis: cadastro, checklist, avaliação
# ---------------------------------------------------------------------------


@operador_required
def lista(request):
    imoveis = Imovel.objects.select_related("captador__usuario", "proprietario")
    if not request.user.eh_central:
        imoveis = imoveis.filter(captador=request.user.perfil_corretor)
    status = request.GET.get("status")
    if status:
        imoveis = imoveis.filter(status=status)
    return render(request, "imoveis/lista.html", {
        "imoveis": imoveis, "status": status, "status_choices": Imovel.Status.choices,
    })


@operador_required
def imovel_form(request, pk=None):
    instancia = _imovel_completo(request, pk) if pk else None
    inicial = {}
    if not pk and request.GET.get("proprietario"):
        inicial["proprietario"] = request.GET["proprietario"]
    if not pk:
        inicial["comissao_pct"] = Configuracao.atual().comissao_referencia_pct
    form = ImovelForm(request.POST or None, instance=instancia, usuario=request.user, initial=inicial)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            imovel = form.save(commit=False)
            if not pk and not request.user.eh_central:
                imovel.captador = request.user.perfil_corretor
            reabrir = (
                pk and not request.user.eh_central and imovel.publicado
                and CAMPOS_SENSIVEIS_PRECO & set(form.changed_data)
            )
            if reabrir:
                imovel.publicado = False
                imovel.status = Imovel.Status.EM_VALIDACAO
                imovel.enviado_validacao_em = timezone.now()
            imovel.save()
            if not pk:
                imovel.criar_checklist()
            registrar(request.user, "imovel_criado" if not pk else "imovel_editado", imovel,
                      ", ".join(form.changed_data))
        if reabrir:
            messages.warning(request, "Dados sensíveis alterados: o anúncio saiu do catálogo e voltou para validação.")
        else:
            messages.success(request, "Imóvel salvo. Campos desconhecidos ficam como 'não informado'.")
        return redirect(imovel)
    return render(request, "imoveis/form.html", {"form": form, "imovel": instancia})


@operador_required
def detalhe(request, pk):
    imovel = get_object_or_404(Imovel.objects.select_related("proprietario", "captador__usuario"), pk=pk)
    if not pode_ver_completo(request.user, imovel):
        return redirect("imoveis:catalogo_detalhe", pk=pk)
    config = Configuracao.atual()
    documentos = list(imovel.documentos.all())
    por_categoria = [(rotulo, [d for d in documentos if d.categoria == chave]) for chave, rotulo in CATEGORIAS]
    negociacoes = imovel.negociacoes.select_related("comprador", "corretor_vendedor__usuario")
    return render(request, "imoveis/detalhe.html", {
        "imovel": imovel,
        "decisao": imovel.decisao_documental(),
        "faixa": imovel.faixa_preco(config),
        "qualidade": imovel.qualidade_dossie(),
        "documentos": [(r, docs) for r, docs in por_categoria if docs],
        "verificacoes": imovel.verificacoes.all(),
        "fotos": imovel.fotos.all(),
        "contratos": imovel.contratos.all(),
        "contrato_vigente": imovel.contrato_vigente(),
        "negociacoes": negociacoes,
        "compativeis": servicos.compatibilidades_do_imovel(imovel, limite=5),
        "historico": historico(imovel),
    })


class DocumentoCorretorForm(DocumentoForm):
    """O captador anexa e informa o status; só a central valida e aponta riscos."""

    STATUS_CORRETOR = {"pendente", "recebido", "nao_aplicavel", "vencido"}

    class Meta(DocumentoForm.Meta):
        fields = ["status", "emissao", "validade", "responsavel", "prazo", "observacoes", "arquivo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        permitidos = self.STATUS_CORRETOR | {self.instance.status}
        self.fields["status"].choices = [c for c in self.fields["status"].choices if c[0] in permitidos]


@operador_required
def checklist(request, pk):
    imovel = _imovel_completo(request, pk)
    central = request.user.eh_central
    form_classe = DocumentoForm if central else DocumentoCorretorForm
    FormSet = forms.modelformset_factory(DocumentoChecklist, form=form_classe, extra=0)
    docs = FormSet(request.POST or None, request.FILES or None, queryset=imovel.documentos.all(), prefix="doc")
    verif = VerificacaoFormSet(request.POST or None, queryset=imovel.verificacoes.all(), prefix="ver")
    if request.method == "POST" and docs.is_valid() and verif.is_valid():
        if not central and any(
            f.cleaned_data.get("fonte") == VerificacaoBloco.Fonte.VALIDADO and "fonte" in f.changed_data
            for f in verif.forms
        ):
            messages.error(request, "Somente a central pode marcar um bloco como 'validado por especialista'.")
        else:
            alterados = [f.instance.descricao[:40] for f in docs.forms if f.has_changed()]
            docs.save()
            verif.save()
            registrar(request.user, "checklist_atualizado", imovel, "; ".join(alterados))
            messages.success(request, "Checklist atualizado.")
            return redirect(imovel)
    linhas = list(zip(imovel.documentos.all(), docs.forms))
    grupos = [(rotulo, [l for l in linhas if l[0].categoria == chave]) for chave, rotulo in CATEGORIAS]
    return render(request, "imoveis/checklist.html", {
        "imovel": imovel, "docs": docs, "verif": verif, "grupos": [g for g in grupos if g[1]],
    })


@operador_required
def foto_nova(request, pk):
    imovel = _imovel_completo(request, pk)
    form = FotoForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        foto = form.save(commit=False)
        foto.imovel = imovel
        foto.enviada_por = request.user
        foto.save()
        registrar(request.user, "foto_adicionada", imovel, foto.descricao)
        messages.success(request, "Foto adicionada.")
        return redirect(imovel)
    return render(request, "core/form_pagina.html", {
        "form": form, "titulo": f"Nova foto — {imovel.codigo}", "multipart": True, "voltar_obj": imovel,
        "aviso": "Foto obrigatória por grupo de infraestrutura, com data, autor e descrição. "
                 "Não use imagens de safras anteriores como se fossem atuais.",
    })


@operador_required
@require_POST
def foto_remover(request, pk):
    foto = get_object_or_404(FotoImovel, pk=pk)
    imovel = _imovel_completo(request, foto.imovel_id)
    foto.arquivo.delete(save=False)
    foto.delete()
    registrar(request.user, "foto_removida", imovel, foto.descricao)
    return redirect(imovel)


@operador_required
def contrato_form(request, pk, contrato_pk=None):
    imovel = _imovel_completo(request, pk)
    contrato = get_object_or_404(ContratoRepresentacao, pk=contrato_pk, imovel=imovel) if contrato_pk else None
    config = Configuracao.atual()
    inicial = {
        "prazo_dias": config.dias_exclusividade_padrao,
        "comissao_pct": imovel.comissao_pct,
        "preco_autorizado": imovel.preco_autorizado or imovel.preco_pretendido,
    }
    form = ContratoForm(request.POST or None, request.FILES or None, instance=contrato, initial=inicial)
    if request.method == "POST" and form.is_valid():
        contrato = form.save(commit=False)
        contrato.imovel = imovel
        contrato.save()
        registrar(request.user, "contrato_salvo", imovel, f"{contrato.get_tipo_display()} — {contrato.get_status_display()}")
        messages.success(request, "Autorização de venda registrada.")
        return redirect(imovel)
    return render(request, "core/form_pagina.html", {
        "form": form, "titulo": f"Autorização de venda — {imovel.codigo}", "multipart": True, "voltar_obj": imovel,
        "aviso": "Exclusividade por prazo determinado, com preço, comissão e exceções. A minuta gerada é "
                 "orientativa e exige revisão por advogado (Código Civil, arts. 722 a 729).",
    })


@operador_required
@require_POST
def enviar_validacao(request, pk):
    imovel = _imovel_completo(request, pk)
    if imovel.status in (Imovel.Status.RASCUNHO, Imovel.Status.PENDENTE, Imovel.Status.RECUSADO):
        imovel.status = Imovel.Status.EM_VALIDACAO
        imovel.enviado_validacao_em = timezone.now()
        imovel.save(update_fields=["status", "enviado_validacao_em"])
        registrar(request.user, "imovel_enviado_validacao", imovel)
        messages.success(request, "Enviado para validação da central.")
    return redirect(imovel)


@operador_required
def avaliar(request, pk):
    if not request.user.eh_central:
        raise PermissionDenied
    imovel = get_object_or_404(Imovel, pk=pk)
    config = Configuracao.atual()
    form = AvaliacaoForm(request.POST or None, instance=imovel)
    if request.method == "POST" and form.is_valid():
        imovel = form.save(commit=False)
        if "status" in form.changed_data:
            imovel.validado_por = request.user
            imovel.validado_em = timezone.now()
        if imovel.data_avaliacao:
            imovel.revisar_preco_em = imovel.data_avaliacao + timezone.timedelta(days=config.dias_revisao_preco_rural)
        imovel.save()
        registrar(request.user, "imovel_deliberado", imovel,
                  f"{imovel.get_status_display()}; publicado={imovel.publicado}; " + ", ".join(form.changed_data))
        messages.success(request, "Deliberação registrada.")
        return redirect(imovel)
    return render(request, "imoveis/avaliar.html", {
        "imovel": imovel, "form": form, "faixa": imovel.faixa_preco(config), "decisao": imovel.decisao_documental(),
        "config": config,
    })


@operador_required
def dossie(request, pk):
    """Dossiê de captação: uso interno, acesso individual, marca d'água e log (Estratégia V2, seção 09)."""
    imovel = get_object_or_404(Imovel.objects.select_related("proprietario", "captador__usuario"), pk=pk)
    if not pode_ver_dossie(request.user, imovel):
        raise PermissionDenied("Registre um comprador e solicite acesso ao data room.")
    completo = pode_ver_completo(request.user, imovel)
    registrar(request.user, "acesso_dossie", imovel)
    return render(request, "imoveis/dossie.html", {
        "imovel": imovel,
        "completo": completo,
        "liberacao": None if completo else negociacao_com_dossie(request.user, imovel),
        "decisao": imovel.decisao_documental(),
        "documentos": imovel.documentos.all(),
        "verificacoes": imovel.verificacoes.all(),
        "fotos": imovel.fotos.filter(autorizada=True) if not completo else imovel.fotos.all(),
        "agora": timezone.now(),
    })


# ---------------------------------------------------------------------------
# Catálogo fechado para corretores
# ---------------------------------------------------------------------------


@operador_required
def catalogo(request):
    form = FiltroCatalogoForm(request.GET or None)
    imoveis = servicos.imoveis_catalogo()
    if form.is_valid():
        f = form.cleaned_data
        if f["q"]:
            imoveis = imoveis.filter(Q(titulo__icontains=f["q"]) | Q(municipio__icontains=f["q"]) |
                                     Q(regiao__icontains=f["q"]) | Q(codigo__icontains=f["q"]))
        if f["uf"]:
            imoveis = imoveis.filter(uf=f["uf"])
        if f["aptidao"]:
            imoveis = imoveis.filter(aptidoes__contains=f["aptidao"])
        if f["irrigacao"]:
            imoveis = imoveis.filter(irrigacao=True)
        if f["preco_max"]:
            imoveis = imoveis.filter(Q(preco_autorizado__lte=f["preco_max"]) |
                                     Q(preco_autorizado=None, preco_pretendido__lte=f["preco_max"]))
        lista = list(imoveis)
        if f["area_min"]:
            lista = [i for i in lista if i.area_total_ha and i.area_total_ha >= f["area_min"]]
        if f["area_max"]:
            lista = [i for i in lista if i.area_total_ha and i.area_total_ha <= f["area_max"]]
    else:
        lista = list(imoveis)
    return render(request, "imoveis/catalogo.html", {"form": form, "imoveis": lista})


@operador_required
def catalogo_detalhe(request, pk):
    imovel = get_object_or_404(Imovel.objects.select_related("captador__usuario"), pk=pk)
    if not (imovel.publicado or pode_ver_completo(request.user, imovel)):
        raise PermissionDenied
    corretor = request.user.perfil_corretor
    minhas = Negociacao.objects.filter(imovel=imovel, corretor_vendedor=corretor) if corretor else []
    registrar(request.user, "acesso_ficha", imovel)
    return render(request, "imoveis/catalogo_detalhe.html", {
        "imovel": imovel,
        "decisao": imovel.decisao_documental(),
        "fotos": imovel.fotos.filter(autorizada=True),
        "minhas": minhas,
        "pode_dossie": pode_ver_dossie(request.user, imovel),
        "completo": pode_ver_completo(request.user, imovel),
    })
