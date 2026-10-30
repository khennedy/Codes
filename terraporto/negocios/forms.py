from django import forms

from contas.models import Corretor
from core.choices import APTIDOES, UFS, lista_codigos
from core.forms import ModelForm
from imoveis.models import Imovel
from negocios.models import (
    ApuracaoComissao,
    Atividade,
    Comprador,
    Conflito,
    Demanda,
    EncaminhamentoCredito,
    Negociacao,
    ParticipacaoComissao,
    Visita,
)


def corretores_operantes():
    return Corretor.objects.filter(status__in=Corretor.STATUS_OPERANTES, creci_verificado=True)


class CompradorForm(ModelForm):
    uf = forms.ChoiceField(label="UF", choices=UFS, initial="MG")
    secoes_campos = [
        ("Contato (primeira etapa)", ["nome", "tipo", "telefone", "email", "municipio", "uf"]),
        ("Registro", ["corretor", "origem", "etapa_cadastro", "documento", "evidencia_relacionamento",
                      "consentimento_lgpd", "observacoes"]),
    ]

    class Meta:
        model = Comprador
        fields = ["nome", "tipo", "telefone", "email", "municipio", "uf", "corretor", "origem", "etapa_cadastro",
                  "documento", "evidencia_relacionamento", "consentimento_lgpd", "observacoes"]

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["consentimento_lgpd"].required = True
        if usuario and not usuario.eh_central:
            del self.fields["corretor"]
        else:
            self.fields["corretor"].queryset = corretores_operantes()

    def clean(self):
        dados = super().clean()
        if not (dados.get("telefone") or dados.get("email")):
            raise forms.ValidationError("Informe ao menos telefone ou e-mail.")
        return dados


class DemandaForm(ModelForm):
    aptidoes = forms.MultipleChoiceField(
        label="Aptidões", choices=APTIDOES, required=False, widget=forms.CheckboxSelectMultiple
    )
    uf = forms.ChoiceField(label="UF", choices=[("", "Qualquer")] + UFS, required=False)

    class Meta:
        model = Demanda
        exclude = ["comprador", "criado_em"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial.setdefault("aptidoes", lista_codigos(self.instance.aptidoes))

    def clean_aptidoes(self):
        return ",".join(self.cleaned_data["aptidoes"])


class NegociacaoForm(ModelForm):
    class Meta:
        model = Negociacao
        fields = ["imovel", "comprador", "corretor_vendedor", "situacao", "proxima_acao", "proxima_acao_em"]

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        imoveis = Imovel.objects.filter(publicado=True, status__in=Imovel.STATUS_PUBLICAVEIS)
        if usuario and not usuario.eh_central:
            corretor = usuario.perfil_corretor
            del self.fields["corretor_vendedor"]
            self.fields["comprador"].queryset = Comprador.objects.filter(corretor=corretor)
            self.fields["imovel"].queryset = imoveis | Imovel.objects.filter(captador=corretor)
        else:
            self.fields["corretor_vendedor"].queryset = corretores_operantes()
            self.fields["imovel"].queryset = Imovel.objects.exclude(status=Imovel.Status.VENDIDO)

    def clean(self):
        dados = super().clean()
        imovel, comprador = dados.get("imovel"), dados.get("comprador")
        if imovel and comprador and Negociacao.objects.filter(imovel=imovel, comprador=comprador).exists():
            raise forms.ValidationError("Este comprador já está registrado para este imóvel.")
        return dados


class EtapaForm(ModelForm):
    class Meta:
        model = Negociacao
        fields = ["etapa", "valor_proposta", "valor_fechamento", "data_fechamento", "motivo_perda", "proxima_acao",
                  "proxima_acao_em"]

    def clean(self):
        dados = super().clean()
        etapa = dados.get("etapa")
        if etapa == Negociacao.Etapa.CONCLUIDO:
            if not dados.get("valor_fechamento"):
                self.add_error("valor_fechamento", "Informe o valor de fechamento.")
            if not dados.get("data_fechamento"):
                self.add_error("data_fechamento", "Informe a data de fechamento.")
        if etapa == Negociacao.Etapa.PERDIDO and not dados.get("motivo_perda"):
            self.add_error("motivo_perda", "Registre a justificativa da perda.")
        return dados


class AtividadeForm(ModelForm):
    class Meta:
        model = Atividade
        fields = ["tipo", "descricao"]
        widgets = {"descricao": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo"].choices = [
            c for c in Atividade.Tipo.choices if c[0] not in (Atividade.Tipo.REGISTRO, Atividade.Tipo.ETAPA)
        ]


class VisitaForm(ModelForm):
    secoes_campos = [
        ("Agenda", ["data_hora", "objetivo", "participantes", "autorizacao_proprietario", "realizada"]),
        ("Relatório", ["interesses_restricoes", "pontos_apresentados", "perguntas_tecnicas", "condicoes_negociais",
                       "pendencias", "proxima_acao", "consentimentos"]),
    ]

    class Meta:
        model = Visita
        exclude = ["negociacao", "corretor", "criado_em"]

    def clean(self):
        dados = super().clean()
        if not dados.get("autorizacao_proprietario"):
            self.add_error("autorizacao_proprietario", "A visita precisa de autorização do proprietário ou representante.")
        return dados


class ApuracaoStatusForm(ModelForm):
    class Meta:
        model = ApuracaoComissao
        fields = ["status"]


class ParticipacaoForm(ModelForm):
    class Meta:
        model = ParticipacaoComissao
        fields = ["papel", "corretor", "percentual", "observacao", "nota_fiscal_emitida", "pago"]


ParticipacaoFormSet = forms.inlineformset_factory(
    ApuracaoComissao, ParticipacaoComissao, form=ParticipacaoForm, extra=1, can_delete=True
)


class ConflitoForm(ModelForm):
    class Meta:
        model = Conflito
        fields = ["tipo", "negociacao", "imovel", "comprador", "envolvidos", "descricao", "evidencias"]
        widgets = {"envolvidos": forms.CheckboxSelectMultiple}

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["envolvidos"].queryset = Corretor.objects.exclude(status=Corretor.Status.DESLIGADO)
        if usuario and not usuario.eh_central:
            corretor = usuario.perfil_corretor
            self.fields["negociacao"].queryset = Negociacao.objects.filter(corretor_vendedor=corretor) | \
                Negociacao.objects.filter(imovel__captador=corretor)
            self.fields["comprador"].queryset = Comprador.objects.filter(corretor=corretor)
            self.fields["imovel"].queryset = Imovel.objects.filter(publicado=True) | Imovel.objects.filter(captador=corretor)


class ConflitoDecisaoForm(ModelForm):
    class Meta:
        model = Conflito
        fields = ["status", "fundamentacao", "medida"]

    def clean(self):
        dados = super().clean()
        if dados.get("status") in Conflito.STATUS_ENCERRADOS and not dados.get("fundamentacao"):
            self.add_error("fundamentacao", "Registre a fundamentação antes de encerrar.")
        if dados.get("medida") not in (None, "", Conflito.Medida.NENHUMA) and not dados.get("fundamentacao"):
            self.add_error("fundamentacao", "Medidas disciplinares exigem fundamentação e direito de defesa.")
        return dados


class EncaminhamentoForm(ModelForm):
    class Meta:
        model = EncaminhamentoCredito
        fields = ["produto", "valor_estimado", "negociacao", "consentimento"]

    def __init__(self, *args, comprador=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["consentimento"].required = True
        if comprador:
            self.fields["negociacao"].queryset = comprador.negociacoes.all()


class EncaminhamentoStatusForm(ModelForm):
    class Meta:
        model = EncaminhamentoCredito
        fields = ["status", "retorno"]
