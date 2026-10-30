APTIDOES = [
    ("cafe", "Cafeicultura"),
    ("pecuaria_corte", "Pecuária de corte"),
    ("pecuaria_leite", "Pecuária de leite"),
    ("graos", "Grãos"),
    ("silvicultura", "Silvicultura"),
    ("fruticultura", "Fruticultura / hortaliças"),
    ("irrigada", "Produção irrigada"),
    ("lazer", "Lazer / chácara"),
    ("misto", "Uso misto"),
]
ROTULO_APTIDAO = dict(APTIDOES)

UFS = [
    (uf, uf)
    for uf in (
        "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
    )
]


def lista_codigos(texto: str) -> list[str]:
    return [c for c in (texto or "").split(",") if c]


def rotulos_aptidao(texto: str) -> list[str]:
    return [ROTULO_APTIDAO.get(c, c) for c in lista_codigos(texto)]
