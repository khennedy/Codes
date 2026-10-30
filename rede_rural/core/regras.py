"""Regras de negócio da rede, sem dependência de banco de dados.

Cada função cita a seção dos documentos de referência que ela implementa:
- "Estratégia V2": A Nova Infraestrutura do Mercado de Terras (out/2026).
- "Regulamento de Proteção": Documento 2 do Projeto de Parceria com Corretores.
- "Regulamento de Avaliação": Regulamento de Avaliação Mercadológica e Precificação.
- "Checklist": Anexo 01 — Checklist Documental e Diligência Rural.

Os percentuais e prazos são premissas ilustrativas dos documentos e podem ser
alterados pela Central em Configurações. Nada aqui substitui parecer jurídico.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from core.choices import ROTULO_APTIDAO

CENTAVO = Decimal("0.01")
CEM = Decimal("100")


def dinheiro(valor) -> Decimal:
    return Decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Níveis de credenciamento (Estratégia V2, seções 06, 13 e 19)
# ---------------------------------------------------------------------------

NIVEIS = ("pleno", "senior", "master", "partner")
ROTULO_NIVEL = {"pleno": "Pleno", "senior": "Sênior", "master": "Master", "partner": "Partner"}


@dataclass(frozen=True)
class ParamNivel:
    nivel: str
    pct_captacao: Decimal  # % sobre o valor de venda
    pct_venda: Decimal  # % sobre o valor de venda
    mensalidade: Decimal
    volume_min_12m: Decimal  # VGV concluído nos últimos 12 meses para alcançar o nível


PARAMETROS_PADRAO = {
    "pleno": ParamNivel("pleno", Decimal("0.60"), Decimal("1.00"), Decimal("100"), Decimal("0")),
    "senior": ParamNivel("senior", Decimal("0.70"), Decimal("1.30"), Decimal("200"), Decimal("20000000")),
    "master": ParamNivel("master", Decimal("0.80"), Decimal("1.60"), Decimal("300"), Decimal("40000000")),
    "partner": ParamNivel("partner", Decimal("1.00"), Decimal("2.00"), Decimal("400"), Decimal("60000000")),
}


def nivel_sugerido(volume_12m, parametros=PARAMETROS_PADRAO) -> str:
    """Tabela da seção 19: Pleno até R$ 20 mi, Sênior 20–40, Master 40–60, Partner acima de 60.

    É apenas uma sugestão: a evolução também considera qualidade documental, cursos,
    avaliações, ética e satisfação (seção 06).
    """
    volume = Decimal(volume_12m or 0)
    escolhido = "pleno"
    for p in sorted(parametros.values(), key=lambda p: p.volume_min_12m):
        if p.volume_min_12m == 0 or volume > p.volume_min_12m:
            escolhido = p.nivel
    return escolhido


# ---------------------------------------------------------------------------
# Comissões (Estratégia V2 seção 13/19; Regulamento de Proteção seções 7, 8 e 9)
# ---------------------------------------------------------------------------

MODELO_NIVEL = "nivel"
MODELO_REGULAMENTO = "regulamento"

SITUACAO_A = "A"  # comprador da carteira própria, negociação independente da plataforma
SITUACAO_B = "B"  # comprador originado pela rede (outro corretor)
SITUACAO_C = "C"  # captação e venda pelo mesmo corretor, dentro da rede

DESCRICAO_SITUACAO = {
    SITUACAO_A: "Comprador independente da rede: prevalecem os contratos aplicáveis; "
    "a participação da central não é automática.",
    SITUACAO_B: "Comprador originado pela rede: a participação de quem apresentou o "
    "comprador é preservada.",
    SITUACAO_C: "Captação e venda pelo mesmo corretor dentro da rede: segue as condições "
    "contratadas para operações conduzidas pela plataforma.",
}


@dataclass
class Parcela:
    papel: str
    corretor_id: int | None
    valor: Decimal
    percentual: Decimal = Decimal("0")  # % da comissão total
    observacao: str = ""


@dataclass
class Rateio:
    valor_venda: Decimal
    comissao_pct: Decimal
    comissao_total: Decimal
    modelo: str
    situacao: str
    parcelas: list[Parcela] = field(default_factory=list)
    alertas: list[str] = field(default_factory=list)

    def valor_por_papel(self, papel: str) -> Decimal:
        return sum((p.valor for p in self.parcelas if p.papel == papel), Decimal("0"))


def calcular_rateio(
    valor_venda,
    comissao_pct,
    *,
    captador_id,
    captador_nivel,
    vendedor_id,
    vendedor_nivel,
    modelo=MODELO_NIVEL,
    situacao=SITUACAO_B,
    parametros=PARAMETROS_PADRAO,
    pct_regulamento=(Decimal("45"), Decimal("45"), Decimal("10")),
) -> Rateio:
    valor_venda = Decimal(valor_venda)
    comissao_pct = Decimal(comissao_pct)
    total = dinheiro(valor_venda * comissao_pct / CEM)
    rateio = Rateio(valor_venda, comissao_pct, total, modelo, situacao)

    if situacao in (SITUACAO_A, SITUACAO_C) and captador_id != vendedor_id:
        rateio.alertas.append(
            "Situações A e C pressupõem o mesmo corretor como captador e vendedor; confira a origem do comprador."
        )

    if modelo == MODELO_REGULAMENTO:
        pct_capt, pct_vend, _pct_central = (Decimal(x) for x in pct_regulamento)
        capt = dinheiro(total * pct_capt / CEM)
        vend = dinheiro(total * pct_vend / CEM)
    else:
        capt = dinheiro(valor_venda * parametros[captador_nivel].pct_captacao / CEM)
        vend = dinheiro(valor_venda * parametros[vendedor_nivel].pct_venda / CEM)

    if situacao == SITUACAO_A:
        # O comprador não veio da rede: sem participação automática da central.
        vend = total - capt
        rateio.alertas.append(DESCRICAO_SITUACAO[SITUACAO_A] + " Valide o rateio com o contrato antes de aprovar.")

    if capt + vend > total:
        fator = total / (capt + vend)
        capt = dinheiro(capt * fator)
        vend = total - capt
        rateio.alertas.append(
            "A comissão contratual é menor que a soma dos percentuais de nível; "
            "o rateio foi reduzido proporcionalmente e precisa de acordo prévio."
        )

    central = total - capt - vend
    rateio.parcelas = [
        Parcela("captador", captador_id, capt),
        Parcela("vendedor", vendedor_id, vend),
        Parcela("central", None, central, observacao="Valor residual bruto — não é lucro."),
    ]
    for p in rateio.parcelas:
        p.percentual = (p.valor / total * CEM).quantize(CENTAVO) if total else Decimal("0")
    return rateio


# ---------------------------------------------------------------------------
# Faixas de compatibilidade de preço (Regulamento de Avaliação, arts. 10 a 13)
# ---------------------------------------------------------------------------


@dataclass
class ResultadoPreco:
    faixa: str
    desvio_pct: Decimal | None
    rotulo: str
    recomendacao: str


def classificar_preco(preco, referencia, limites=(5, 10, 15), limite_abaixo=10) -> ResultadoPreco:
    if not preco or not referencia:
        return ResultadoPreco(
            "SEM_REFERENCIA",
            None,
            "Sem avaliação",
            "Sem valor de mercado fundamentado: as faixas internas não se aplicam (art. 11).",
        )
    preco, referencia = Decimal(preco), Decimal(referencia)
    desvio = ((preco - referencia) / referencia * CEM).quantize(Decimal("0.1"))
    a, b, c = (Decimal(x) for x in limites)
    if desvio <= -Decimal(limite_abaixo):
        return ResultadoPreco(
            "ABAIXO",
            desvio,
            "Abaixo do valor estimado",
            "Comunicar ao proprietário com transparência e registrar decisão livre e expressa (art. 13).",
        )
    if desvio <= a:
        return ResultadoPreco("A", desvio, "Faixa A", "Aprovação ordinária, desde que justificada.")
    if desvio <= b:
        return ResultadoPreco("B", desvio, "Faixa B", "Aprovação condicionada a análise comercial complementar.")
    if desvio <= c:
        return ResultadoPreco(
            "C", desvio, "Faixa C", "Exige revisão técnica ou justificativa documentada e aprovação especial."
        )
    return ResultadoPreco(
        "D", desvio, "Faixa D", "Recusa preliminar, salvo novas evidências que justifiquem revisão (art. 12)."
    )


# ---------------------------------------------------------------------------
# Matriz de decisão do checklist documental (Checklist, seção 7; Estratégia V2 seção 10)
# ---------------------------------------------------------------------------

STATUS_OK = {"validado", "nao_aplicavel"}
# Itens que comprovam titularidade/representação; se verificados, o imóvel pode
# seguir "com ressalvas" mesmo havendo outras pendências descritas.
CODIGOS_TITULARIDADE = {"id_titulares", "matricula_onus", "pf_documentos", "pj_cnpj", "pj_poderes"}

DECISAO_APTO = "apto"
DECISAO_RESSALVAS = "ressalvas"
DECISAO_PENDENTE = "pendente"
DECISAO_BLOQUEADO = "bloqueado"

ROTULO_DECISAO = {
    DECISAO_APTO: "Apto para divulgação",
    DECISAO_RESSALVAS: "Apto com ressalvas",
    DECISAO_PENDENTE: "Pendente",
    DECISAO_BLOQUEADO: "Bloqueado",
}


@dataclass
class ItemDecisao:
    codigo: str
    descricao: str
    essencial: bool
    status: str
    risco: str = "nenhum"
    vencido: bool = False

    @property
    def ok(self) -> bool:
        return self.status in STATUS_OK and not self.vencido


@dataclass
class ResultadoDecisao:
    codigo: str
    motivos: list[str]

    @property
    def rotulo(self) -> str:
        return ROTULO_DECISAO[self.codigo]


def decidir_publicacao(itens: list[ItemDecisao], autorizacao_assinada: bool) -> ResultadoDecisao:
    impeditivos = [i for i in itens if i.risco == "impeditivo"]
    if impeditivos:
        return ResultadoDecisao(DECISAO_BLOQUEADO, [f"Impeditivo: {i.descricao}" for i in impeditivos])

    if not autorizacao_assinada:
        return ResultadoDecisao(
            DECISAO_PENDENTE, ["Sem autorização escrita de intermediação e publicidade vigente."]
        )

    essenciais_pendentes = [i for i in itens if i.essencial and not i.ok]
    condicionantes = [i for i in itens if i.risco == "condicionante"]
    if not essenciais_pendentes and not condicionantes:
        return ResultadoDecisao(DECISAO_APTO, [])

    motivos = [f"Pendente: {i.descricao}" for i in essenciais_pendentes]
    motivos += [f"Condicionante: {i.descricao}" for i in condicionantes]
    titularidade = [i for i in itens if i.codigo in CODIGOS_TITULARIDADE]
    if titularidade and all(i.ok for i in titularidade):
        return ResultadoDecisao(DECISAO_RESSALVAS, motivos)
    return ResultadoDecisao(DECISAO_PENDENTE, motivos)


# ---------------------------------------------------------------------------
# Motor de compatibilidade comprador × imóvel (Estratégia V2 seção 12)
# ---------------------------------------------------------------------------


@dataclass
class PerfilImovel:
    preco: Decimal | None
    area_ha: Decimal | None
    aptidoes: set[str]
    municipio: str
    uf: str
    regiao: str
    irrigacao: bool
    mecanizavel_pct: Decimal | None
    decisao: str


@dataclass
class PerfilDemanda:
    orcamento_min: Decimal | None
    orcamento_max: Decimal | None
    area_min: Decimal | None
    area_max: Decimal | None
    aptidoes: set[str]
    municipios: set[str]
    regiao: str
    uf: str
    exige_irrigacao: bool
    mecanizacao_min: Decimal | None


@dataclass
class Criterio:
    nome: str
    pontos: int
    maximo: int
    explicacao: str


def _normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "").strip().lower())


def _dentro(valor, minimo, maximo, folga_pct) -> int:
    """2 = dentro do intervalo, 1 = dentro da folga, 0 = fora."""
    if valor is None:
        return 0
    valor = Decimal(valor)
    folga = Decimal(folga_pct) / CEM
    if (minimo is None or valor >= minimo) and (maximo is None or valor <= maximo):
        return 2
    if (minimo is None or valor >= minimo * (1 - folga)) and (maximo is None or valor <= maximo * (1 + folga)):
        return 1
    return 0


def pontuar_compatibilidade(imovel: PerfilImovel, demanda: PerfilDemanda) -> tuple[int, list[Criterio]]:
    criterios: list[Criterio] = []

    faixa = _dentro(imovel.preco, demanda.orcamento_min, demanda.orcamento_max, 10)
    criterios.append(
        Criterio(
            "Preço",
            {2: 25, 1: 12, 0: 0}[faixa],
            25,
            {2: "dentro do orçamento", 1: "até 10% fora do orçamento", 0: "fora do orçamento ou não informado"}[
                faixa
            ],
        )
    )

    faixa = _dentro(imovel.area_ha, demanda.area_min, demanda.area_max, 20)
    criterios.append(
        Criterio(
            "Área",
            {2: 20, 1: 10, 0: 0}[faixa],
            20,
            {2: "área dentro do desejado", 1: "área até 20% fora do desejado", 0: "área incompatível ou não informada"}[
                faixa
            ],
        )
    )

    if not demanda.aptidoes:
        criterios.append(Criterio("Aptidão", 20, 20, "comprador não restringiu aptidão"))
    else:
        comuns = demanda.aptidoes & imovel.aptidoes
        criterios.append(
            Criterio(
                "Aptidão",
                20 if comuns else 0,
                20,
                "em comum: " + ", ".join(sorted(ROTULO_APTIDAO.get(c, c).lower() for c in comuns)) if comuns else "nenhuma aptidão em comum",
            )
        )

    municipios = {_normalizar(m) for m in demanda.municipios if m}
    if municipios and _normalizar(imovel.municipio) in municipios:
        criterios.append(Criterio("Localização", 15, 15, f"município desejado ({imovel.municipio})"))
    elif demanda.regiao and _normalizar(demanda.regiao) == _normalizar(imovel.regiao):
        criterios.append(Criterio("Localização", 10, 15, f"mesma região ({imovel.regiao})"))
    elif not municipios and not demanda.regiao and (not demanda.uf or demanda.uf == imovel.uf):
        criterios.append(Criterio("Localização", 10, 15, "comprador sem restrição de localização"))
    elif demanda.uf and demanda.uf == imovel.uf:
        criterios.append(Criterio("Localização", 5, 15, f"mesmo estado ({imovel.uf})"))
    else:
        criterios.append(Criterio("Localização", 0, 15, "fora da região de interesse"))

    pontos_infra = 10
    notas = []
    if demanda.exige_irrigacao and not imovel.irrigacao:
        pontos_infra -= 6
        notas.append("sem irrigação")
    if demanda.mecanizacao_min:
        if imovel.mecanizavel_pct is None or imovel.mecanizavel_pct < demanda.mecanizacao_min:
            pontos_infra -= 4
            notas.append("mecanização abaixo do mínimo")
    criterios.append(
        Criterio("Infraestrutura", pontos_infra, 10, ", ".join(notas) if notas else "atende às exigências")
    )

    pontos_doc = {DECISAO_APTO: 10, DECISAO_RESSALVAS: 5, DECISAO_PENDENTE: 2}.get(imovel.decisao, 0)
    criterios.append(
        Criterio("Documentação", pontos_doc, 10, ROTULO_DECISAO.get(imovel.decisao, "não avaliada").lower())
    )

    return sum(c.pontos for c in criterios), criterios


# ---------------------------------------------------------------------------
# Proteção do comprador e duplicidades (Regulamento de Proteção, seções 4 e 5)
# ---------------------------------------------------------------------------

# Atividades que comprovam atuação efetiva e renovam a prioridade comercial.
ATIVIDADES_QUE_RENOVAM = {"visita_agendada", "visita", "proposta", "negociacao", "reuniao"}


def renovar_protecao(atual: date | None, hoje: date, dias: int) -> date:
    nova = hoje + timedelta(days=dias)
    return max(atual, nova) if atual else nova


def chaves_contato(telefone: str = "", email: str = "", documento: str = "") -> set[str]:
    chaves = set()
    digitos = re.sub(r"\D", "", telefone or "")
    if len(digitos) > 11 and digitos.startswith("55"):
        digitos = digitos[2:]
    if len(digitos) >= 8:
        chaves.add("tel:" + digitos[-8:])
    email = (email or "").strip().lower()
    if "@" in email:
        chaves.add("email:" + email)
    doc = re.sub(r"\D", "", documento or "")
    if len(doc) in (11, 14):
        chaves.add("doc:" + doc)
    return chaves


# ---------------------------------------------------------------------------
# Capacidade de a terra se pagar (Estratégia V2 seção 11)
# ---------------------------------------------------------------------------

CENARIOS_VIABILIDADE = (
    ("Conservador", Decimal("-20"), Decimal("-10")),
    ("Base", Decimal("0"), Decimal("0")),
    ("Otimista", Decimal("10"), Decimal("5")),
)


def parcela_price(principal, taxa_anual_pct, prazo_anos) -> Decimal:
    principal = Decimal(principal)
    if principal <= 0 or not prazo_anos:
        return Decimal("0")
    i = Decimal(taxa_anual_pct) / CEM
    n = int(prazo_anos)
    if i == 0:
        return dinheiro(principal / n)
    return dinheiro(principal * i / (1 - (1 + i) ** -n))


def simular_viabilidade(
    *,
    area_produtiva_ha,
    produtividade_por_ha,
    preco_unitario,
    custo_por_ha,
    preco_imovel,
    entrada_pct,
    taxa_anual_pct,
    prazo_anos,
    outros_custos_anuais=0,
) -> list[dict]:
    """Projeção simples por cenário. Não é promessa de rentabilidade nem garantia de crédito."""
    area = Decimal(area_produtiva_ha)
    financiado = Decimal(preco_imovel) * (1 - Decimal(entrada_pct) / CEM)
    parcela = parcela_price(financiado, taxa_anual_pct, prazo_anos)
    custo = dinheiro(area * Decimal(custo_por_ha) + Decimal(outros_custos_anuais))
    resultado = []
    for nome, var_prod, var_preco in CENARIOS_VIABILIDADE:
        prod = Decimal(produtividade_por_ha) * (1 + var_prod / CEM)
        preco = Decimal(preco_unitario) * (1 + var_preco / CEM)
        receita = dinheiro(area * prod * preco)
        operacional = receita - custo
        cobertura = (operacional / parcela).quantize(Decimal("0.01")) if parcela else None
        resultado.append(
            {
                "cenario": nome,
                "produtividade": prod.quantize(Decimal("0.1")),
                "preco": dinheiro(preco),
                "receita": receita,
                "custo": custo,
                "resultado_operacional": operacional,
                "parcela_anual": parcela,
                "saldo_apos_divida": operacional - parcela,
                "cobertura": cobertura,
            }
        )
    return resultado
