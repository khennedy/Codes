"""Modelo do checklist documental (Anexo 01 — Checklist Documental e Diligência Rural).

Cada item: (código, categoria, descrição, essencial, aplica_a) onde aplica_a é
"todos", "pf" ou "pj" conforme o tipo do vendedor.
"""

CATEGORIAS = [
    ("identificacao", "1. Identificação e autorização"),
    ("pessoa_fisica", "2. Pessoa física — vendedor e intervenientes"),
    ("pessoa_juridica", "3. Pessoa jurídica — vendedor"),
    ("registro", "4. Registro, área e situação possessória"),
    ("ambiental", "5. Ambiental, hídrico e produtivo"),
    ("benfeitorias", "6. Benfeitorias, segurança e obrigações"),
]

ITENS = [
    ("id_titulares", "identificacao",
     "Proprietário registral, coproprietários, cônjuge, procuradores, usufrutuários e espólios identificados",
     True, "todos"),
    ("autorizacao", "identificacao",
     "Autorização escrita de intermediação e publicidade antes da divulgação", True, "todos"),
    ("pf_documentos", "pessoa_fisica", "RG/CNH, CPF, endereço e dados de contato", True, "pf"),
    ("pf_estado_civil", "pessoa_fisica",
     "Estado civil e regime de bens comprovados (certidão de casamento, pacto antenupcial)", True, "pf"),
    ("pf_anuencia", "pessoa_fisica", "Anuência conjugal, conforme o caso", False, "pf"),
    ("pf_procuracao", "pessoa_fisica",
     "Procuração com poderes específicos e vigência verificada (se houver)", False, "pf"),
    ("pf_sucessao", "pessoa_fisica",
     "Herdeiros, inventário e formal de partilha (se imóvel em sucessão)", False, "pf"),
    ("pf_certidoes", "pessoa_fisica",
     "Certidões fiscais, cíveis, trabalhistas e de protestos pertinentes ao risco", False, "pf"),
    ("pj_cnpj", "pessoa_juridica", "CNPJ, situação cadastral e contrato/estatuto social consolidado", True, "pj"),
    ("pj_poderes", "pessoa_juridica",
     "Documentos dos administradores, poderes de representação e ata/autorização para alienação", True, "pj"),
    ("pj_certidoes", "pessoa_juridica",
     "Certidões tributárias, trabalhistas, judiciais e de recuperação/falência", False, "pj"),
    ("pj_beneficiarios", "pessoa_juridica",
     "Beneficiários finais e estrutura de controle (PLD/FTP)", False, "pj"),
    ("matricula_onus", "registro",
     "Matrícula atualizada de cada gleba e certidão de ônus reais (hipoteca, penhora, usufruto, servidões)",
     True, "todos"),
    ("cadeia_dominial", "registro", "Cadeia dominial / certidão vintenária quando tecnicamente necessária",
     False, "todos"),
    ("ccir_itr", "registro", "CCIR e comprovantes ITR/DITR", True, "todos"),
    ("georref", "registro",
     "Georreferenciamento, certificação SIGEF/INCRA, memorial descritivo, planta e marcos", False, "todos"),
    ("contratos_agrarios", "registro",
     "Arrendamentos, parcerias, comodatos, ocupações e direitos de preferência", False, "todos"),
    ("confrontacoes", "registro",
     "Confrontações, acesso legal, servidões de passagem e sobreposição de áreas", False, "todos"),
    ("car", "ambiental", "Recibo e situação do CAR, com divergências de APP/RL (CAR não prova regularidade plena)",
     True, "todos"),
    ("licencas", "ambiental", "Licenças, autorizações, TACs, embargos e autos de infração", False, "todos"),
    ("outorgas", "ambiental", "Outorgas/cadastros de uso de água: poços, barramentos, captações, irrigação",
     False, "todos"),
    ("passivos_amb", "ambiental", "Histórico de supressão vegetal, passivos ambientais e PRA/PRAD",
     False, "todos"),
    ("analise_solo", "ambiental", "Análise química de solo (preferencialmente dos últimos 12 meses)",
     False, "todos"),
    ("historico_produtivo", "ambiental", "Histórico produtivo de no mínimo duas safras/anos, com fonte",
     False, "todos"),
    ("benfeitorias", "benfeitorias",
     "Benfeitorias e bens incluídos/excluídos, com fotos e estado de conservação", False, "todos"),
    ("trabalhistas", "benfeitorias", "Trabalhadores residentes, contratos e contingências trabalhistas",
     False, "todos"),
    ("litigios", "benfeitorias", "Passivos, litígios e bens vinculados a garantias", False, "todos"),
]


def itens_para(tipo_vendedor: str):
    tipo = (tipo_vendedor or "pf").lower()
    return [item for item in ITENS if item[4] in ("todos", tipo)]
