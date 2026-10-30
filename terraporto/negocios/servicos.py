from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from contas.models import Corretor, Mensalidade
from core import regras
from core.models import Configuracao, LeadPublico, ParametroNivel
from imoveis.models import ContratoRepresentacao, Imovel
from negocios.models import (
    ApuracaoComissao,
    Atividade,
    Comprador,
    Conflito,
    Demanda,
    EncaminhamentoCredito,
    Negociacao,
    ParticipacaoComissao,
)


@dataclass
class Compatibilidade:
    imovel: Imovel
    demanda: Demanda
    pontos: int
    criterios: list


def imoveis_catalogo():
    return Imovel.objects.filter(publicado=True, status__in=Imovel.STATUS_PUBLICAVEIS).select_related("captador__usuario")


def compatibilidades_da_demanda(demanda: Demanda, minimo=50, limite=10) -> list[Compatibilidade]:
    perfil = demanda.perfil()
    resultado = []
    for imovel in imoveis_catalogo().prefetch_related("documentos", "contratos"):
        pontos, criterios = regras.pontuar_compatibilidade(imovel.perfil_compatibilidade(), perfil)
        if pontos >= minimo:
            resultado.append(Compatibilidade(imovel, demanda, pontos, criterios))
    return sorted(resultado, key=lambda c: -c.pontos)[:limite]


def compatibilidades_do_imovel(imovel: Imovel, minimo=50, limite=20) -> list[Compatibilidade]:
    perfil_imovel = imovel.perfil_compatibilidade()
    resultado = []
    for demanda in Demanda.objects.filter(ativa=True).select_related("comprador__corretor__usuario"):
        pontos, criterios = regras.pontuar_compatibilidade(perfil_imovel, demanda.perfil())
        if pontos >= minimo:
            resultado.append(Compatibilidade(imovel, demanda, pontos, criterios))
    return sorted(resultado, key=lambda c: -c.pontos)[:limite]


def registrar_atividade(negociacao: Negociacao, usuario, tipo: str, descricao: str) -> Atividade:
    """Registra a atividade e, se ela comprovar atuação efetiva, renova a prioridade comercial
    do comprador por mais N dias (Regulamento de Proteção, seção 4.1)."""
    atividade = Atividade.objects.create(negociacao=negociacao, autor=usuario, tipo=tipo, descricao=descricao)
    if atividade.renova_protecao:
        negociacao.comprador.renovar_protecao(Configuracao.atual().dias_protecao_comprador)
    Negociacao.objects.filter(pk=negociacao.pk).update(atualizado_em=timezone.now())
    return atividade


def registrar_comprador(comprador: Comprador) -> list[Comprador]:
    """Salva o registro, define a prioridade inicial e aponta possíveis duplicidades.

    O primeiro registro válido gera prioridade provisória; um segundo registro do mesmo
    comprador por outro corretor fica sem prioridade até a análise da central (seção 5).
    """
    config = Configuracao.atual()
    comprador.save()
    duplicados = [d for d in comprador.possiveis_duplicidades().order_by("criado_em") if d.protegido]
    if duplicados:
        comprador.duplicidade_de = duplicados[0]
        comprador.protecao_ate = None
    else:
        comprador.protecao_ate = regras.renovar_protecao(None, timezone.localdate(), config.dias_protecao_comprador)
    comprador.save(update_fields=["duplicidade_de", "protecao_ate"])
    return duplicados


@transaction.atomic
def gerar_apuracao(negociacao: Negociacao) -> ApuracaoComissao:
    config = Configuracao.atual()
    imovel = negociacao.imovel
    valor = negociacao.valor_fechamento or negociacao.valor_proposta or imovel.preco_referencia_anuncio
    contrato = imovel.contrato_vigente() or imovel.contratos.filter(assinado=True).first()
    comissao_pct = contrato.comissao_pct if contrato else imovel.comissao_pct
    rateio = regras.calcular_rateio(
        valor,
        comissao_pct,
        captador_id=imovel.captador_id,
        captador_nivel=imovel.captador.nivel,
        vendedor_id=negociacao.corretor_vendedor_id,
        vendedor_nivel=negociacao.corretor_vendedor.nivel,
        modelo=config.modelo_rateio,
        situacao=negociacao.situacao,
        parametros=ParametroNivel.como_regras(),
        pct_regulamento=config.pct_regulamento,
    )
    ApuracaoComissao.objects.filter(negociacao=negociacao).delete()
    apuracao = ApuracaoComissao.objects.create(
        negociacao=negociacao,
        valor_venda=rateio.valor_venda,
        comissao_pct=rateio.comissao_pct,
        comissao_total=rateio.comissao_total,
        modelo=rateio.modelo,
        status=ApuracaoComissao.Status.SUSPENSA if negociacao.em_disputa else ApuracaoComissao.Status.PREVISTA,
        alertas="\n".join(rateio.alertas),
    )
    for parcela in rateio.parcelas:
        ParticipacaoComissao.objects.create(
            apuracao=apuracao,
            papel=parcela.papel,
            corretor_id=parcela.corretor_id,
            percentual=parcela.percentual,
            valor=parcela.valor,
            observacao=parcela.observacao,
        )
    return apuracao


def indicadores() -> dict:
    """Indicadores essenciais (Estratégia V2, seção 18)."""
    hoje = timezone.localdate()
    ano = hoje - timezone.timedelta(days=365)
    negocios = Negociacao.objects.all()
    concluidos = negocios.filter(etapa=Negociacao.Etapa.CONCLUIDO)
    concluidos_12m = concluidos.filter(data_fechamento__gte=ano)
    encerrados = negocios.filter(etapa__in=[Negociacao.Etapa.CONCLUIDO, Negociacao.Etapa.PERDIDO]).count()
    imoveis = Imovel.objects.all()
    publicados = imoveis.filter(publicado=True)
    qualidade = [i.qualidade_dossie() for i in publicados.prefetch_related("documentos", "fotos")]
    validados = imoveis.exclude(validado_em=None).exclude(enviado_validacao_em=None)
    dias_validacao = [(i.validado_em - i.enviado_validacao_em).days for i in validados]
    competencia = hoje.replace(day=1)
    mensalidades_mes = Mensalidade.objects.filter(competencia=competencia)
    apuracoes = ApuracaoComissao.objects.filter(negociacao__in=concluidos_12m)
    receita_central = ParticipacaoComissao.objects.filter(
        apuracao__in=apuracoes, papel=ParticipacaoComissao.Papel.CENTRAL
    ).aggregate(t=Sum("valor"))["t"]

    return {
        "corretores_ativos": Corretor.objects.filter(status__in=Corretor.STATUS_OPERANTES).count(),
        "corretores_em_analise": Corretor.objects.filter(
            status__in=[Corretor.Status.INSCRITO, Corretor.Status.EM_ANALISE]
        ).count(),
        "imoveis_total": imoveis.count(),
        "imoveis_publicados": publicados.count(),
        "imoveis_em_validacao": imoveis.filter(status=Imovel.Status.EM_VALIDACAO).count(),
        "exclusivos_validos": ContratoRepresentacao.objects.filter(
            tipo=ContratoRepresentacao.Tipo.EXCLUSIVA, status=ContratoRepresentacao.Status.VIGENTE,
            assinado=True, data_fim__gte=hoje,
        ).count(),
        "qualidade_media": round(sum(qualidade) / len(qualidade)) if qualidade else None,
        "dias_validacao": round(sum(dias_validacao) / len(dias_validacao), 1) if dias_validacao else None,
        "compradores": Comprador.objects.count(),
        "contatos_qualificados": negocios.exclude(etapa=Negociacao.Etapa.NOVO).count(),
        "negociacoes_abertas": negocios.filter(etapa__in=Negociacao.ETAPAS_ABERTAS).count(),
        "visitas": negocios.aggregate(v=Count("visitas", filter=Q(visitas__realizada=True)))["v"],
        "propostas": negocios.filter(
            etapa__in=[Negociacao.Etapa.PROPOSTA, Negociacao.Etapa.DILIGENCIA, Negociacao.Etapa.CONTRATO,
                       Negociacao.Etapa.CONCLUIDO]
        ).count(),
        "conversao": round(100 * concluidos.count() / encerrados) if encerrados else None,
        "vgv_12m": concluidos_12m.aggregate(t=Sum("valor_fechamento"))["t"] or Decimal("0"),
        "comissao_12m": apuracoes.aggregate(t=Sum("comissao_total"))["t"] or Decimal("0"),
        "receita_central_12m": receita_central or Decimal("0"),
        "mensalidades_previstas": mensalidades_mes.exclude(status=Mensalidade.Status.CANCELADA).aggregate(
            t=Sum("valor"))["t"] or Decimal("0"),
        "mensalidades_recebidas": mensalidades_mes.filter(status=Mensalidade.Status.PAGA).aggregate(
            t=Sum("valor"))["t"] or Decimal("0"),
        "inadimplentes": Mensalidade.objects.filter(status=Mensalidade.Status.PENDENTE, vencimento__lt=hoje).count(),
        "conflitos_abertos": Conflito.objects.exclude(status__in=Conflito.STATUS_ENCERRADOS).count(),
        "encaminhamentos_credito": EncaminhamentoCredito.objects.exclude(
            status=EncaminhamentoCredito.Status.CANCELADO).count(),
        "leads_novos": LeadPublico.objects.filter(status=LeadPublico.Status.NOVO).count(),
    }


def funil_por_etapa(queryset):
    contagem = dict(queryset.values_list("etapa").annotate(n=Count("id")))
    return [(valor, rotulo, contagem.get(valor, 0)) for valor, rotulo in Negociacao.Etapa.choices]
