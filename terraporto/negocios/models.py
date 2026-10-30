from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from contas.models import Corretor
from core import regras
from core.choices import APTIDOES, lista_codigos, rotulos_aptidao
from imoveis.models import Imovel


class Comprador(models.Model):
    """Registro de comprador por um corretor. Não significa propriedade sobre o cliente
    (Regulamento de Proteção, seção 4): é evidência de participação comercial."""

    class Tipo(models.TextChoices):
        PF = "pf", "Pessoa física"
        PJ = "pj", "Pessoa jurídica"
        INVESTIDOR = "investidor", "Investidor"

    class Origem(models.TextChoices):
        CARTEIRA = "carteira", "Carteira própria do corretor"
        REDE = "rede", "Originado pela rede / vitrine"
        INDICACAO = "indicacao", "Indicação de terceiro sem CRECI (não remunerada)"
        EVENTO = "evento", "Café com corretores / evento"

    class Etapa(models.IntegerChoices):
        BASICO = 1, "1 — Contato básico"
        PERFIL = 2, "2 — Perfil produtivo e orçamento"
        QUALIFICADO = 3, "3 — Documentação / avaliação financeira"

    nome = models.CharField(max_length=150)
    tipo = models.CharField(max_length=12, choices=Tipo.choices, default=Tipo.PF)
    telefone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    documento = models.CharField("CPF/CNPJ (opcional)", max_length=20, blank=True)
    municipio = models.CharField("Município", max_length=80, blank=True)
    uf = models.CharField("UF", max_length=2, default="MG")
    origem = models.CharField(max_length=12, choices=Origem.choices, default=Origem.CARTEIRA)
    etapa_cadastro = models.PositiveSmallIntegerField("Etapa do cadastro", choices=Etapa.choices, default=Etapa.BASICO)
    corretor = models.ForeignKey(Corretor, on_delete=models.PROTECT, related_name="compradores")
    consentimento_lgpd = models.BooleanField(
        "Comprador autorizou o registro dos seus dados para esta finalidade", default=False
    )
    evidencia_relacionamento = models.TextField(
        "Evidência de relacionamento", blank=True,
        help_text="Como conheceu o comprador, contatos anteriores — base para prioridade em caso de duplicidade",
    )
    protecao_ate = models.DateField("Prioridade comercial até", null=True, blank=True)
    chaves = models.CharField(max_length=250, blank=True, editable=False, db_index=True)
    duplicidade_de = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="duplicidades",
        verbose_name="Possível duplicidade de",
    )
    observacoes = models.TextField("Observações", blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return self.nome

    def get_absolute_url(self):
        return reverse("negocios:comprador", args=[self.pk])

    def save(self, *args, **kwargs):
        self.chaves = "|".join(sorted(regras.chaves_contato(self.telefone, self.email, self.documento)))
        super().save(*args, **kwargs)

    @property
    def protegido(self) -> bool:
        return bool(self.protecao_ate and self.protecao_ate >= timezone.localdate())

    def possiveis_duplicidades(self):
        """Registros de outros corretores com o mesmo telefone, e-mail ou documento."""
        chaves = [c for c in self.chaves.split("|") if c]
        if not chaves:
            return Comprador.objects.none()
        filtro = models.Q()
        for chave in chaves:
            filtro |= models.Q(chaves__contains=chave)
        return Comprador.objects.filter(filtro).exclude(pk=self.pk).exclude(corretor=self.corretor)

    def renovar_protecao(self, dias: int):
        self.protecao_ate = regras.renovar_protecao(self.protecao_ate, timezone.localdate(), dias)
        Comprador.objects.filter(pk=self.pk).update(protecao_ate=self.protecao_ate)


class Demanda(models.Model):
    """Perfil de busca do comprador (Central de Demandas — Projeto, seção 11)."""

    class Horizonte(models.TextChoices):
        IMEDIATO = "imediato", "Imediato"
        SEIS_MESES = "6m", "Até 6 meses"
        DOZE_MESES = "12m", "Até 12 meses"
        SEM_PRAZO = "sem_prazo", "Sem prazo definido"

    comprador = models.ForeignKey(Comprador, on_delete=models.CASCADE, related_name="demandas")
    descricao = models.CharField(
        "Descrição", max_length=200, help_text="Ex.: fazenda de café irrigada de R$ 10 a 20 milhões"
    )
    aptidoes = models.CharField(max_length=200, blank=True)
    municipios = models.CharField(
        "Municípios de interesse", max_length=250, blank=True, help_text="Separe por vírgula"
    )
    regiao = models.CharField("Região", max_length=80, blank=True)
    uf = models.CharField("UF", max_length=2, blank=True)
    orcamento_min = models.DecimalField("Orçamento mínimo (R$)", max_digits=14, decimal_places=2, null=True, blank=True)
    orcamento_max = models.DecimalField("Orçamento máximo (R$)", max_digits=14, decimal_places=2, null=True, blank=True)
    area_min_ha = models.DecimalField("Área mínima (ha)", max_digits=10, decimal_places=2, null=True, blank=True)
    area_max_ha = models.DecimalField("Área máxima (ha)", max_digits=10, decimal_places=2, null=True, blank=True)
    exige_irrigacao = models.BooleanField("Exige irrigação", default=False)
    mecanizacao_min_pct = models.DecimalField(
        "Mecanização mínima (%)", max_digits=5, decimal_places=1, null=True, blank=True
    )
    horizonte = models.CharField("Horizonte de compra", max_length=10, choices=Horizonte.choices, default=Horizonte.SEM_PRAZO)
    pretende_financiar = models.BooleanField("Pretende financiar parte da compra", default=False)
    ativa = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return self.descricao

    @property
    def rotulos_aptidoes(self):
        return rotulos_aptidao(self.aptidoes)

    def perfil(self) -> regras.PerfilDemanda:
        return regras.PerfilDemanda(
            orcamento_min=self.orcamento_min,
            orcamento_max=self.orcamento_max,
            area_min=self.area_min_ha,
            area_max=self.area_max_ha,
            aptidoes=set(lista_codigos(self.aptidoes)),
            municipios={m.strip() for m in self.municipios.split(",") if m.strip()},
            regiao=self.regiao,
            uf=self.uf,
            exige_irrigacao=self.exige_irrigacao,
            mecanizacao_min=self.mecanizacao_min_pct,
        )


class Negociacao(models.Model):
    """Oportunidade imóvel × comprador. Funil do Anexo II da Estratégia V2."""

    class Etapa(models.TextChoices):
        NOVO = "novo", "Novo"
        QUALIFICADO = "qualificado", "Qualificado"
        VISITA_AGENDADA = "visita_agendada", "Visita agendada"
        VISITADO = "visitado", "Visitado"
        PROPOSTA = "proposta", "Proposta"
        DILIGENCIA = "diligencia", "Diligência"
        CONTRATO = "contrato", "Contrato"
        CONCLUIDO = "concluido", "Concluído"
        PERDIDO = "perdido", "Perdido"

    ETAPAS_ABERTAS = [
        Etapa.NOVO, Etapa.QUALIFICADO, Etapa.VISITA_AGENDADA, Etapa.VISITADO,
        Etapa.PROPOSTA, Etapa.DILIGENCIA, Etapa.CONTRATO,
    ]

    class OrigemComprador(models.TextChoices):
        A = regras.SITUACAO_A, "A — Comprador da carteira do captador, negociação independente da rede"
        B = regras.SITUACAO_B, "B — Comprador apresentado por outro corretor da rede"
        C = regras.SITUACAO_C, "C — Captação e venda pelo mesmo corretor, dentro da rede"

    imovel = models.ForeignKey(Imovel, on_delete=models.PROTECT, related_name="negociacoes", verbose_name="Imóvel")
    comprador = models.ForeignKey(Comprador, on_delete=models.PROTECT, related_name="negociacoes")
    corretor_vendedor = models.ForeignKey(Corretor, on_delete=models.PROTECT, related_name="vendas")
    situacao = models.CharField(
        "Origem do comprador", max_length=1, choices=OrigemComprador.choices, default=regras.SITUACAO_B
    )
    etapa = models.CharField(max_length=20, choices=Etapa.choices, default=Etapa.NOVO)
    valor_proposta = models.DecimalField("Valor da proposta (R$)", max_digits=14, decimal_places=2, null=True, blank=True)
    valor_fechamento = models.DecimalField("Valor de fechamento (R$)", max_digits=14, decimal_places=2, null=True, blank=True)
    data_fechamento = models.DateField("Data de fechamento", null=True, blank=True)
    motivo_perda = models.CharField("Motivo da perda", max_length=200, blank=True)
    proxima_acao = models.CharField("Próxima ação", max_length=200, blank=True)
    proxima_acao_em = models.DateField("Data da próxima ação", null=True, blank=True)
    dossie_solicitado_em = models.DateTimeField(null=True, blank=True)
    dossie_liberado_ate = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-atualizado_em"]
        verbose_name = "negociação"
        verbose_name_plural = "negociações"
        constraints = [
            models.UniqueConstraint(
                fields=["imovel", "comprador"], name="negociacao_unica_por_imovel_comprador"
            )
        ]

    def __str__(self):
        return f"{self.imovel.codigo} × {self.comprador}"

    def get_absolute_url(self):
        return reverse("negocios:negociacao", args=[self.pk])

    @property
    def aberta(self) -> bool:
        return self.etapa in self.ETAPAS_ABERTAS

    @property
    def dossie_liberado(self) -> bool:
        return bool(self.dossie_liberado_ate and self.dossie_liberado_ate >= timezone.now())

    @property
    def em_disputa(self) -> bool:
        return self.conflitos.exclude(status__in=Conflito.STATUS_ENCERRADOS).exists()


class Atividade(models.Model):
    class Tipo(models.TextChoices):
        REGISTRO = "registro", "Registro da oportunidade"
        CONTATO = "contato", "Contato"
        REUNIAO = "reuniao", "Reunião com o comprador"
        VISITA_AGENDADA = "visita_agendada", "Visita agendada"
        VISITA = "visita", "Visita realizada"
        PROPOSTA = "proposta", "Proposta apresentada"
        NEGOCIACAO = "negociacao", "Negociação documentada"
        DOCUMENTO = "documento", "Documento"
        ETAPA = "etapa", "Mudança de etapa"
        NOTA = "nota", "Anotação"

    negociacao = models.ForeignKey(Negociacao, on_delete=models.CASCADE, related_name="atividades")
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.NOTA)
    descricao = models.TextField("Descrição")
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]

    @property
    def renova_protecao(self) -> bool:
        return self.tipo in regras.ATIVIDADES_QUE_RENOVAM


class Visita(models.Model):
    """Relatório de visita comercial — não se mistura com o dossiê do imóvel (Estratégia V2, seção 09)."""

    negociacao = models.ForeignKey(Negociacao, on_delete=models.CASCADE, related_name="visitas")
    data_hora = models.DateTimeField("Data e hora")
    corretor = models.ForeignKey(Corretor, on_delete=models.PROTECT, related_name="visitas")
    autorizacao_proprietario = models.BooleanField("Visita autorizada pelo proprietário/representante", default=False)
    realizada = models.BooleanField(default=False)
    objetivo = models.CharField(max_length=200)
    participantes = models.CharField(max_length=250, blank=True)
    interesses_restricoes = models.TextField("Interesses e restrições do comprador", blank=True)
    pontos_apresentados = models.TextField(blank=True)
    perguntas_tecnicas = models.TextField("Dúvidas e perguntas técnicas", blank=True)
    condicoes_negociais = models.TextField("Condições negociais discutidas", blank=True)
    pendencias = models.TextField("Pendências, responsáveis e prazo de retorno", blank=True)
    proxima_acao = models.CharField("Próxima ação", max_length=200, blank=True)
    consentimentos = models.CharField("Consentimentos registrados", max_length=250, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_hora"]


class ApuracaoComissao(models.Model):
    class Status(models.TextChoices):
        PREVISTA = "prevista", "Prevista"
        SUSPENSA = "suspensa", "Suspensa (disputa em análise)"
        APROVADA = "aprovada", "Aprovada"
        RECEBIDA = "recebida", "Comissão recebida do cliente"
        REPASSADA = "repassada", "Repasses concluídos"

    negociacao = models.OneToOneField(Negociacao, on_delete=models.CASCADE, related_name="apuracao")
    valor_venda = models.DecimalField(max_digits=14, decimal_places=2)
    comissao_pct = models.DecimalField(max_digits=5, decimal_places=2)
    comissao_total = models.DecimalField(max_digits=14, decimal_places=2)
    modelo = models.CharField(max_length=15, choices=[(regras.MODELO_NIVEL, "Por nível"), (regras.MODELO_REGULAMENTO, "Regulamento 45/45/10")])
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PREVISTA)
    alertas = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    @property
    def soma_participacoes(self) -> Decimal:
        return sum((p.valor for p in self.participacoes.all()), Decimal("0"))

    @property
    def fechada(self) -> bool:
        return self.soma_participacoes == self.comissao_total


class ParticipacaoComissao(models.Model):
    class Papel(models.TextChoices):
        CAPTADOR = "captador", "Captador"
        VENDEDOR = "vendedor", "Vendedor"
        INDICACAO = "indicacao", "Indicação do comprador (corretor)"
        ATENDIMENTO = "atendimento", "Atendimento / negociação"
        CENTRAL = "central", "Central de negócios"

    apuracao = models.ForeignKey(ApuracaoComissao, on_delete=models.CASCADE, related_name="participacoes")
    papel = models.CharField(max_length=15, choices=Papel.choices)
    corretor = models.ForeignKey(Corretor, null=True, blank=True, on_delete=models.PROTECT)
    percentual = models.DecimalField("% da comissão", max_digits=6, decimal_places=2)
    valor = models.DecimalField(max_digits=14, decimal_places=2)
    nota_fiscal_emitida = models.BooleanField(default=False)
    pago = models.BooleanField(default=False)
    observacao = models.CharField("Observação", max_length=250, blank=True)

    class Meta:
        ordering = ["id"]


class Conflito(models.Model):
    """Procedimento de resolução de conflitos (Regulamento de Proteção, seções 5, 6, 12 e 13)."""

    class Tipo(models.TextChoices):
        DUPLICIDADE = "duplicidade", "Comprador apresentado por mais de um corretor"
        ORIGEM = "origem", "Origem da captação"
        RATEIO = "rateio", "Divergência de rateio"
        CONTORNO = "contorno", "Contorno comercial"
        CADASTRO = "cadastro", "Cadastro indevido / informação falsa"
        OUTRO = "outro", "Outro"

    class Status(models.TextChoices):
        REGISTRADO = "registrado", "1. Reclamação registrada"
        COMUNICADO = "comunicado", "2. Envolvidos comunicados"
        EVIDENCIAS = "evidencias", "3. Apresentação de evidências"
        ANALISE = "analise", "4. Análise dos registros"
        PROPOSTA = "proposta", "5. Proposta fundamentada de solução"
        MEDIACAO = "mediacao", "6. Mediação externa"
        JURIDICO = "juridico", "7. Encaminhado ao jurídico"
        RESOLVIDO = "resolvido", "Resolvido"
        ARQUIVADO = "arquivado", "Arquivado"

    STATUS_ENCERRADOS = [Status.RESOLVIDO, Status.ARQUIVADO]

    class Medida(models.TextChoices):
        NENHUMA = "nenhuma", "Nenhuma"
        ADVERTENCIA = "advertencia", "Advertência formal"
        SUSPENSAO = "suspensao", "Suspensão temporária do acesso"
        RESTRICAO = "restricao", "Restrição de funcionalidades"
        RESCISAO = "rescisao", "Rescisão da parceria"

    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    negociacao = models.ForeignKey(Negociacao, null=True, blank=True, on_delete=models.SET_NULL, related_name="conflitos",
                                   verbose_name="Negociação")
    imovel = models.ForeignKey(Imovel, null=True, blank=True, on_delete=models.SET_NULL, related_name="conflitos",
                               verbose_name="Imóvel")
    comprador = models.ForeignKey(Comprador, null=True, blank=True, on_delete=models.SET_NULL, related_name="conflitos")
    reclamante = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="conflitos_abertos")
    envolvidos = models.ManyToManyField(Corretor, blank=True, related_name="conflitos")
    descricao = models.TextField("Descrição")
    evidencias = models.TextField("Evidências", blank=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.REGISTRADO)
    fundamentacao = models.TextField("Fundamentação da decisão", blank=True)
    medida = models.CharField("Medida disciplinar", max_length=15, choices=Medida.choices, default=Medida.NENHUMA)
    decidido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="conflitos_decididos"
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    encerrado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Conflito #{self.pk} — {self.get_tipo_display()}"

    def interessado(self, usuario) -> bool:
        """Quem é parte da disputa não decide sozinho o resultado (seção 12)."""
        if usuario.pk == self.reclamante_id:
            return True
        corretor = usuario.perfil_corretor
        return bool(corretor and self.envolvidos.filter(pk=corretor.pk).exists())


class EncaminhamentoCredito(models.Model):
    """Fluxo de crédito separado: a plataforma envia apenas os dados necessários,
    com consentimento, e guarda só o status — nunca dados financeiros (Estratégia V2, seções 02 e 12)."""

    class Produto(models.TextChoices):
        CREDITO_RURAL = "credito_rural", "Crédito rural"
        AQUISICAO = "aquisicao", "Crédito para aquisição de propriedade"
        FINANCIAMENTO = "financiamento", "Financiamento imobiliário"
        CONSORCIO = "consorcio", "Consórcio"
        DIAGNOSTICO = "diagnostico", "Diagnóstico 360°"

    class Status(models.TextChoices):
        SOLICITADO = "solicitado", "Solicitado"
        ENVIADO = "enviado", "Enviado ao parceiro"
        EM_ATENDIMENTO = "em_atendimento", "Em atendimento pelo parceiro"
        CONCLUIDO = "concluido", "Atendimento concluído"
        CANCELADO = "cancelado", "Cancelado"

    comprador = models.ForeignKey(Comprador, on_delete=models.CASCADE, related_name="encaminhamentos")
    negociacao = models.ForeignKey(Negociacao, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="Negociação")
    produto = models.CharField(max_length=15, choices=Produto.choices)
    valor_estimado = models.DecimalField("Valor estimado da necessidade (R$)", max_digits=14, decimal_places=2, null=True, blank=True)
    consentimento = models.BooleanField(
        "O comprador autorizou o compartilhamento de nome, contato e necessidade com o parceiro de crédito",
        default=False,
    )
    dados_compartilhados = models.CharField(max_length=250, editable=False, blank=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.SOLICITADO)
    retorno = models.CharField(
        "Retorno do parceiro (somente status)", max_length=250, blank=True,
        help_text="Não registre endividamento, consultas restritivas ou dados financeiros",
    )
    solicitado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
