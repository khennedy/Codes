from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from core import regras
from core.regras import ItemDecisao


class RateioTests(SimpleTestCase):
    def rateio(self, valor, pct, nivel_capt, nivel_vend, **kw):
        return regras.calcular_rateio(
            Decimal(valor), Decimal(pct), captador_id=1, captador_nivel=nivel_capt, vendedor_id=2,
            vendedor_nivel=nivel_vend, **kw,
        )

    def test_exemplo_partner_da_estrategia(self):
        # Seção 19: R$ 5 mi, 5% = R$ 250 mil; Partner: 50 mil captação, 100 mil venda, 100 mil central
        r = self.rateio("5000000", "5", "partner", "partner")
        self.assertEqual(r.comissao_total, Decimal("250000.00"))
        self.assertEqual(r.valor_por_papel("captador"), Decimal("50000.00"))
        self.assertEqual(r.valor_por_papel("vendedor"), Decimal("100000.00"))
        self.assertEqual(r.valor_por_papel("central"), Decimal("100000.00"))

    def test_exemplo_pleno_da_estrategia(self):
        r = self.rateio("5000000", "5", "pleno", "pleno")
        self.assertEqual(r.valor_por_papel("captador"), Decimal("30000.00"))
        self.assertEqual(r.valor_por_papel("vendedor"), Decimal("50000.00"))
        self.assertEqual(r.valor_por_papel("central"), Decimal("170000.00"))

    def test_exemplo_do_regulamento_45_45_10(self):
        # Regulamento de Proteção, seção 7: fazenda de R$ 8 mi, 5% = 400 mil → 180/180/40
        r = self.rateio("8000000", "5", "pleno", "pleno", modelo=regras.MODELO_REGULAMENTO)
        self.assertEqual(r.valor_por_papel("captador"), Decimal("180000.00"))
        self.assertEqual(r.valor_por_papel("vendedor"), Decimal("180000.00"))
        self.assertEqual(r.valor_por_papel("central"), Decimal("40000.00"))
        self.assertEqual([p.percentual for p in r.parcelas], [Decimal("45.00"), Decimal("45.00"), Decimal("10.00")])

    def test_situacao_a_nao_gera_participacao_automatica_da_central(self):
        r = regras.calcular_rateio(
            Decimal("2000000"), Decimal("5"), captador_id=1, captador_nivel="senior", vendedor_id=1,
            vendedor_nivel="senior", situacao=regras.SITUACAO_A,
        )
        self.assertEqual(r.valor_por_papel("central"), Decimal("0"))
        self.assertEqual(r.valor_por_papel("captador") + r.valor_por_papel("vendedor"), r.comissao_total)
        self.assertTrue(r.alertas)

    def test_comissao_menor_que_soma_de_niveis_reduz_proporcionalmente(self):
        r = self.rateio("1000000", "2", "partner", "partner")  # 1% + 2% > 2%
        self.assertEqual(sum(p.valor for p in r.parcelas), r.comissao_total)
        self.assertEqual(r.valor_por_papel("central"), Decimal("0"))
        self.assertTrue(any("proporcionalmente" in a for a in r.alertas))

    def test_soma_sempre_fecha_com_o_total(self):
        r = self.rateio("1234567.89", "5.5", "master", "senior")
        self.assertEqual(sum(p.valor for p in r.parcelas), r.comissao_total)


class FaixaPrecoTests(SimpleTestCase):
    def test_faixas_do_regulamento_de_avaliacao(self):
        casos = {"104": "A", "105": "A", "107": "B", "112": "C", "120": "D", "85": "ABAIXO", "95": "A"}
        for preco, faixa in casos.items():
            with self.subTest(preco=preco):
                self.assertEqual(regras.classificar_preco(Decimal(preco), Decimal("100")).faixa, faixa)

    def test_sem_avaliacao_nao_aplica_faixa(self):
        self.assertEqual(regras.classificar_preco(Decimal("100"), None).faixa, "SEM_REFERENCIA")


class NivelTests(SimpleTestCase):
    def test_tabela_de_volume(self):
        self.assertEqual(regras.nivel_sugerido(0), "pleno")
        self.assertEqual(regras.nivel_sugerido(Decimal("20000000")), "pleno")
        self.assertEqual(regras.nivel_sugerido(Decimal("25000000")), "senior")
        self.assertEqual(regras.nivel_sugerido(Decimal("45000000")), "master")
        self.assertEqual(regras.nivel_sugerido(Decimal("61000000")), "partner")


class DecisaoDocumentalTests(SimpleTestCase):
    def itens(self, **sobrescritos):
        base = {
            "id_titulares": ItemDecisao("id_titulares", "Titulares", True, "validado"),
            "matricula_onus": ItemDecisao("matricula_onus", "Matrícula", True, "validado"),
            "pf_documentos": ItemDecisao("pf_documentos", "Documentos PF", True, "validado"),
            "car": ItemDecisao("car", "CAR", True, "validado"),
            "georref": ItemDecisao("georref", "Georref", False, "pendente"),
        }
        base.update(sobrescritos)
        return list(base.values())

    def test_apto(self):
        self.assertEqual(regras.decidir_publicacao(self.itens(), True).codigo, regras.DECISAO_APTO)

    def test_sem_autorizacao_fica_pendente(self):
        self.assertEqual(regras.decidir_publicacao(self.itens(), False).codigo, regras.DECISAO_PENDENTE)

    def test_impeditivo_bloqueia_mesmo_com_autorizacao(self):
        itens = self.itens(georref=ItemDecisao("georref", "Georref", False, "pendente", "impeditivo"))
        self.assertEqual(regras.decidir_publicacao(itens, True).codigo, regras.DECISAO_BLOQUEADO)

    def test_condicionante_com_titularidade_ok_e_ressalva(self):
        itens = self.itens(georref=ItemDecisao("georref", "Georref", False, "pendente", "condicionante"))
        resultado = regras.decidir_publicacao(itens, True)
        self.assertEqual(resultado.codigo, regras.DECISAO_RESSALVAS)
        self.assertIn("Condicionante: Georref", resultado.motivos)

    def test_essencial_pendente_sem_titularidade_fica_pendente(self):
        itens = self.itens(matricula_onus=ItemDecisao("matricula_onus", "Matrícula", True, "recebido"))
        self.assertEqual(regras.decidir_publicacao(itens, True).codigo, regras.DECISAO_PENDENTE)

    def test_documento_vencido_nao_conta_como_ok(self):
        itens = self.itens(car=ItemDecisao("car", "CAR", True, "validado", vencido=True))
        self.assertEqual(regras.decidir_publicacao(itens, True).codigo, regras.DECISAO_RESSALVAS)


class CompatibilidadeTests(SimpleTestCase):
    def imovel(self, **kw):
        base = dict(preco=Decimal("15000000"), area_ha=Decimal("240"), aptidoes={"cafe", "irrigada"},
                    municipio="Três Pontas", uf="MG", regiao="Sul de Minas", irrigacao=True,
                    mecanizavel_pct=Decimal("85"), decisao=regras.DECISAO_APTO)
        base.update(kw)
        return regras.PerfilImovel(**base)

    def demanda(self, **kw):
        base = dict(orcamento_min=Decimal("10000000"), orcamento_max=Decimal("20000000"), area_min=Decimal("150"),
                    area_max=Decimal("400"), aptidoes={"cafe"}, municipios=set(), regiao="Sul de Minas", uf="MG",
                    exige_irrigacao=True, mecanizacao_min=None)
        base.update(kw)
        return regras.PerfilDemanda(**base)

    def test_compatibilidade_total_explicada(self):
        pontos, criterios = regras.pontuar_compatibilidade(self.imovel(), self.demanda())
        self.assertEqual(pontos, 95)  # localização por região = 10 de 15
        self.assertEqual({c.nome for c in criterios}, {"Preço", "Área", "Aptidão", "Localização", "Infraestrutura", "Documentação"})

    def test_imovel_fora_do_perfil_pontua_menos(self):
        bom, _ = regras.pontuar_compatibilidade(self.imovel(), self.demanda())
        ruim, _ = regras.pontuar_compatibilidade(
            self.imovel(preco=Decimal("40000000"), aptidoes={"pecuaria_corte"}, irrigacao=False), self.demanda()
        )
        self.assertLess(ruim, 50)
        self.assertGreater(bom, ruim)


class ProtecaoTests(SimpleTestCase):
    def test_renovacao_nunca_encurta(self):
        hoje = date(2026, 10, 1)
        self.assertEqual(regras.renovar_protecao(None, hoje, 30), date(2026, 10, 31))
        self.assertEqual(regras.renovar_protecao(date(2026, 12, 31), hoje, 30), date(2026, 12, 31))

    def test_chaves_normalizam_telefone_e_email(self):
        a = regras.chaves_contato("+55 (35) 98888-1234", " Paulo@Exemplo.com ")
        b = regras.chaves_contato("35988881234", "paulo@exemplo.com")
        self.assertEqual(a, b)
        self.assertIn("doc:12345678901", regras.chaves_contato(documento="123.456.789-01"))


class ViabilidadeTests(SimpleTestCase):
    def test_parcela_price(self):
        self.assertEqual(regras.parcela_price(Decimal("1000000"), 0, 10), Decimal("100000.00"))
        self.assertEqual(regras.parcela_price(Decimal("1000000"), 10, 10), Decimal("162745.39"))

    def test_cenarios_ordenados(self):
        cenarios = regras.simular_viabilidade(
            area_produtiva_ha=100, produtividade_por_ha=30, preco_unitario=1000, custo_por_ha=20000,
            preco_imovel=5000000, entrada_pct=40, taxa_anual_pct=10, prazo_anos=10,
        )
        self.assertEqual([c["cenario"] for c in cenarios], ["Conservador", "Base", "Otimista"])
        self.assertLess(cenarios[0]["saldo_apos_divida"], cenarios[2]["saldo_apos_divida"])
