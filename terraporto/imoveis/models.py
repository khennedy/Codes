from datetime import timedelta

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from contas.models import Corretor
from core import regras
from core.choices import APTIDOES, lista_codigos, rotulos_aptidao
from imoveis import checklist


class Proprietario(models.Model):
    class Tipo(models.TextChoices):
        PF = "pf", "Pessoa física"
        PJ = "pj", "Pessoa jurídica"

    tipo = models.CharField(max_length=2, choices=Tipo.choices, default=Tipo.PF)
    nome = models.CharField("Nome / razão social", max_length=150)
    cpf_cnpj = models.CharField("CPF/CNPJ", max_length=20, blank=True)
    estado_civil = models.CharField(max_length=40, blank=True)
    regime_bens = models.CharField("Regime de bens", max_length=60, blank=True)
    conjuge = models.CharField("Cônjuge / anuente", max_length=150, blank=True)
    representante = models.CharField("Representante legal / procurador", max_length=150, blank=True)
    telefone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    municipio = models.CharField("Município", max_length=80, blank=True)
    uf = models.CharField("UF", max_length=2, default="MG")
    consentimento_lgpd = models.BooleanField(
        "Consentiu com o tratamento de dados para a intermediação", default=False
    )
    captado_por = models.ForeignKey(
        Corretor, null=True, blank=True, on_delete=models.SET_NULL, related_name="proprietarios"
    )
    observacoes = models.TextField("Observações", blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Imovel(models.Model):
    """Cadastro técnico rural (Estratégia V2, seção 08; Anexo I)."""

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", "Rascunho"
        EM_VALIDACAO = "em_validacao", "Em validação"
        APROVADO = "aprovado", "Aprovado"
        APROVADO_RESSALVAS = "aprovado_ressalvas", "Aprovado com ressalvas"
        PENDENTE = "pendente_regularizacao", "Pendente de regularização"
        RECUSADO = "recusado", "Recusado"
        SUSPENSO = "suspenso", "Suspenso"
        VENDIDO = "vendido", "Vendido"

    STATUS_PUBLICAVEIS = {Status.APROVADO, Status.APROVADO_RESSALVAS}

    class Origem(models.TextChoices):
        CORRETOR = "corretor", "Corretor associado"
        PROPRIETARIO = "proprietario", "Proprietário diretamente"
        INSTITUCIONAL = "institucional", "Parceiro institucional (inventariante, administrador...)"

    class Declividade(models.TextChoices):
        PLANO = "plano", "Plano"
        SUAVE = "suave_ondulado", "Suave ondulado"
        ONDULADO = "ondulado", "Ondulado"
        FORTE = "forte_ondulado", "Forte ondulado"
        MONTANHOSO = "montanhoso", "Montanhoso"

    class Outorga(models.TextChoices):
        NAO_INFORMADO = "nao_informado", "Não informado"
        POSSUI = "possui", "Possui"
        EM_PROCESSO = "em_processo", "Em processo"
        NAO_POSSUI = "nao_possui", "Não possui"
        NAO_APLICA = "nao_aplica", "Não se aplica"

    class NivelAnuncio(models.TextChoices):
        ESSENCIAL = "essencial", "Padrão Essencial"
        PREMIUM = "premium", "Padrão Premium"
        INVESTIDOR = "investidor", "Padrão Investidor"

    codigo = models.CharField(max_length=20, unique=True, blank=True)
    titulo = models.CharField("Título comercial", max_length=150)
    proprietario = models.ForeignKey(Proprietario, on_delete=models.PROTECT, related_name="imoveis")
    captador = models.ForeignKey(Corretor, on_delete=models.PROTECT, related_name="captacoes")
    origem_entrada = models.CharField("Origem da captação", max_length=15, choices=Origem.choices, default=Origem.CORRETOR)

    # Localização (coordenadas são protegidas: só central, captador e data room)
    municipio = models.CharField("Município", max_length=80)
    uf = models.CharField("UF", max_length=2, default="MG")
    regiao = models.CharField("Região", max_length=80, blank=True, help_text="Ex.: Sul de Minas")
    acesso = models.CharField("Acesso", max_length=200, blank=True, help_text="Distância da sede, tipo de estrada")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Identificação fundiária
    matricula = models.CharField("Matrícula(s)", max_length=120, blank=True)
    cartorio = models.CharField("Cartório de registro", max_length=120, blank=True)
    area_registral_ha = models.DecimalField("Área registral (ha)", max_digits=10, decimal_places=2, null=True, blank=True)
    area_medida_ha = models.DecimalField("Área medida (ha)", max_digits=10, decimal_places=2, null=True, blank=True)
    area_util_ha = models.DecimalField("Área útil/produtiva (ha)", max_digits=10, decimal_places=2, null=True, blank=True)
    area_app_rl_ha = models.DecimalField("APP + Reserva Legal (ha)", max_digits=10, decimal_places=2, null=True, blank=True)
    car = models.CharField("Nº do recibo CAR", max_length=80, blank=True)
    ccir = models.CharField("CCIR", max_length=40, blank=True)
    nirf = models.CharField("NIRF / ITR", max_length=40, blank=True)
    sigef_certificado = models.BooleanField("Certificação SIGEF", null=True, blank=True)

    # Terra, relevo e fertilidade
    aptidao_principal = models.CharField("Aptidão principal", max_length=20, choices=APTIDOES)
    aptidoes = models.CharField("Aptidões", max_length=200, blank=True)
    altitude_m = models.PositiveIntegerField("Altitude (m)", null=True, blank=True)
    declividade = models.CharField(max_length=20, choices=Declividade.choices, blank=True)
    textura_solo = models.CharField("Textura / classe de solo", max_length=80, blank=True)
    mecanizavel_pct = models.DecimalField("Área mecanizável (%)", max_digits=5, decimal_places=1, null=True, blank=True)
    data_analise_solo = models.DateField("Data da análise de solo", null=True, blank=True)

    # Recursos hídricos
    nascentes = models.PositiveIntegerField(null=True, blank=True)
    cursos_dagua = models.CharField("Cursos d'água", max_length=120, blank=True)
    acudes = models.PositiveIntegerField("Açudes / represas", null=True, blank=True)
    pocos = models.PositiveIntegerField("Poços", null=True, blank=True)
    irrigacao = models.BooleanField("Possui irrigação", default=False)
    area_irrigada_ha = models.DecimalField("Área irrigada (ha)", max_digits=10, decimal_places=2, null=True, blank=True)
    outorga = models.CharField("Outorga de água", max_length=15, choices=Outorga.choices, default=Outorga.NAO_INFORMADO)

    # Agricultura e silvicultura
    culturas = models.TextField("Culturas por talhão", blank=True, help_text="Talhão, cultura, área, idade, produtividade dos últimos 2 ciclos")
    cafe_pes = models.PositiveIntegerField("Pés de café", null=True, blank=True)
    cafe_variedades = models.CharField("Variedades de café", max_length=120, blank=True)
    cafe_area_ha = models.DecimalField("Área de café (ha)", max_digits=10, decimal_places=2, null=True, blank=True)
    produtividade_media = models.CharField("Produtividade média (2 últimos ciclos)", max_length=120, blank=True)

    # Pecuária e infraestrutura
    rebanho = models.CharField("Rebanho (espécie, categoria, cabeças)", max_length=150, blank=True)
    lotacao_ua_ha = models.DecimalField("Lotação (UA/ha)", max_digits=5, decimal_places=2, null=True, blank=True)
    pastagem = models.CharField("Forrageira e estado do pasto", max_length=150, blank=True)
    casas = models.PositiveIntegerField("Casas", null=True, blank=True)
    barracoes_m2 = models.PositiveIntegerField("Barracões (m²)", null=True, blank=True)
    cercas_km = models.DecimalField("Cercas (km)", max_digits=6, decimal_places=1, null=True, blank=True)
    energia = models.CharField("Energia", max_length=80, blank=True, help_text="Monofásica, trifásica, solar...")
    benfeitorias = models.TextField("Outras benfeitorias", blank=True, help_text="Currais, silos, terreiros, secadores, ordenha, estradas internas")
    bens_incluidos = models.TextField("Bens móveis incluídos na venda", blank=True)

    # Precificação (três valores distintos — Regulamento de Avaliação, art. 10)
    preco_pretendido = models.DecimalField("Valor pretendido pelo proprietário (R$)", max_digits=14, decimal_places=2)
    valor_mercado = models.DecimalField("Valor de mercado estimado (R$)", max_digits=14, decimal_places=2, null=True, blank=True)
    metodologia_avaliacao = models.CharField("Metodologia", max_length=150, blank=True)
    data_avaliacao = models.DateField("Data de referência da avaliação", null=True, blank=True)
    avaliador = models.CharField("Responsável pela avaliação", max_length=120, blank=True)
    limitacoes_avaliacao = models.TextField("Limitações da avaliação", blank=True)
    preco_autorizado = models.DecimalField("Preço autorizado para anúncio (R$)", max_digits=14, decimal_places=2, null=True, blank=True)
    condicoes_pagamento = models.CharField("Condições de pagamento", max_length=200, blank=True)
    comissao_pct = models.DecimalField("Comissão (%)", max_digits=5, decimal_places=2, default=5)
    exibir_preco_publico = models.BooleanField("Exibir preço na vitrine pública", default=False)

    descricao_comercial = models.TextField(
        "Descrição comercial", blank=True,
        help_text="Sem promessas como 'valorização garantida' ou 'rentabilidade certa'.",
    )
    destaques_publicos = models.CharField(
        "Destaques do teaser público", max_length=250, blank=True, help_text="Separe por ponto e vírgula"
    )

    status = models.CharField(max_length=25, choices=Status.choices, default=Status.RASCUNHO)
    publicado = models.BooleanField("Publicado no catálogo", default=False)
    nivel_anuncio = models.CharField("Padrão do anúncio", max_length=12, choices=NivelAnuncio.choices, default=NivelAnuncio.ESSENCIAL)
    parecer_central = models.TextField("Parecer da central", blank=True)
    validado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    validado_em = models.DateTimeField(null=True, blank=True)
    enviado_validacao_em = models.DateTimeField(null=True, blank=True)
    revisar_preco_em = models.DateField("Próxima revisão de preço", null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "imóvel"
        verbose_name_plural = "imóveis"

    def __str__(self):
        return f"{self.codigo} — {self.titulo}"

    def save(self, *args, **kwargs):
        if self.aptidao_principal and self.aptidao_principal not in lista_codigos(self.aptidoes):
            self.aptidoes = ",".join([self.aptidao_principal, *lista_codigos(self.aptidoes)])
        super().save(*args, **kwargs)
        if not self.codigo:
            self.codigo = f"TP-{self.criado_em:%Y}-{self.pk:04d}"
            Imovel.objects.filter(pk=self.pk).update(codigo=self.codigo)

    def get_absolute_url(self):
        return reverse("imoveis:detalhe", args=[self.pk])

    # ----- leitura derivada -------------------------------------------------
    @property
    def area_total_ha(self):
        return self.area_medida_ha or self.area_registral_ha

    @property
    def preco_referencia_anuncio(self):
        return self.preco_autorizado or self.preco_pretendido

    @property
    def preco_por_ha(self):
        area = self.area_total_ha
        return (self.preco_referencia_anuncio / area) if area else None

    @property
    def rotulos_aptidoes(self):
        return rotulos_aptidao(self.aptidoes)

    @property
    def lista_destaques(self):
        return [d.strip() for d in self.destaques_publicos.split(";") if d.strip()]

    def faixa_preco(self, config=None):
        from core.models import Configuracao

        config = config or Configuracao.atual()
        preco = self.preco_autorizado or self.preco_pretendido
        return regras.classificar_preco(preco, self.valor_mercado, config.limites_faixa)

    def contrato_vigente(self):
        hoje = timezone.localdate()
        return (
            self.contratos.filter(assinado=True, status=ContratoRepresentacao.Status.VIGENTE, data_fim__gte=hoje)
            .order_by("-data_fim")
            .first()
        )

    def decisao_documental(self) -> regras.ResultadoDecisao:
        itens = [
            regras.ItemDecisao(d.codigo, d.descricao, d.essencial, d.status, d.risco, d.vencido)
            for d in self.documentos.all()
        ]
        return regras.decidir_publicacao(itens, autorizacao_assinada=self.contrato_vigente() is not None)

    def qualidade_dossie(self) -> int:
        """Percentual de completude do cadastro técnico (campos-chave preenchidos + evidências)."""
        campos = [
            self.matricula, self.cartorio, self.area_registral_ha, self.area_util_ha, self.car, self.ccir,
            self.altitude_m, self.declividade, self.textura_solo, self.mecanizavel_pct, self.cursos_dagua,
            self.energia, self.benfeitorias, self.valor_mercado, self.descricao_comercial,
        ]
        pontos = sum(1 for c in campos if c not in (None, ""))
        total = len(campos) + 3
        if self.fotos.exists():
            pontos += 1
        docs = list(self.documentos.all())
        if docs:
            ok = sum(1 for d in docs if d.status in regras.STATUS_OK)
            pontos += 2 * ok / len(docs)
        return round(100 * pontos / total)

    def criar_checklist(self):
        existentes = set(self.documentos.values_list("codigo", flat=True))
        novos = [
            DocumentoChecklist(imovel=self, codigo=codigo, categoria=cat, descricao=desc, essencial=essencial)
            for codigo, cat, desc, essencial, _ in checklist.itens_para(self.proprietario.tipo)
            if codigo not in existentes
        ]
        DocumentoChecklist.objects.bulk_create(novos)
        for bloco, _ in VerificacaoBloco.Bloco.choices:
            VerificacaoBloco.objects.get_or_create(imovel=self, bloco=bloco)

    def perfil_compatibilidade(self) -> regras.PerfilImovel:
        return regras.PerfilImovel(
            preco=self.preco_referencia_anuncio,
            area_ha=self.area_total_ha,
            aptidoes=set(lista_codigos(self.aptidoes)),
            municipio=self.municipio,
            uf=self.uf,
            regiao=self.regiao,
            irrigacao=self.irrigacao,
            mecanizavel_pct=self.mecanizavel_pct,
            decisao=self.decisao_documental().codigo,
        )


class VerificacaoBloco(models.Model):
    """Fonte de cada bloco de dados: declarado, observado, documentado ou validado (Anexo I, 'Qualidade')."""

    class Bloco(models.TextChoices):
        CADASTRO = "cadastro", "Cadastro e localização"
        SOLO = "solo", "Solo e relevo"
        AGUA = "agua", "Água"
        AMBIENTE = "ambiente", "Ambiente"
        CULTURAS = "culturas", "Culturas"
        PECUARIA = "pecuaria", "Pecuária"
        BENFEITORIAS = "benfeitorias", "Benfeitorias"
        DOCUMENTOS = "documentos", "Documentos"

    class Fonte(models.TextChoices):
        NAO_INFORMADO = "nao_informado", "Não informado"
        DECLARADO = "declarado", "Informado pelo proprietário"
        OBSERVADO = "observado", "Observado em visita"
        DOCUMENTADO = "documentado", "Documentado"
        VALIDADO = "validado", "Validado por especialista"

    imovel = models.ForeignKey(Imovel, on_delete=models.CASCADE, related_name="verificacoes")
    bloco = models.CharField(max_length=15, choices=Bloco.choices)
    fonte = models.CharField(max_length=15, choices=Fonte.choices, default=Fonte.NAO_INFORMADO)
    observacao = models.CharField("Observação", max_length=200, blank=True)

    class Meta:
        unique_together = ("imovel", "bloco")
        ordering = ["id"]


def caminho_documento(instance, filename):
    return f"imoveis/{instance.imovel_id}/documentos/{filename}"


def caminho_foto(instance, filename):
    return f"imoveis/{instance.imovel_id}/fotos/{filename}"


class DocumentoChecklist(models.Model):
    class Status(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        RECEBIDO = "recebido", "Recebido — aguarda verificação"
        EXIGE_VALIDACAO = "exige_validacao", "Exige validação"
        VALIDADO = "validado", "Validado"
        VENCIDO = "vencido", "Vencido"
        NAO_APLICAVEL = "nao_aplicavel", "Não aplicável"

    class Risco(models.TextChoices):
        NENHUM = "nenhum", "Sem apontamento"
        CONDICIONANTE = "condicionante", "Condicionante"
        IMPEDITIVO = "impeditivo", "Impeditivo"

    imovel = models.ForeignKey(Imovel, on_delete=models.CASCADE, related_name="documentos")
    codigo = models.CharField(max_length=30)
    categoria = models.CharField(max_length=20, choices=checklist.CATEGORIAS)
    descricao = models.CharField(max_length=250)
    essencial = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDENTE)
    risco = models.CharField(max_length=15, choices=Risco.choices, default=Risco.NENHUM)
    emissao = models.DateField("Emissão", null=True, blank=True)
    validade = models.DateField(null=True, blank=True)
    responsavel = models.CharField("Responsável", max_length=120, blank=True)
    prazo = models.DateField("Prazo para regularizar", null=True, blank=True)
    observacoes = models.CharField("Observações", max_length=250, blank=True)
    arquivo = models.FileField(upload_to=caminho_documento, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        unique_together = ("imovel", "codigo")

    @property
    def vencido(self) -> bool:
        return self.status == self.Status.VENCIDO or bool(self.validade and self.validade < timezone.localdate())

    @property
    def semaforo(self) -> str:
        """Semáforo da Estratégia V2 (seção 10): impeditivo, condicionante, pendente e validado."""
        if self.risco == self.Risco.IMPEDITIVO:
            return "impeditivo"
        if self.risco == self.Risco.CONDICIONANTE:
            return "condicionante"
        if self.status in regras.STATUS_OK and not self.vencido:
            return "validado"
        return "pendente"


class FotoImovel(models.Model):
    imovel = models.ForeignKey(Imovel, on_delete=models.CASCADE, related_name="fotos")
    arquivo = models.FileField(
        upload_to=caminho_foto, validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])]
    )
    bloco = models.CharField(max_length=15, choices=VerificacaoBloco.Bloco.choices, default=VerificacaoBloco.Bloco.CADASTRO)
    descricao = models.CharField("Descrição", max_length=150)
    data_foto = models.DateField("Data da foto", default=timezone.localdate)
    autor = models.CharField(max_length=120, blank=True)
    autorizada = models.BooleanField("Uso autorizado pelo proprietário", default=False)
    publica = models.BooleanField("Pode aparecer no teaser público", default=False)
    enviada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["bloco", "id"]


class ContratoRepresentacao(models.Model):
    """Autorização de venda: representação exclusiva ou autorização compartilhada (Anexo IV)."""

    class Tipo(models.TextChoices):
        EXCLUSIVA = "exclusiva", "Representação exclusiva"
        COMPARTILHADA = "compartilhada", "Autorização sem exclusividade (carteira compartilhada)"

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", "Rascunho"
        VIGENTE = "vigente", "Vigente"
        ENCERRADO = "encerrado", "Encerrado"
        RESCINDIDO = "rescindido", "Rescindido"

    imovel = models.ForeignKey(Imovel, on_delete=models.CASCADE, related_name="contratos")
    tipo = models.CharField(max_length=15, choices=Tipo.choices, default=Tipo.EXCLUSIVA)
    data_inicio = models.DateField("Data de início", default=timezone.localdate)
    prazo_dias = models.PositiveIntegerField("Prazo (dias)", default=180)
    data_fim = models.DateField(blank=True)
    renovacao_automatica = models.BooleanField("Renovável por igual período", default=False)
    comissao_pct = models.DecimalField("Comissão (%)", max_digits=5, decimal_places=2, default=5)
    preco_autorizado = models.DecimalField("Preço autorizado (R$)", max_digits=14, decimal_places=2)
    assinado = models.BooleanField(default=False)
    data_assinatura = models.DateField("Data da assinatura", null=True, blank=True)
    arquivo = models.FileField("Contrato assinado (PDF)", upload_to=caminho_documento, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RASCUNHO)
    excecoes = models.TextField(
        "Exceções e compradores já conhecidos", blank=True,
        help_text="Regras para venda direta, comprador já conhecido e negócio após o término",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_inicio"]

    def save(self, *args, **kwargs):
        self.data_fim = self.data_inicio + timedelta(days=self.prazo_dias)
        super().save(*args, **kwargs)

    @property
    def dias_restantes(self) -> int:
        return (self.data_fim - timezone.localdate()).days

    @property
    def vencendo(self) -> bool:
        return self.status == self.Status.VIGENTE and 0 <= self.dias_restantes <= 30
