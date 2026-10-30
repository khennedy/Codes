"""Fluxo ponta a ponta: captação → validação → catálogo → registro de comprador → data room → venda → comissão."""
import shutil
import tempfile
from decimal import Decimal

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from contas.models import Corretor, Usuario
from core.models import LogAuditoria
from imoveis import checklist
from imoveis.models import ContratoRepresentacao, FotoImovel, Imovel, Proprietario
from negocios.models import ApuracaoComissao, Comprador, Conflito, Negociacao

MEDIA_TEMP = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_TEMP)
class FluxoRedeTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEMP, ignore_errors=True)

    def criar_corretor(self, login, nivel="pleno"):
        u = Usuario.objects.create_user(login, password="senha-forte-123", first_name=login.title())
        return Corretor.objects.create(usuario=u, creci=f"{login}-F", creci_verificado=True, status="ativo", nivel=nivel)

    def setUp(self):
        self.central = Usuario.objects.create_user("central", password="senha-forte-123", papel="central")
        self.captador = self.criar_corretor("ana", "partner")
        self.vendedor = self.criar_corretor("diego", "partner")
        self.proprietario = Proprietario.objects.create(
            nome="Proprietário Teste", telefone="(35) 91234-0000", captado_por=self.captador, consentimento_lgpd=True
        )

    def login(self, usuario):
        self.client.force_login(usuario if isinstance(usuario, Usuario) else usuario.usuario)

    def cadastrar_imovel(self):
        self.login(self.captador)
        resposta = self.client.post(reverse("imoveis:novo"), {
            "titulo": "Fazenda Teste", "proprietario": self.proprietario.pk, "origem_entrada": "corretor",
            "aptidao_principal": "cafe", "aptidoes": ["irrigada"], "municipio": "Três Pontas", "uf": "MG",
            "matricula": "MAT-999", "area_registral_ha": "200", "preco_pretendido": "5000000", "comissao_pct": "5",
            "outorga": "nao_informado",
        })
        self.assertEqual(resposta.status_code, 302)
        return Imovel.objects.get(titulo="Fazenda Teste")

    def validar_documentos(self, imovel):
        imovel.documentos.filter(essencial=True).update(status="validado")
        ContratoRepresentacao.objects.create(
            imovel=imovel, preco_autorizado=Decimal("5000000"), assinado=True, data_assinatura=timezone.localdate(),
            status="vigente",
        )
        foto = FotoImovel(imovel=imovel, descricao="Sede", autorizada=True)
        foto.arquivo.save("sede.png", ContentFile(b"\x89PNG"), save=True)

    def publicar(self, imovel, **extra):
        self.login(self.central)
        dados = {"valor_mercado": "4900000", "preco_autorizado": "5000000", "status": "aprovado",
                 "publicado": "on", "nivel_anuncio": "essencial", "data_avaliacao": "2026-10-01"}
        dados.update(extra)
        return self.client.post(reverse("imoveis:avaliar", args=[imovel.pk]), dados)

    def test_fluxo_completo(self):
        imovel = self.cadastrar_imovel()
        self.assertEqual(imovel.captador, self.captador)
        self.assertTrue(imovel.codigo.startswith("TP-"))
        self.assertEqual(imovel.documentos.count(), len(checklist.itens_para("pf")))
        self.assertFalse(imovel.documentos.filter(categoria="pessoa_juridica").exists())

        # Sem documentos nem autorização, a central não consegue publicar
        resposta = self.publicar(imovel)
        self.assertEqual(resposta.status_code, 200)
        imovel.refresh_from_db()
        self.assertFalse(imovel.publicado)

        self.validar_documentos(imovel)
        self.assertEqual(imovel.decisao_documental().codigo, "apto")
        self.assertEqual(self.publicar(imovel).status_code, 302)
        imovel.refresh_from_db()
        self.assertTrue(imovel.publicado)
        self.assertEqual(imovel.faixa_preco().faixa, "A")
        self.assertIsNotNone(imovel.revisar_preco_em)

        # Outro corretor vê a ficha comercial, mas não o proprietário nem a matrícula
        self.login(self.vendedor)
        ficha = self.client.get(reverse("imoveis:catalogo_detalhe", args=[imovel.pk]))
        self.assertContains(ficha, "Fazenda Teste")
        self.assertNotContains(ficha, "Proprietário Teste")
        self.assertNotContains(ficha, "MAT-999")
        self.assertEqual(self.client.get(reverse("imoveis:detalhe", args=[imovel.pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse("imoveis:dossie", args=[imovel.pk])).status_code, 403)

        # Registra comprador e a oportunidade
        self.client.post(reverse("negocios:comprador_novo"), {
            "nome": "Investidor X", "tipo": "investidor", "telefone": "(11) 95555-0000", "uf": "SP",
            "origem": "carteira", "etapa_cadastro": 1, "consentimento_lgpd": "on",
        })
        comprador = Comprador.objects.get(nome="Investidor X")
        self.assertEqual(comprador.corretor, self.vendedor)
        self.assertTrue(comprador.protegido)
        self.client.post(reverse("negocios:negociacao_nova"), {
            "imovel": imovel.pk, "comprador": comprador.pk, "situacao": "B",
        })
        negociacao = Negociacao.objects.get(imovel=imovel, comprador=comprador)

        # Data room: pedido → liberação pela central → acesso registrado
        self.client.post(reverse("negocios:dossie_solicitar", args=[negociacao.pk]))
        self.login(self.central)
        self.client.post(reverse("negocios:dossie_liberar", args=[negociacao.pk]))
        self.login(self.vendedor)
        dossie = self.client.get(reverse("imoveis:dossie", args=[imovel.pk]))
        self.assertEqual(dossie.status_code, 200)
        self.assertContains(dossie, "MAT-999")
        self.assertTrue(LogAuditoria.objects.filter(acao="acesso_dossie", usuario=self.vendedor.usuario).exists())

        # O captador não vê o contato do comprador de outro corretor
        self.login(self.captador)
        pagina = self.client.get(reverse("negocios:negociacao", args=[negociacao.pk]))
        self.assertNotContains(pagina, "95555-0000")

        # Conclusão: imóvel sai do catálogo e a comissão é apurada (Partner/Partner)
        self.login(self.vendedor)
        self.client.post(reverse("negocios:negociacao_etapa", args=[negociacao.pk]), {
            "etapa": "concluido", "valor_fechamento": "5000000", "data_fechamento": "2026-10-20",
        })
        imovel.refresh_from_db()
        self.assertEqual(imovel.status, "vendido")
        self.assertFalse(imovel.publicado)
        apuracao = ApuracaoComissao.objects.get(negociacao=negociacao)
        valores = {p.papel: p.valor for p in apuracao.participacoes.all()}
        self.assertEqual(valores, {"captador": Decimal("50000.00"), "vendedor": Decimal("100000.00"),
                                   "central": Decimal("100000.00")})

    def test_corretor_altera_preco_de_imovel_publicado_e_volta_para_validacao(self):
        imovel = self.cadastrar_imovel()
        self.validar_documentos(imovel)
        self.publicar(imovel)
        self.login(self.captador)
        self.client.post(reverse("imoveis:editar", args=[imovel.pk]), {
            "titulo": "Fazenda Teste", "proprietario": self.proprietario.pk, "origem_entrada": "corretor",
            "aptidao_principal": "cafe", "municipio": "Três Pontas", "uf": "MG", "matricula": "MAT-999",
            "area_registral_ha": "200", "preco_pretendido": "7000000", "comissao_pct": "5", "outorga": "nao_informado",
        })
        imovel.refresh_from_db()
        self.assertFalse(imovel.publicado)
        self.assertEqual(imovel.status, "em_validacao")

    def test_duplicidade_de_comprador(self):
        primeiro = Comprador(corretor=self.captador, nome="Paulo", telefone="(35) 98888-1234", consentimento_lgpd=True)
        from negocios import servicos
        servicos.registrar_comprador(primeiro)
        self.login(self.vendedor)
        resposta = self.client.post(reverse("negocios:comprador_novo"), {
            "nome": "Paulo H.", "tipo": "pf", "telefone": "35988881234", "uf": "MG", "origem": "carteira",
            "etapa_cadastro": 1, "consentimento_lgpd": "on",
        }, follow=True)
        self.assertContains(resposta, "Possível duplicidade")
        segundo = Comprador.objects.get(nome="Paulo H.")
        self.assertEqual(segundo.duplicidade_de, primeiro)
        self.assertIsNone(segundo.protecao_ate)

    def test_atividade_efetiva_renova_protecao(self):
        imovel = self.cadastrar_imovel()
        comprador = Comprador.objects.create(corretor=self.vendedor, nome="C", telefone="1199999999",
                                             protecao_ate=timezone.localdate())
        negociacao = Negociacao.objects.create(imovel=imovel, comprador=comprador, corretor_vendedor=self.vendedor)
        self.login(self.vendedor)
        self.client.post(reverse("negocios:negociacao_atividade", args=[negociacao.pk]),
                         {"tipo": "nota", "descricao": "anotação"})
        comprador.refresh_from_db()
        self.assertEqual(comprador.protecao_ate, timezone.localdate())
        self.client.post(reverse("negocios:negociacao_atividade", args=[negociacao.pk]),
                         {"tipo": "proposta", "descricao": "proposta formal"})
        comprador.refresh_from_db()
        self.assertEqual(comprador.protecao_ate, timezone.localdate() + timezone.timedelta(days=30))

    def test_parte_interessada_nao_decide_conflito(self):
        conflito = Conflito.objects.create(tipo="rateio", reclamante=self.central, descricao="teste")
        self.login(self.central)
        pagina = self.client.get(reverse("negocios:conflito", args=[conflito.pk]))
        self.assertIsNone(pagina.context["form"])
        outro_central = Usuario.objects.create_user("central2", password="x-senha-123", papel="central")
        self.login(outro_central)
        self.assertIsNotNone(self.client.get(reverse("negocios:conflito", args=[conflito.pk])).context["form"])

    def test_rateio_manual_precisa_fechar_100(self):
        imovel = self.cadastrar_imovel()
        comprador = Comprador.objects.create(corretor=self.vendedor, nome="C")
        negociacao = Negociacao.objects.create(imovel=imovel, comprador=comprador, corretor_vendedor=self.vendedor,
                                               valor_fechamento=Decimal("1000000"))
        self.login(self.central)
        self.client.get(reverse("negocios:apuracao", args=[negociacao.pk]))
        apuracao = negociacao.apuracao
        partes = list(apuracao.participacoes.all())
        dados = {"status": "aprovada", "participacoes-TOTAL_FORMS": "3", "participacoes-INITIAL_FORMS": "3",
                 "participacoes-MIN_NUM_FORMS": "0", "participacoes-MAX_NUM_FORMS": "1000"}
        for i, p in enumerate(partes):
            dados.update({f"participacoes-{i}-id": p.pk, f"participacoes-{i}-papel": p.papel,
                          f"participacoes-{i}-corretor": p.corretor_id or "", f"participacoes-{i}-percentual": "30"})
        resposta = self.client.post(reverse("negocios:apuracao", args=[negociacao.pk]), dados, follow=True)
        self.assertContains(resposta, "precisa fechar em 100%")
        dados["participacoes-2-percentual"] = "40"
        self.client.post(reverse("negocios:apuracao", args=[negociacao.pk]), dados)
        apuracao.refresh_from_db()
        self.assertEqual(apuracao.status, "aprovada")
        self.assertEqual(apuracao.soma_participacoes, apuracao.comissao_total)


@override_settings(MEDIA_ROOT=MEDIA_TEMP)
class AcessoTests(TestCase):
    def setUp(self):
        u = Usuario.objects.create_user("ana", password="senha-forte-123")
        self.corretor = Corretor.objects.create(usuario=u, creci="1", creci_verificado=True, status="ativo")
        p = Proprietario.objects.create(nome="Dono Secreto", captado_por=self.corretor)
        self.imovel = Imovel.objects.create(
            titulo="Publicado", proprietario=p, captador=self.corretor, municipio="Lavras", aptidao_principal="lazer",
            preco_pretendido=1, preco_autorizado=1, status="aprovado", publicado=True, matricula="MAT-SECRETA",
        )
        Imovel.objects.create(titulo="Rascunho oculto", proprietario=p, captador=self.corretor, municipio="Lavras",
                              aptidao_principal="lazer", preco_pretendido=1)
        self.foto_privada = FotoImovel(imovel=self.imovel, descricao="interna", autorizada=True, publica=False)
        self.foto_privada.arquivo.save("x.png", ContentFile(b"\x89PNG"), save=True)

    def test_vitrine_mostra_so_publicados_sem_dados_sensiveis(self):
        pagina = self.client.get(reverse("core:vitrine"))
        self.assertContains(pagina, "Publicado")
        self.assertNotContains(pagina, "Rascunho oculto")
        detalhe = self.client.get(reverse("core:vitrine_detalhe", args=[self.imovel.codigo]))
        self.assertNotContains(detalhe, "Dono Secreto")
        self.assertNotContains(detalhe, "MAT-SECRETA")

    def test_lead_da_vitrine(self):
        self.client.post(reverse("core:vitrine_detalhe", args=[self.imovel.codigo]), {
            "nome": "Interessado", "telefone": "11 90000-0000", "consentimento": "on",
        })
        from core.models import LeadPublico
        self.assertTrue(LeadPublico.objects.filter(nome="Interessado", imovel=self.imovel).exists())

    def test_foto_nao_publica_exige_login(self):
        self.assertEqual(self.client.get(reverse("core:arquivo_foto", args=[self.foto_privada.pk])).status_code, 403)

    def test_corretor_nao_acessa_area_da_central(self):
        self.client.force_login(self.corretor.usuario)
        self.assertEqual(self.client.get(reverse("core:configuracoes")).status_code, 403)
        self.assertEqual(self.client.get(reverse("imoveis:avaliar", args=[self.imovel.pk])).status_code, 403)

    def test_corretor_inscrito_aguarda_aprovacao(self):
        u = Usuario.objects.create_user("novo", password="senha-forte-123")
        Corretor.objects.create(usuario=u, creci="2")
        self.client.force_login(u)
        self.assertRedirects(self.client.get(reverse("imoveis:catalogo")), reverse("contas:aguardando"))

    def test_inscricao_publica(self):
        resposta = self.client.post(reverse("contas:inscricao"), {
            "username": "novo_corretor", "password1": "Campo#Forte2026", "password2": "Campo#Forte2026",
            "first_name": "Novo", "last_name": "Corretor", "email": "novo@exemplo.com", "telefone": "35 9",
            "cpf": "000", "municipio": "Lavras", "uf": "MG", "creci": "999", "creci_uf": "MG",
            "aceite_etica_lgpd": "on",
        })
        self.assertRedirects(resposta, reverse("contas:aguardando"))
        corretor = Corretor.objects.get(creci="999")
        self.assertEqual(corretor.status, "inscrito")
        self.assertFalse(corretor.pode_operar)


class LeadTests(TestCase):
    def test_central_distribui_lead_de_comprador_e_abre_negociacao(self):
        from core.models import LeadPublico

        central = Usuario.objects.create_user("central", password="senha-forte-123", papel="central")
        captador = Corretor.objects.create(usuario=Usuario.objects.create_user("ana"), creci="1",
                                           creci_verificado=True, status="ativo")
        vendedor = Corretor.objects.create(usuario=Usuario.objects.create_user("bia"), creci="2",
                                           creci_verificado=True, status="ativo")
        p = Proprietario.objects.create(nome="Dono", captado_por=captador)
        imovel = Imovel.objects.create(titulo="Chácara", proprietario=p, captador=captador, municipio="Lavras",
                                       aptidao_principal="lazer", preco_pretendido=1, status="aprovado", publicado=True)
        lead = LeadPublico.objects.create(tipo="comprador", nome="Lead", telefone="11 97777-0000", imovel=imovel,
                                          consentimento=True)
        self.client.force_login(central)
        pagina = self.client.get(reverse("core:lead_atribuir", args=[lead.pk]))
        self.assertContains(pagina, 'name="corretor"')
        self.client.post(reverse("core:lead_atribuir", args=[lead.pk]), {"corretor": vendedor.pk})
        lead.refresh_from_db()
        self.assertEqual(lead.status, "atribuido")
        comprador = Comprador.objects.get(nome="Lead")
        self.assertEqual((comprador.corretor, comprador.origem), (vendedor, "rede"))
        negociacao = Negociacao.objects.get(imovel=imovel, comprador=comprador)
        self.assertEqual((negociacao.corretor_vendedor, negociacao.situacao), (vendedor, "B"))
