from decimal import Decimal

from django.conf import settings
from django.db import models

from core import regras


class Configuracao(models.Model):
    """Parâmetros comerciais da rede (registro único). Valores iniciais vêm dos documentos-base."""

    class ModeloRateio(models.TextChoices):
        NIVEL = regras.MODELO_NIVEL, "Por nível (Estratégia V2: % sobre o valor de venda)"
        REGULAMENTO = regras.MODELO_REGULAMENTO, "Regulamento de parcerias (45/45/10 da comissão)"

    razao_social = models.CharField("Razão social", max_length=150, default="[RAZÃO SOCIAL A DEFINIR]")
    cnpj = models.CharField("CNPJ", max_length=20, default="[A DEFINIR]")
    creci_j = models.CharField("CRECI-J", max_length=20, default="[A DEFINIR]")
    endereco = models.CharField("Endereço da sede", max_length=200, default="[A DEFINIR]")
    foro = models.CharField("Comarca do foro", max_length=80, default="[A DEFINIR]")
    responsavel_tecnico = models.CharField("Responsável técnico (CRECI)", max_length=120, default="[A DEFINIR]")

    comissao_referencia_pct = models.DecimalField(
        "Comissão de referência ao vendedor (%)", max_digits=5, decimal_places=2, default=Decimal("5.00")
    )
    modelo_rateio = models.CharField("Modelo de rateio", max_length=15, choices=ModeloRateio.choices, default=ModeloRateio.NIVEL)
    pct_captador_regulamento = models.DecimalField("Regulamento: captador (% da comissão)", max_digits=5, decimal_places=2, default=Decimal("45"))
    pct_vendedor_regulamento = models.DecimalField("Regulamento: vendedor (% da comissão)", max_digits=5, decimal_places=2, default=Decimal("45"))
    pct_central_regulamento = models.DecimalField("Regulamento: central (% da comissão)", max_digits=5, decimal_places=2, default=Decimal("10"))

    dias_protecao_comprador = models.PositiveIntegerField("Prioridade comercial do comprador (dias)", default=30)
    dias_exclusividade_padrao = models.PositiveIntegerField("Prazo padrão de exclusividade (dias)", default=180)
    dias_revisao_preco_rural = models.PositiveIntegerField("Revisão de preço — imóveis rurais (dias)", default=180)
    dias_acesso_dossie = models.PositiveIntegerField("Validade do acesso ao data room (dias)", default=15)

    faixa_a_pct = models.DecimalField("Limite da faixa A (%)", max_digits=5, decimal_places=2, default=Decimal("5"))
    faixa_b_pct = models.DecimalField("Limite da faixa B (%)", max_digits=5, decimal_places=2, default=Decimal("10"))
    faixa_c_pct = models.DecimalField("Limite da faixa C (%)", max_digits=5, decimal_places=2, default=Decimal("15"))

    parceiro_credito = models.CharField(
        "Parceiro de crédito", max_length=120, default="Hábil Assessoria e Consultoria"
    )
    dia_vencimento_mensalidade = models.PositiveIntegerField("Dia de vencimento da mensalidade", default=10)

    class Meta:
        verbose_name = "configuração"
        verbose_name_plural = "configuração"

    def __str__(self):
        return "Configuração da rede"

    @classmethod
    def atual(cls) -> "Configuracao":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def limites_faixa(self):
        return (self.faixa_a_pct, self.faixa_b_pct, self.faixa_c_pct)

    @property
    def pct_regulamento(self):
        return (self.pct_captador_regulamento, self.pct_vendedor_regulamento, self.pct_central_regulamento)


class ParametroNivel(models.Model):
    nivel = models.CharField(max_length=10, unique=True, choices=list(regras.ROTULO_NIVEL.items()))
    pct_captacao = models.DecimalField("Captação (% do preço)", max_digits=5, decimal_places=2)
    pct_venda = models.DecimalField("Venda (% do preço)", max_digits=5, decimal_places=2)
    mensalidade = models.DecimalField(max_digits=10, decimal_places=2)
    volume_min_12m = models.DecimalField("Volume mínimo 12 meses (R$)", max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["volume_min_12m"]
        verbose_name_plural = "parâmetros por nível"

    def __str__(self):
        return self.get_nivel_display()

    @classmethod
    def como_regras(cls) -> dict[str, regras.ParamNivel]:
        params = dict(regras.PARAMETROS_PADRAO)
        for p in cls.objects.all():
            params[p.nivel] = regras.ParamNivel(
                p.nivel, p.pct_captacao, p.pct_venda, p.mensalidade, p.volume_min_12m
            )
        return params


class LogAuditoria(models.Model):
    """Trilha de auditoria de alterações e acessos (Estratégia V2, seções 07 e 16)."""

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    acao = models.CharField(max_length=60)
    objeto_tipo = models.CharField(max_length=60, blank=True)
    objeto_id = models.PositiveBigIntegerField(null=True, blank=True)
    descricao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["objeto_tipo", "objeto_id"])]

    def __str__(self):
        return f"{self.criado_em:%d/%m/%Y %H:%M} {self.usuario} {self.acao}"


class LeadPublico(models.Model):
    """Contato recebido pela vitrine pública (cadastro progressivo, primeira etapa)."""

    class Tipo(models.TextChoices):
        COMPRADOR = "comprador", "Interesse de compra"
        PROPRIETARIO = "proprietario", "Proprietário quer vender"

    class Status(models.TextChoices):
        NOVO = "novo", "Novo"
        ATRIBUIDO = "atribuido", "Atribuído a corretor"
        DESCARTADO = "descartado", "Descartado"

    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    nome = models.CharField(max_length=120)
    telefone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    municipio = models.CharField("Município", max_length=80, blank=True)
    imovel = models.ForeignKey("imoveis.Imovel", null=True, blank=True, on_delete=models.SET_NULL, verbose_name="Imóvel")
    mensagem = models.TextField(blank=True)
    consentimento = models.BooleanField(default=False)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.NOVO)
    atribuido_a = models.ForeignKey("contas.Corretor", null=True, blank=True, on_delete=models.SET_NULL)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
