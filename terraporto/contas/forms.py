from django import forms
from django.contrib.auth.forms import UserCreationForm

from contas.models import Corretor, Usuario
from core.choices import UFS
from core.forms import ModelForm, SecoesMixin


class InscricaoForm(SecoesMixin, UserCreationForm):
    """Processo de entrada (Estratégia V2, seção 06): inscrição → verificação CRECI → aprovação."""

    first_name = forms.CharField(label="Nome", max_length=150)
    last_name = forms.CharField(label="Sobrenome", max_length=150)
    email = forms.EmailField(label="E-mail")
    telefone = forms.CharField(max_length=30)
    creci = forms.CharField(label="CRECI", max_length=20)
    creci_uf = forms.ChoiceField(label="UF do CRECI", choices=UFS, initial="MG")
    cpf = forms.CharField(label="CPF", max_length=14)
    municipio = forms.CharField(label="Município", max_length=80)
    uf = forms.ChoiceField(label="UF", choices=UFS, initial="MG")
    regiao_atuacao = forms.CharField(label="Região de atuação", max_length=120, required=False)
    especialidades = forms.CharField(max_length=200, required=False, help_text="Ex.: café, pecuária de leite, grãos")
    experiencia = forms.CharField(label="Experiência e referências", widget=forms.Textarea, required=False)
    aceite_etica_lgpd = forms.BooleanField(
        label="Li e aceito o código de ética e a política de proteção de dados da rede", required=True
    )

    secoes_campos = [
        ("Acesso", ["username", "password1", "password2"]),
        ("Dados pessoais", ["first_name", "last_name", "email", "telefone", "cpf", "municipio", "uf"]),
        ("Habilitação profissional", ["creci", "creci_uf", "regiao_atuacao", "especialidades", "experiencia"]),
        ("Compromissos", ["aceite_etica_lgpd"]),
    ]

    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = ("username",)

    def save(self, commit=True):
        from django.utils import timezone

        usuario = super().save(commit=False)
        usuario.first_name = self.cleaned_data["first_name"]
        usuario.last_name = self.cleaned_data["last_name"]
        usuario.email = self.cleaned_data["email"]
        usuario.telefone = self.cleaned_data["telefone"]
        usuario.papel = Usuario.Papel.CORRETOR
        usuario.save()
        Corretor.objects.create(
            usuario=usuario,
            creci=self.cleaned_data["creci"],
            creci_uf=self.cleaned_data["creci_uf"],
            cpf=self.cleaned_data["cpf"],
            municipio=self.cleaned_data["municipio"],
            uf=self.cleaned_data["uf"],
            regiao_atuacao=self.cleaned_data["regiao_atuacao"],
            especialidades=self.cleaned_data["especialidades"],
            experiencia=self.cleaned_data["experiencia"],
            aceite_etica_lgpd=True,
            aceite_em=timezone.now(),
        )
        return usuario


class CorretorCentralForm(ModelForm):
    secoes_campos = [
        ("Credenciamento", ["status", "nivel", "creci_verificado", "treinamento_inicial", "nota_prova_pratica",
                            "data_adesao"]),
        ("Dados profissionais", ["creci", "creci_uf", "cpf", "municipio", "uf", "regiao_atuacao", "especialidades",
                                 "experiencia"]),
        ("Uso interno", ["observacoes_central"]),
    ]

    class Meta:
        model = Corretor
        exclude = ["usuario", "aceite_etica_lgpd", "aceite_em"]


class PerfilForm(ModelForm):
    class Meta:
        model = Corretor
        fields = ["municipio", "uf", "regiao_atuacao", "especialidades", "experiencia"]
