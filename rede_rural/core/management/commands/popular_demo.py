"""Popula o banco com dados FICTÍCIOS para demonstração do piloto (Sul de Minas / Campo das Vertentes).

Uso: python manage.py popular_demo [--forcar]
Todos os usuários de demonstração usam a senha "demo1234". Não use em produção.
"""
import importlib
import struct
import zlib
from datetime import timedelta
from decimal import Decimal

from django.apps import apps
from django.core.files.base import ContentFile
from django.core.management import BaseCommand, CommandError, call_command
from django.db import transaction
from django.utils import timezone

from contas.models import Corretor, Mensalidade, ProgressoTrilha, Trilha, Usuario
from core.auditoria import registrar
from core.models import LeadPublico, ParametroNivel
from imoveis.models import ContratoRepresentacao, FotoImovel, Imovel, Proprietario, VerificacaoBloco
from negocios import servicos
from negocios.models import Comprador, Conflito, Demanda, EncaminhamentoCredito, Negociacao, Visita

SENHA = "demo1234"


def png_paisagem(largura, altura, ceu, faixas):
    """Gera um PNG simples (céu + faixas de talhões) sem dependências externas."""
    linhas = []
    limite_ceu = altura * 2 // 5
    altura_faixa = max(1, (altura - limite_ceu) // len(faixas))
    for y in range(altura):
        if y < limite_ceu:
            f = y / limite_ceu
            cor = tuple(int(ceu[0][i] * (1 - f) + ceu[1][i] * f) for i in range(3))
            linha = bytes(cor) * largura
        else:
            indice = min((y - limite_ceu) // altura_faixa, len(faixas) - 1)
            base = faixas[indice]
            linha = bytearray()
            for x in range(largura):
                listra = 10 if ((x + y * 2) // 9) % 2 else 0
                linha += bytes(max(0, min(255, c - listra)) for c in base)
            linha = bytes(linha)
        linhas.append(b"\x00" + linha)

    def bloco(tipo, dados):
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)

    cabecalho = struct.pack(">IIBBBBB", largura, altura, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", cabecalho) + bloco(b"IDAT", zlib.compress(b"".join(linhas), 9)) + bloco(b"IEND", b"")


CEU = ((126, 170, 206), (214, 228, 236))
PALETAS = {
    "cafe": [(58, 102, 52), (78, 120, 60), (92, 134, 70), (120, 98, 66)],
    "pecuaria": [(118, 156, 74), (136, 170, 84), (104, 142, 66), (150, 130, 90)],
    "graos": [(196, 176, 92), (176, 160, 80), (120, 150, 70), (208, 190, 110)],
    "lazer": [(80, 140, 90), (70, 120, 150), (96, 150, 96), (110, 140, 90)],
    "benfeitoria": [(150, 120, 96), (170, 150, 120), (110, 130, 80), (130, 110, 90)],
}


class Command(BaseCommand):
    help = "Popula o banco com dados fictícios de demonstração."

    def add_arguments(self, parser):
        parser.add_argument("--forcar", action="store_true", help="Apaga todos os dados antes de popular.")

    def handle(self, *args, **opcoes):
        if Usuario.objects.exists():
            if not opcoes["forcar"]:
                raise CommandError("O banco já tem dados. Use --forcar para apagar tudo e recriar a demonstração.")
            call_command("flush", interactive=False, verbosity=0)
            importlib.import_module("core.migrations.0002_dados_iniciais").criar(apps, None)
        with transaction.atomic():
            self.popular()
        self.stdout.write(self.style.SUCCESS("Demonstração criada. Usuários: central, ana, bruno, carla, diego, eduardo — senha: demo1234"))

    # ------------------------------------------------------------------
    def usuario(self, login, nome, sobrenome, **extra):
        u = Usuario(username=login, first_name=nome, last_name=sobrenome, email=f"{login}@exemplo.com.br", **extra)
        u.set_password(SENHA)
        u.save()
        return u

    def corretor(self, login, nome, sobrenome, creci, nivel, municipio, regiao, especialidades, status="ativo"):
        u = self.usuario(login, nome, sobrenome, telefone="(35) 90000-0000")
        return Corretor.objects.create(
            usuario=u, creci=creci, creci_uf="MG", creci_verificado=status == "ativo", municipio=municipio,
            regiao_atuacao=regiao, especialidades=especialidades, nivel=nivel, status=status,
            aceite_etica_lgpd=True, aceite_em=timezone.now(), treinamento_inicial=status == "ativo",
            nota_prova_pratica=Decimal("8.5") if status == "ativo" else None,
            data_adesao=self.hoje - timedelta(days=200) if status == "ativo" else None,
        )

    def foto(self, imovel, bloco, descricao, paleta, publica=True):
        f = FotoImovel(imovel=imovel, bloco=bloco, descricao=descricao, autor=imovel.captador.nome, autorizada=True,
                       publica=publica, data_foto=self.hoje - timedelta(days=20), enviada_por=imovel.captador.usuario)
        f.arquivo.save(f"{bloco}-{imovel.pk}.png", ContentFile(png_paisagem(480, 300, CEU, PALETAS[paleta])), save=False)
        f.save()

    def documentos(self, imovel, validados=(), status_padrao="validado", ajustes=None, essenciais="validado"):
        """Marca o checklist: itens essenciais validados e demais com status padrão, salvo ajustes."""
        ajustes = ajustes or {}
        for d in imovel.documentos.all():
            if d.codigo in ajustes:
                for campo, valor in ajustes[d.codigo].items():
                    setattr(d, campo, valor)
            elif d.essencial or d.codigo in validados:
                d.status = essenciais if d.essencial else "validado"
                d.responsavel = "Central — equipe documental"
            else:
                d.status = status_padrao
            d.save()

    def fontes(self, imovel, fonte):
        imovel.verificacoes.update(fonte=fonte)

    def contrato(self, imovel, dias_atras=30, tipo="exclusiva"):
        return ContratoRepresentacao.objects.create(
            imovel=imovel, tipo=tipo, data_inicio=self.hoje - timedelta(days=dias_atras), prazo_dias=180,
            renovacao_automatica=True, comissao_pct=Decimal("5"), preco_autorizado=imovel.preco_autorizado or imovel.preco_pretendido,
            assinado=True, data_assinatura=self.hoje - timedelta(days=dias_atras), status="vigente",
            excecoes="Compradores já conhecidos pelo proprietário antes da assinatura: nenhum declarado.",
        )

    def aprovar(self, imovel, status="aprovado", publicado=True, dias_validacao=3):
        imovel.status = status
        imovel.publicado = publicado
        imovel.enviado_validacao_em = timezone.now() - timedelta(days=20)
        imovel.validado_em = imovel.enviado_validacao_em + timedelta(days=dias_validacao)
        imovel.validado_por = self.central
        imovel.data_avaliacao = self.hoje - timedelta(days=25)
        imovel.revisar_preco_em = imovel.data_avaliacao + timedelta(days=180)
        imovel.save()

    # ------------------------------------------------------------------
    def popular(self):
        self.hoje = timezone.localdate()
        self.central = self.usuario("central", "Equipe", "Central", papel="central", is_staff=True, is_superuser=True)

        ana = self.corretor("ana", "Ana", "Ribeiro", "41.201-F", "partner", "Três Pontas", "Sul de Minas", "café, irrigação")
        bruno = self.corretor("bruno", "Bruno", "Carvalho", "38.774-F", "master", "Lavras", "Campo das Vertentes", "pecuária de leite, chácaras")
        carla = self.corretor("carla", "Carla", "Mendes", "45.090-F", "senior", "São João del-Rei", "Campo das Vertentes", "grãos, pecuária")
        diego = self.corretor("diego", "Diego", "Souza", "52.318-F", "pleno", "Varginha", "Sul de Minas", "café, investidores")
        self.corretor("eduardo", "Eduardo", "Lima", "55.002-F", "pleno", "Alfenas", "Sul de Minas", "silvicultura", status="inscrito")

        # ---------------- Imóvel 1: café irrigado, apto, faixa A, publicado
        p1 = Proprietario.objects.create(
            tipo="pj", nome="Agropecuária Serra Verde Ltda (fictícia)", representante="Sócio-administrador",
            telefone="(35) 90000-1001", municipio="Três Pontas", consentimento_lgpd=True, captado_por=ana,
        )
        i1 = Imovel.objects.create(
            titulo="Fazenda Serra Verde — café irrigado", proprietario=p1, captador=ana, municipio="Três Pontas",
            regiao="Sul de Minas", acesso="12 km da cidade, 9 km de asfalto", latitude=Decimal("-21.366000"),
            longitude=Decimal("-45.512000"), matricula="12.345 e 12.346", cartorio="CRI de Três Pontas",
            area_registral_ha=Decimal("242"), area_medida_ha=Decimal("240.5"), area_util_ha=Decimal("180"),
            area_app_rl_ha=Decimal("52"), car="MG-3169406-XXXX", ccir="950.123.456.789-0", nirf="1.234.567-8",
            sigef_certificado=True, aptidao_principal="cafe", aptidoes="cafe,irrigada", altitude_m=920,
            declividade="suave_ondulado", textura_solo="Latossolo vermelho-amarelo, argiloso", mecanizavel_pct=Decimal("85"),
            data_analise_solo=self.hoje - timedelta(days=150), nascentes=3, cursos_dagua="Córrego da Serra", acudes=2,
            pocos=1, irrigacao=True, area_irrigada_ha=Decimal("110"), outorga="possui",
            culturas="T1 — Catuaí 144, 60 ha, 8 anos, 42 e 36 sc/ha\nT2 — Mundo Novo, 50 ha, 12 anos, 38 e 33 sc/ha\nT3 — Arara, 40 ha, 4 anos, 30 e 45 sc/ha",
            cafe_pes=650000, cafe_variedades="Catuaí 144, Mundo Novo, Arara", cafe_area_ha=Decimal("150"),
            produtividade_media="38 sc/ha (média dos 2 últimos ciclos)", casas=4, barracoes_m2=1200, cercas_km=Decimal("14"),
            energia="Trifásica", benfeitorias="Terreiro de 3.000 m², 2 secadores, tulhas, oficina, gotejamento em 110 ha",
            bens_incluidos="Trator e pulverizador, conforme inventário anexo ao contrato",
            preco_pretendido=Decimal("16500000"), valor_mercado=Decimal("16000000"),
            metodologia_avaliacao="Comparativo direto com 7 dados de mercado, homogeneizados", avaliador="Ana Ribeiro (PTAM)",
            preco_autorizado=Decimal("16500000"), condicoes_pagamento="40% de entrada, saldo em 3 safras",
            comissao_pct=Decimal("5"), nivel_anuncio="investidor",
            descricao_comercial="Propriedade cafeeira com irrigação por gotejamento, alta mecanização e infraestrutura de pós-colheita completa.",
            destaques_publicos="Café irrigado em altitude;Alta mecanização;Pós-colheita completa",
        )
        i1.criar_checklist()
        self.documentos(i1, validados=("georref", "outorgas", "analise_solo", "historico_produtivo"))
        self.fontes(i1, VerificacaoBloco.Fonte.DOCUMENTADO)
        i1.verificacoes.filter(bloco__in=["cadastro", "documentos"]).update(fonte="validado")
        self.contrato(i1, dias_atras=40)
        self.foto(i1, "cadastro", "Vista geral da sede e lavouras", "cafe")
        self.foto(i1, "culturas", "Talhão T1 — Catuaí 144", "cafe")
        self.foto(i1, "benfeitorias", "Terreiro e secadores", "benfeitoria")
        self.aprovar(i1)

        # ---------------- Imóvel 2: pecuária de leite, apto com ressalvas, faixa B
        p2 = Proprietario.objects.create(
            tipo="pf", nome="José Carlos Pereira (fictício)", estado_civil="Casado", regime_bens="comunhão parcial",
            conjuge="Marta Pereira (fictícia)", telefone="(35) 90000-2002", municipio="Lavras", consentimento_lgpd=True,
            captado_por=bruno,
        )
        i2 = Imovel.objects.create(
            titulo="Sítio Boa Vista — pecuária de leite", proprietario=p2, captador=bruno, municipio="Lavras",
            regiao="Campo das Vertentes", acesso="6 km de estrada de terra cascalhada", matricula="8.901",
            cartorio="CRI de Lavras", area_registral_ha=Decimal("96.8"), area_util_ha=Decimal("70"),
            car="MG-3138203-YYYY", ccir="950.222.333.444-1", aptidao_principal="pecuaria_leite", aptidoes="pecuaria_leite",
            altitude_m=880, declividade="ondulado", mecanizavel_pct=Decimal("40"), nascentes=2,
            cursos_dagua="Ribeirão Boa Vista", acudes=1, outorga="em_processo",
            rebanho="Bovinos leiteiros: 85 matrizes Girolando", lotacao_ua_ha=Decimal("1.8"),
            pastagem="Brachiaria e Tifton 85, bom estado", casas=2, barracoes_m2=450, cercas_km=Decimal("9.5"),
            energia="Trifásica", benfeitorias="Curral, ordenha mecânica 6 conjuntos, tanque de expansão 3.000 L, silo trincheira",
            preco_pretendido=Decimal("3400000"), valor_mercado=Decimal("3150000"),
            metodologia_avaliacao="Comparativo direto (5 dados) + benfeitorias pelo custo de reprodução depreciado",
            avaliador="Bruno Carvalho (PTAM)", preco_autorizado=Decimal("3380000"),
            condicoes_pagamento="À vista ou 50% + 12 meses", comissao_pct=Decimal("5"),
            descricao_comercial="Sítio leiteiro estruturado, com ordenha mecânica e pastagens formadas.",
            destaques_publicos="Ordenha mecânica;Pastagens formadas;Água abundante",
        )
        i2.criar_checklist()
        self.documentos(i2, status_padrao="recebido", ajustes={
            "georref": {"status": "pendente", "risco": "condicionante", "responsavel": "Agrimensor contratado",
                        "prazo": self.hoje + timedelta(days=60), "observacoes": "Certificação SIGEF em andamento"},
        })
        self.fontes(i2, VerificacaoBloco.Fonte.OBSERVADO)
        self.contrato(i2, dias_atras=165)  # vence em ~15 dias
        self.foto(i2, "pecuaria", "Pastagens e curral", "pecuaria")
        self.foto(i2, "benfeitorias", "Sala de ordenha", "benfeitoria")
        i2.parecer_central = "Aprovado com ressalvas: georreferenciamento/SIGEF pendente, com prazo definido. Não anunciar como certificado."
        self.aprovar(i2, status="aprovado_ressalvas", dias_validacao=5)

        # ---------------- Imóvel 3: grãos com pivô, em validação, faixa D
        p3 = Proprietario.objects.create(
            tipo="pf", nome="Maria Helena Andrade (fictícia)", estado_civil="Viúva", telefone="(32) 90000-3003",
            municipio="São João del-Rei", consentimento_lgpd=True, captado_por=carla,
        )
        i3 = Imovel.objects.create(
            titulo="Fazenda Ribeirão Fundo — grãos irrigados", proprietario=p3, captador=carla,
            municipio="São João del-Rei", regiao="Campo das Vertentes", acesso="Às margens da rodovia",
            matricula="20.110", cartorio="CRI de São João del-Rei", area_registral_ha=Decimal("410"),
            area_util_ha=Decimal("330"), aptidao_principal="graos", aptidoes="graos,irrigada", altitude_m=950,
            declividade="plano", mecanizavel_pct=Decimal("95"), irrigacao=True, area_irrigada_ha=Decimal("120"),
            outorga="possui", culturas="Soja/milho safrinha em 330 ha; 2 pivôs centrais (120 ha)",
            produtividade_media="Soja 62 sc/ha; milho 140 sc/ha", casas=3, barracoes_m2=2000, energia="Trifásica",
            benfeitorias="2 pivôs, armazém 2.000 m², balança", preco_pretendido=Decimal("24000000"),
            valor_mercado=Decimal("19000000"), metodologia_avaliacao="Comparativo direto (4 dados) — poucos comparáveis",
            avaliador="Equipe técnica credenciada", comissao_pct=Decimal("5"),
        )
        i3.criar_checklist()
        self.documentos(i3, status_padrao="pendente", essenciais="recebido")
        self.contrato(i3, dias_atras=5)
        i3.status = "em_validacao"
        i3.data_avaliacao = self.hoje - timedelta(days=4)
        i3.enviado_validacao_em = timezone.now() - timedelta(days=2)
        i3.save()

        # ---------------- Imóvel 4: espólio, bloqueado
        p4 = Proprietario.objects.create(
            tipo="pf", nome="Espólio de Antônio Ferreira (fictício)", representante="Inventariante: Lúcia Ferreira",
            telefone="(35) 90000-4004", municipio="Nepomuceno", consentimento_lgpd=True, captado_por=ana,
        )
        i4 = Imovel.objects.create(
            titulo="Fazenda Santa Clara — café e eucalipto", proprietario=p4, captador=ana, municipio="Nepomuceno",
            regiao="Sul de Minas", area_registral_ha=Decimal("180"), aptidao_principal="cafe",
            aptidoes="cafe,silvicultura", preco_pretendido=Decimal("9000000"), comissao_pct=Decimal("5"),
            origem_entrada="institucional",
        )
        i4.criar_checklist()
        self.documentos(i4, status_padrao="pendente", ajustes={
            "pf_sucessao": {"status": "exige_validacao", "risco": "impeditivo",
                            "observacoes": "Inventário sem formal de partilha nem alvará judicial para alienação"},
        })
        self.contrato(i4, dias_atras=10)
        i4.status = "pendente_regularizacao"
        i4.parecer_central = "Bloqueado até apresentação de alvará judicial ou formal de partilha registrado."
        i4.save()

        # ---------------- Imóvel 5: rascunho
        p5 = Proprietario.objects.create(tipo="pj", nome="Agro Lima Participações S.A. (fictícia)", municipio="Boa Esperança",
                                         consentimento_lgpd=True, captado_por=diego)
        i5 = Imovel.objects.create(
            titulo="Fazenda Água Limpa — pecuária de corte", proprietario=p5, captador=diego, municipio="Boa Esperança",
            regiao="Sul de Minas", area_registral_ha=Decimal("520"), aptidao_principal="pecuaria_corte",
            preco_pretendido=Decimal("14000000"), comissao_pct=Decimal("5"),
        )
        i5.criar_checklist()

        # ---------------- Imóvel 6: chácara com preço público
        p6 = Proprietario.objects.create(tipo="pf", nome="Ricardo Nunes (fictício)", estado_civil="Solteiro",
                                         municipio="Carrancas", consentimento_lgpd=True, captado_por=bruno)
        i6 = Imovel.objects.create(
            titulo="Chácara Recanto do Lago", proprietario=p6, captador=bruno, municipio="Carrancas",
            regiao="Campo das Vertentes", area_registral_ha=Decimal("12.5"), aptidao_principal="lazer",
            aptidoes="lazer,fruticultura", car="MG-3114309-ZZZZ", ccir="950.555.666.777-2", matricula="3.210",
            cartorio="CRI de Lavras", nascentes=1, acudes=1, casas=1, energia="Monofásica",
            benfeitorias="Casa sede 180 m², pomar, lago com 0,6 ha", preco_pretendido=Decimal("1350000"),
            valor_mercado=Decimal("1300000"), preco_autorizado=Decimal("1350000"), metodologia_avaliacao="Comparativo direto",
            avaliador="Bruno Carvalho", exibir_preco_publico=True, comissao_pct=Decimal("6"),
            destaques_publicos="Lago próprio;Pomar formado;Perto das cachoeiras de Carrancas",
        )
        i6.criar_checklist()
        self.documentos(i6)
        self.fontes(i6, VerificacaoBloco.Fonte.DOCUMENTADO)
        self.contrato(i6, dias_atras=20)
        self.foto(i6, "cadastro", "Lago e casa sede", "lazer")
        self.aprovar(i6)

        # ---------------- Imóvel 7: vendido (negócio concluído)
        p7 = Proprietario.objects.create(tipo="pf", nome="Sebastião Rocha (fictício)", municipio="Ijaci",
                                         consentimento_lgpd=True, captado_por=bruno)
        i7 = Imovel.objects.create(
            titulo="Sítio Pedra Branca — leite e milho", proprietario=p7, captador=bruno, municipio="Ijaci",
            regiao="Campo das Vertentes", area_registral_ha=Decimal("88"), aptidao_principal="pecuaria_leite",
            aptidoes="pecuaria_leite,graos", preco_pretendido=Decimal("3300000"), valor_mercado=Decimal("3200000"),
            preco_autorizado=Decimal("3250000"), comissao_pct=Decimal("5"),
        )
        i7.criar_checklist()
        self.documentos(i7)
        self.contrato(i7, dias_atras=120)
        self.foto(i7, "cadastro", "Vista geral", "pecuaria", publica=False)
        self.aprovar(i7)

        # ---------------- Compradores, demandas e negociações
        def comprador(corretor, nome, telefone, **extra):
            c = Comprador(corretor=corretor, nome=nome, telefone=telefone, consentimento_lgpd=True,
                          evidencia_relacionamento="Cliente acompanhado desde 2025 (fictício).", **extra)
            servicos.registrar_comprador(c)
            return c

        investidor = comprador(diego, "Grupo Investidor Mantiqueira (fictício)", "(11) 90000-5005", tipo="investidor",
                               email="contato@mantiqueira.exemplo", origem="carteira", etapa_cadastro=3)
        Demanda.objects.create(comprador=investidor, descricao="Fazenda de café irrigada de R$ 10 a 20 milhões",
                               aptidoes="cafe,irrigada", regiao="Sul de Minas", uf="MG",
                               orcamento_min=Decimal("10000000"), orcamento_max=Decimal("20000000"),
                               area_min_ha=Decimal("150"), area_max_ha=Decimal("400"), exige_irrigacao=True,
                               horizonte="6m", pretende_financiar=True)
        roberto = comprador(carla, "Roberto Alves (fictício)", "(32) 90000-6006", etapa_cadastro=2)
        Demanda.objects.create(comprador=roberto, descricao="Área produtiva para leite até R$ 4 milhões",
                               aptidoes="pecuaria_leite", regiao="Campo das Vertentes", uf="MG",
                               orcamento_min=Decimal("2000000"), orcamento_max=Decimal("4000000"),
                               area_min_ha=Decimal("60"), area_max_ha=Decimal("200"), horizonte="12m")
        fernanda = comprador(carla, "Fernanda Costa (fictícia)", "(31) 90000-7007", etapa_cadastro=3)
        paulo = comprador(ana, "Paulo Henrique Rocha (fictício)", "(35) 98888-1234", email="paulo.rocha@exemplo.com")
        Demanda.objects.create(comprador=paulo, descricao="Café de montanha, até 300 ha", aptidoes="cafe",
                               uf="MG", orcamento_max=Decimal("18000000"), area_min_ha=Decimal("100"),
                               area_max_ha=Decimal("300"))
        paulo_dup = comprador(diego, "Paulo H. Rocha (fictício)", "35 98888-1234")

        n1 = Negociacao.objects.create(imovel=i1, comprador=investidor, corretor_vendedor=diego, situacao="B",
                                       etapa="proposta", valor_proposta=Decimal("15800000"),
                                       proxima_acao="Retorno do proprietário sobre contraproposta",
                                       proxima_acao_em=self.hoje + timedelta(days=3),
                                       dossie_solicitado_em=timezone.now() - timedelta(days=8),
                                       dossie_liberado_ate=timezone.now() + timedelta(days=7))
        servicos.registrar_atividade(n1, diego.usuario, "registro", "Comprador registrado para FAZ Serra Verde.")
        Visita.objects.create(negociacao=n1, data_hora=timezone.now() - timedelta(days=6), corretor=diego,
                              autorizacao_proprietario=True, realizada=True, objetivo="Conhecer lavouras e pós-colheita",
                              participantes="Diego, Ana (captadora), 2 representantes do grupo",
                              pontos_apresentados="Talhões irrigados, terreiro e secadores, outorga vigente",
                              perguntas_tecnicas="Idade dos talhões, custo por saca, regularidade da outorga",
                              condicoes_negociais="Interesse em 40% de entrada", pendencias="Enviar histórico de safras — Ana, 5 dias",
                              proxima_acao="Proposta formal")
        servicos.registrar_atividade(n1, diego.usuario, "visita", "Visita realizada com o grupo investidor.")
        servicos.registrar_atividade(n1, diego.usuario, "proposta", "Proposta de R$ 15,8 mi com 40% de entrada.")
        EncaminhamentoCredito.objects.create(comprador=investidor, negociacao=n1, produto="aquisicao",
                                             valor_estimado=Decimal("9000000"), consentimento=True,
                                             dados_compartilhados="nome, telefone, e-mail, município, produto de interesse e valor estimado",
                                             status="em_atendimento", retorno="Diagnóstico 360° agendado",
                                             solicitado_por=diego.usuario)

        n2 = Negociacao.objects.create(imovel=i2, comprador=roberto, corretor_vendedor=carla, situacao="B",
                                       etapa="visita_agendada", proxima_acao="Visita ao sítio",
                                       proxima_acao_em=self.hoje + timedelta(days=2),
                                       dossie_solicitado_em=timezone.now() - timedelta(hours=5))
        servicos.registrar_atividade(n2, carla.usuario, "registro", "Comprador registrado para o Sítio Boa Vista.")
        Visita.objects.create(negociacao=n2, data_hora=timezone.now() + timedelta(days=2), corretor=carla,
                              autorizacao_proprietario=True, objetivo="Apresentar estrutura de ordenha e pastagens")
        servicos.registrar_atividade(n2, carla.usuario, "visita_agendada", "Visita agendada com autorização do proprietário.")

        n3 = Negociacao.objects.create(imovel=i7, comprador=fernanda, corretor_vendedor=carla, situacao="B",
                                       etapa="concluido", valor_proposta=Decimal("3200000"),
                                       valor_fechamento=Decimal("3200000"), data_fechamento=self.hoje - timedelta(days=40))
        servicos.registrar_atividade(n3, carla.usuario, "registro", "Comprador registrado.")
        servicos.registrar_atividade(n3, self.central, "etapa", "Etapa: Contrato → Concluído")
        i7.status = "vendido"
        i7.publicado = False
        i7.save()
        apuracao = servicos.gerar_apuracao(n3)
        apuracao.status = "recebida"
        apuracao.save()

        n4 = Negociacao.objects.create(imovel=i1, comprador=paulo, corretor_vendedor=ana, situacao="C", etapa="qualificado")
        servicos.registrar_atividade(n4, ana.usuario, "registro", "Comprador da captadora registrado no próprio imóvel.")

        conflito = Conflito.objects.create(
            tipo="duplicidade", comprador=paulo_dup, reclamante=diego.usuario,
            descricao="Registrei o comprador Paulo H. Rocha, mas o sistema indicou registro anterior de outra corretora.",
            evidencias="Troca de mensagens com o comprador desde setembro (fictício).", status="evidencias",
        )
        conflito.envolvidos.add(ana, diego)

        # ---------------- Leads, mensalidades, trilhas e auditoria
        LeadPublico.objects.create(tipo="comprador", nome="Luiz Fernando (fictício)", telefone="(35) 90000-8008",
                                   municipio="Varginha", imovel=i6, consentimento=True,
                                   mensagem="Gostaria de visitar a chácara no fim de semana.")
        LeadPublico.objects.create(tipo="proprietario", nome="Cláudia Prado (fictícia)", telefone="(35) 90000-9009",
                                   municipio="Campo Belo", consentimento=True,
                                   mensagem="Tenho 150 ha com café e pasto e quero avaliar a venda.")

        params = ParametroNivel.como_regras()
        competencia = self.hoje.replace(day=1)
        for i, c in enumerate(Corretor.objects.filter(status="ativo")):
            for meses in (1, 0):
                comp = (competencia - timedelta(days=28 * meses)).replace(day=1)
                Mensalidade.objects.create(
                    corretor=c, competencia=comp, valor=params[c.nivel].mensalidade, vencimento=comp.replace(day=10),
                    status="paga" if meses or i % 2 == 0 else "pendente", paga_em=comp.replace(day=9) if meses or i % 2 == 0 else None,
                )
        for c in Corretor.objects.filter(status="ativo"):
            for t in Trilha.objects.filter(obrigatoria_ingresso=True):
                ProgressoTrilha.objects.create(corretor=c, trilha=t, status="concluido", concluido_em=self.hoje - timedelta(days=150),
                                               validado_por=self.central)
        ProgressoTrilha.objects.create(corretor=diego, trilha=Trilha.objects.get(nome="Cafeicultura"), status="aguardando",
                                       concluido_em=self.hoje - timedelta(days=1))

        for imovel in (i1, i2, i6, i7):
            registrar(self.central, "imovel_deliberado", imovel, f"{imovel.get_status_display()} (demonstração)")
        registrar(self.central, "dossie_liberado", n1, "15 dias (demonstração)")
