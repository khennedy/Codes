from django import forms

from contas.models import Corretor
from core.choices import APTIDOES, UFS, lista_codigos
from core.forms import Form, ModelForm
from imoveis.models import (
    ContratoRepresentacao,
    DocumentoChecklist,
    FotoImovel,
    Imovel,
    Proprietario,
    VerificacaoBloco,
)

PALAVRAS_PROIBIDAS = ("valorização garantida", "rentabilidade certa", "melhor investimento da região", "lucro garantido")


class ProprietarioForm(ModelForm):
    uf = forms.ChoiceField(label="UF", choices=UFS, initial="MG")
    secoes_campos = [
        ("Identificação", ["tipo", "nome", "cpf_cnpj", "estado_civil", "regime_bens", "conjuge", "representante"]),
        ("Contato", ["telefone", "email", "municipio", "uf"]),
        ("LGPD e observações", ["consentimento_lgpd", "observacoes"]),
    ]

    class Meta:
        model = Proprietario
        exclude = ["captado_por"]


class ImovelForm(ModelForm):
    aptidoes = forms.MultipleChoiceField(
        label="Outras aptidões", choices=APTIDOES, required=False, widget=forms.CheckboxSelectMultiple
    )
    uf = forms.ChoiceField(label="UF", choices=UFS, initial="MG")

    secoes_campos = [
        ("Identificação", ["titulo", "proprietario", "captador", "origem_entrada", "aptidao_principal", "aptidoes"]),
        ("Localização (coordenadas ficam protegidas)", ["municipio", "uf", "regiao", "acesso", "latitude", "longitude"]),
        ("Identificação fundiária", ["matricula", "cartorio", "area_registral_ha", "area_medida_ha", "area_util_ha",
                                     "area_app_rl_ha", "car", "ccir", "nirf", "sigef_certificado"]),
        ("Terra, relevo e fertilidade", ["altitude_m", "declividade", "textura_solo", "mecanizavel_pct",
                                         "data_analise_solo"]),
        ("Recursos hídricos", ["nascentes", "cursos_dagua", "acudes", "pocos", "irrigacao", "area_irrigada_ha",
                               "outorga"]),
        ("Agricultura e silvicultura", ["culturas", "cafe_pes", "cafe_variedades", "cafe_area_ha",
                                        "produtividade_media"]),
        ("Pecuária e infraestrutura", ["rebanho", "lotacao_ua_ha", "pastagem", "casas", "barracoes_m2", "cercas_km",
                                       "energia", "benfeitorias", "bens_incluidos"]),
        ("Comercial", ["preco_pretendido", "condicoes_pagamento", "comissao_pct", "descricao_comercial",
                       "destaques_publicos"]),
    ]

    class Meta:
        model = Imovel
        exclude = [
            "codigo", "status", "publicado", "nivel_anuncio", "parecer_central", "validado_por", "validado_em",
            "enviado_validacao_em", "revisar_preco_em", "valor_mercado", "metodologia_avaliacao", "data_avaliacao",
            "avaliador", "limitacoes_avaliacao", "preco_autorizado", "exibir_preco_publico",
        ]
        widgets = {"sigef_certificado": forms.NullBooleanSelect}

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial.setdefault("aptidoes", lista_codigos(self.instance.aptidoes))
        corretor = usuario.perfil_corretor if usuario else None
        if usuario and not usuario.eh_central:
            del self.fields["captador"]
            self.fields["proprietario"].queryset = Proprietario.objects.filter(captado_por=corretor)
        else:
            self.fields["captador"].queryset = Corretor.objects.filter(status__in=Corretor.STATUS_OPERANTES)

    def clean_aptidoes(self):
        return ",".join(self.cleaned_data["aptidoes"])

    def clean(self):
        dados = super().clean()
        texto = f"{dados.get('descricao_comercial', '')} {dados.get('destaques_publicos', '')}".lower()
        proibidas = [p for p in PALAVRAS_PROIBIDAS if p in texto]
        if proibidas:
            self.add_error(
                "descricao_comercial",
                f"Remova afirmações sem fundamento: {', '.join(proibidas)} (Regulamento de Qualidade, art. 7º).",
            )
        return dados


class DocumentoForm(ModelForm):
    class Meta:
        model = DocumentoChecklist
        fields = ["status", "risco", "emissao", "validade", "responsavel", "prazo", "observacoes", "arquivo"]


DocumentoFormSet = forms.modelformset_factory(DocumentoChecklist, form=DocumentoForm, extra=0)

VerificacaoFormSet = forms.modelformset_factory(VerificacaoBloco, fields=["fonte", "observacao"], extra=0)


class FotoForm(ModelForm):
    class Meta:
        model = FotoImovel
        fields = ["arquivo", "bloco", "descricao", "data_foto", "autor", "autorizada", "publica"]

    def clean(self):
        dados = super().clean()
        if dados.get("publica") and not dados.get("autorizada"):
            self.add_error("publica", "Só fotos com uso autorizado podem ir para o teaser público.")
        return dados


class ContratoForm(ModelForm):
    class Meta:
        model = ContratoRepresentacao
        fields = ["tipo", "data_inicio", "prazo_dias", "renovacao_automatica", "comissao_pct", "preco_autorizado",
                  "excecoes", "assinado", "data_assinatura", "status", "arquivo"]

    def clean(self):
        dados = super().clean()
        if dados.get("status") == ContratoRepresentacao.Status.VIGENTE and not dados.get("assinado"):
            self.add_error("status", "Um contrato só fica vigente depois de assinado.")
        if dados.get("assinado") and not dados.get("data_assinatura"):
            self.add_error("data_assinatura", "Informe a data da assinatura.")
        return dados


class AvaliacaoForm(ModelForm):
    """Deliberação da central: avaliação, preço autorizado, classificação e publicação."""

    secoes_campos = [
        ("Avaliação (três valores distintos)", ["valor_mercado", "metodologia_avaliacao", "data_avaliacao", "avaliador",
                                                "limitacoes_avaliacao", "preco_autorizado", "exibir_preco_publico"]),
        ("Classificação e publicação", ["status", "publicado", "nivel_anuncio", "parecer_central"]),
    ]

    class Meta:
        model = Imovel
        fields = ["valor_mercado", "metodologia_avaliacao", "data_avaliacao", "avaliador", "limitacoes_avaliacao",
                  "preco_autorizado", "exibir_preco_publico", "status", "publicado", "nivel_anuncio",
                  "parecer_central"]

    def clean(self):
        dados = super().clean()
        imovel = self.instance
        status = dados.get("status")
        if dados.get("publicado"):
            if status not in Imovel.STATUS_PUBLICAVEIS:
                self.add_error("publicado", "Só imóveis aprovados (com ou sem ressalvas) podem ser publicados.")
            decisao = imovel.decisao_documental()
            if decisao.codigo in ("bloqueado", "pendente"):
                self.add_error(
                    "publicado", f"Checklist documental: {decisao.rotulo}. Resolva as pendências antes de publicar."
                )
            if not dados.get("preco_autorizado"):
                self.add_error("preco_autorizado", "Informe o preço formalmente autorizado para anúncio.")
            if not imovel.fotos.filter(autorizada=True).exists():
                self.add_error("publicado", "Inclua ao menos uma foto com uso autorizado.")
        if status in (Imovel.Status.RECUSADO, Imovel.Status.PENDENTE) and not dados.get("parecer_central"):
            self.add_error("parecer_central", "Recusa e pendência precisam de fundamentação registrada (art. 12).")
        return dados


class FiltroCatalogoForm(Form):
    q = forms.CharField(label="Busca", required=False)
    uf = forms.ChoiceField(label="UF", choices=[("", "Todas")] + UFS, required=False)
    aptidao = forms.ChoiceField(label="Aptidão", choices=[("", "Todas")] + APTIDOES, required=False)
    area_min = forms.DecimalField(label="Área mínima (ha)", required=False)
    area_max = forms.DecimalField(label="Área máxima (ha)", required=False)
    preco_max = forms.DecimalField(label="Preço máximo (R$)", required=False)
    irrigacao = forms.BooleanField(label="Com irrigação", required=False)
