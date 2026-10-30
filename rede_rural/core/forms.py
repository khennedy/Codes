from decimal import Decimal

from django import forms

from contas.models import Corretor
from core import regras
from core.models import Configuracao, LeadPublico, ParametroNivel


class SecoesMixin:
    """Agrupa campos em seções (fieldsets) e aplica widgets HTML5 adequados."""

    secoes_campos: list[tuple[str, list[str]]] = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            if isinstance(campo, forms.DateTimeField):
                campo.widget = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")
                campo.input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]
            elif isinstance(campo, forms.DateField):
                campo.widget = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
            elif isinstance(campo.widget, forms.Textarea):
                campo.widget.attrs.setdefault("rows", 3)

    def secoes(self):
        if not self.secoes_campos:
            return [("", list(self))]
        usados, resultado = set(), []
        for titulo, nomes in self.secoes_campos:
            campos = [self[n] for n in nomes if n in self.fields]
            usados.update(nomes)
            if campos:
                resultado.append((titulo, campos))
        resto = [self[n] for n in self.fields if n not in usados]
        if resto:
            resultado.append(("Outros", resto))
        return resultado


class Form(SecoesMixin, forms.Form):
    pass


class ModelForm(SecoesMixin, forms.ModelForm):
    pass


class LeadCompradorForm(ModelForm):
    consentimento = forms.BooleanField(
        label="Autorizo o contato e o uso destes dados apenas para atender meu interesse.", required=True
    )

    class Meta:
        model = LeadPublico
        fields = ["nome", "telefone", "email", "municipio", "mensagem", "consentimento"]
        labels = {"municipio": "Seu município", "mensagem": "O que você procura?"}


class LeadProprietarioForm(LeadCompradorForm):
    class Meta(LeadCompradorForm.Meta):
        labels = {"municipio": "Município do imóvel", "mensagem": "Conte sobre a propriedade (área, atividade)"}


class AtribuirLeadForm(Form):
    corretor = forms.ModelChoiceField(
        queryset=Corretor.objects.filter(status__in=Corretor.STATUS_OPERANTES, creci_verificado=True)
    )


class ConfiguracaoForm(ModelForm):
    secoes_campos = [
        ("Dados da imobiliária (CRECI-J)", ["razao_social", "cnpj", "creci_j", "endereco", "foro", "responsavel_tecnico"]),
        ("Comissões", ["comissao_referencia_pct", "modelo_rateio", "pct_captador_regulamento",
                       "pct_vendedor_regulamento", "pct_central_regulamento"]),
        ("Prazos", ["dias_protecao_comprador", "dias_exclusividade_padrao", "dias_revisao_preco_rural",
                    "dias_acesso_dossie", "dia_vencimento_mensalidade"]),
        ("Faixas de compatibilidade de preço", ["faixa_a_pct", "faixa_b_pct", "faixa_c_pct"]),
        ("Parceiro de crédito", ["parceiro_credito"]),
    ]

    class Meta:
        model = Configuracao
        fields = "__all__"

    def clean(self):
        dados = super().clean()
        soma = sum(
            dados.get(c) or 0
            for c in ("pct_captador_regulamento", "pct_vendedor_regulamento", "pct_central_regulamento")
        )
        if soma != 100:
            raise forms.ValidationError("No modelo do regulamento, captador + vendedor + central deve somar 100%.")
        return dados


ParametroNivelFormSet = forms.modelformset_factory(
    ParametroNivel, fields=["pct_captacao", "pct_venda", "mensalidade", "volume_min_12m"], extra=0
)

NIVEIS_CHOICES = list(regras.ROTULO_NIVEL.items())


class SimuladorVendaForm(Form):
    valor_venda = forms.DecimalField(label="Valor de venda (R$)", initial=Decimal("5000000"), min_value=0)
    comissao_pct = forms.DecimalField(label="Comissão contratual (%)", initial=Decimal("5"), min_value=0, max_value=20)
    nivel_captador = forms.ChoiceField(choices=NIVEIS_CHOICES, initial="partner")
    nivel_vendedor = forms.ChoiceField(choices=NIVEIS_CHOICES, initial="partner")
    modelo = forms.ChoiceField(choices=Configuracao.ModeloRateio.choices, initial=regras.MODELO_NIVEL)


class SimuladorCenariosForm(Form):
    vendas_piloto = forms.IntegerField(initial=6, min_value=0)
    ticket_piloto = forms.DecimalField(label="Ticket médio piloto (R$)", initial=Decimal("3000000"))
    vendas_base = forms.IntegerField(initial=18, min_value=0)
    ticket_base = forms.DecimalField(label="Ticket médio base (R$)", initial=Decimal("4000000"))
    vendas_escala = forms.IntegerField(initial=36, min_value=0)
    ticket_escala = forms.DecimalField(label="Ticket médio escala (R$)", initial=Decimal("5000000"))
    corretores = forms.IntegerField(label="Corretores pagantes", initial=100, min_value=0)
    mensalidade_media = forms.DecimalField(label="Mensalidade média (R$)", initial=Decimal("100"))
    pct_central = forms.DecimalField(
        label="Participação média da central na comissão (%)", initial=Decimal("40"),
        help_text="Ex.: 40% equivale a R$ 100 mil de R$ 250 mil no exemplo Partner/Partner.",
    )


class ViabilidadeForm(Form):
    preco_imovel = forms.DecimalField(label="Preço do imóvel (R$)", initial=Decimal("8000000"))
    area_produtiva_ha = forms.DecimalField(label="Área produtiva (ha)", initial=Decimal("120"))
    produtividade_por_ha = forms.DecimalField(label="Produtividade (unid./ha/ano)", initial=Decimal("35"),
                                              help_text="Ex.: sacas de café por hectare")
    preco_unitario = forms.DecimalField(label="Preço por unidade (R$)", initial=Decimal("1300"))
    custo_por_ha = forms.DecimalField(label="Custo de produção (R$/ha/ano)", initial=Decimal("28000"))
    outros_custos_anuais = forms.DecimalField(label="Outros custos anuais (R$)", initial=Decimal("150000"))
    entrada_pct = forms.DecimalField(label="Entrada (%)", initial=Decimal("40"), min_value=0, max_value=100)
    taxa_anual_pct = forms.DecimalField(label="Taxa de juros (% a.a.)", initial=Decimal("10"), min_value=0)
    prazo_anos = forms.IntegerField(label="Prazo (anos)", initial=10, min_value=1, max_value=40)
