from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property


class Usuario(AbstractUser):
    class Papel(models.TextChoices):
        CENTRAL = "central", "Central (qualidade e direção)"
        CORRETOR = "corretor", "Corretor associado"

    papel = models.CharField(max_length=20, choices=Papel.choices, default=Papel.CORRETOR)
    telefone = models.CharField(max_length=30, blank=True)

    @property
    def eh_central(self) -> bool:
        return self.is_superuser or self.papel == self.Papel.CENTRAL

    @cached_property
    def perfil_corretor(self):
        try:
            return self.corretor
        except ObjectDoesNotExist:
            return None

    def __str__(self):
        return self.get_full_name() or self.username


class Corretor(models.Model):
    """Corretor associado. Níveis são credenciamento comercial, não cargos (Estratégia V2, seção 06)."""

    class Nivel(models.TextChoices):
        PLENO = "pleno", "Pleno"
        SENIOR = "senior", "Sênior"
        MASTER = "master", "Master"
        PARTNER = "partner", "Partner"

    class Status(models.TextChoices):
        INSCRITO = "inscrito", "Inscrito"
        EM_ANALISE = "em_analise", "Em análise"
        APROVADO_CONDICIONAL = "aprovado_condicional", "Aprovado condicionado"
        ATIVO = "ativo", "Ativo"
        SUSPENSO = "suspenso", "Suspenso"
        DESLIGADO = "desligado", "Desligado"

    STATUS_OPERANTES = {Status.ATIVO, Status.APROVADO_CONDICIONAL}

    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE, related_name="corretor")
    creci = models.CharField("CRECI", max_length=20)
    creci_uf = models.CharField("UF do CRECI", max_length=2, default="MG")
    creci_verificado = models.BooleanField("CRECI verificado pela central", default=False)
    cpf = models.CharField("CPF", max_length=14, blank=True)
    municipio = models.CharField("Município", max_length=80, blank=True)
    uf = models.CharField("UF", max_length=2, default="MG")
    regiao_atuacao = models.CharField("Região de atuação", max_length=120, blank=True)
    especialidades = models.CharField(
        "Especialidades", max_length=200, blank=True, help_text="Ex.: café, pecuária de leite, grãos"
    )
    experiencia = models.TextField("Experiência e referências", blank=True)
    nivel = models.CharField("Nível", max_length=10, choices=Nivel.choices, default=Nivel.PLENO)
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.INSCRITO)
    aceite_etica_lgpd = models.BooleanField("Aceite do código de ética e da política LGPD", default=False)
    aceite_em = models.DateTimeField(null=True, blank=True)
    treinamento_inicial = models.BooleanField("Treinamento inicial concluído", default=False)
    nota_prova_pratica = models.DecimalField(
        "Nota da prova prática (0–10)", max_digits=4, decimal_places=1, null=True, blank=True
    )
    data_adesao = models.DateField("Data de adesão", null=True, blank=True)
    observacoes_central = models.TextField("Observações da central", blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["usuario__first_name", "usuario__username"]
        verbose_name_plural = "corretores"

    def __str__(self):
        return f"{self.usuario} (CRECI {self.creci}/{self.creci_uf})"

    @property
    def nome(self) -> str:
        return str(self.usuario)

    @property
    def pode_operar(self) -> bool:
        return self.status in self.STATUS_OPERANTES and self.creci_verificado

    def volume_12_meses(self) -> Decimal:
        """VGV de negócios concluídos nos últimos 12 meses em que atuou como captador ou vendedor."""
        from negocios.models import Negociacao

        desde = timezone.localdate() - timezone.timedelta(days=365)
        negocios = Negociacao.objects.filter(
            etapa=Negociacao.Etapa.CONCLUIDO, data_fechamento__gte=desde
        ).filter(models.Q(corretor_vendedor=self) | models.Q(imovel__captador=self))
        total = negocios.aggregate(t=models.Sum("valor_fechamento"))["t"]
        return total or Decimal("0")


class Trilha(models.Model):
    """Trilha da Universidade Rural (Estratégia V2, seção 06)."""

    nome = models.CharField(max_length=120, unique=True)
    descricao = models.TextField(blank=True)
    carga_horaria = models.PositiveIntegerField("Carga horária (h)", default=4)
    obrigatoria_ingresso = models.BooleanField("Obrigatória para ingresso", default=False)
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["ordem", "nome"]

    def __str__(self):
        return self.nome


class ProgressoTrilha(models.Model):
    class Status(models.TextChoices):
        INSCRITO = "inscrito", "Inscrito"
        AGUARDANDO = "aguardando", "Conclusão informada — aguardando validação"
        CONCLUIDO = "concluido", "Concluído"

    corretor = models.ForeignKey(Corretor, on_delete=models.CASCADE, related_name="trilhas")
    trilha = models.ForeignKey(Trilha, on_delete=models.CASCADE, related_name="progressos")
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.INSCRITO)
    concluido_em = models.DateField(null=True, blank=True)
    validado_por = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        unique_together = ("corretor", "trilha")


class Mensalidade(models.Model):
    """Mensalidade vinculada a acesso à tecnologia, suporte e formação (Estratégia V2, seção 13)."""

    class Status(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        PAGA = "paga", "Paga"
        CANCELADA = "cancelada", "Cancelada"

    corretor = models.ForeignKey(Corretor, on_delete=models.CASCADE, related_name="mensalidades")
    competencia = models.DateField("Competência", help_text="Primeiro dia do mês de referência")
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDENTE)
    vencimento = models.DateField()
    paga_em = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-competencia", "corretor"]
        unique_together = ("corretor", "competencia")

    @property
    def atrasada(self) -> bool:
        return self.status == self.Status.PENDENTE and self.vencimento < timezone.localdate()
