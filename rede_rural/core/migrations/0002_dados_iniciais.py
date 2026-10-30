"""Parâmetros iniciais da rede e trilhas da Universidade Rural (Estratégia V2, seções 06 e 19)."""
from decimal import Decimal

from django.db import migrations

NIVEIS = [
    ("pleno", "0.60", "1.00", "100", "0"),
    ("senior", "0.70", "1.30", "200", "20000000"),
    ("master", "0.80", "1.60", "300", "40000000"),
    ("partner", "1.00", "2.00", "400", "60000000"),
]

TRILHAS = [
    ("Fundamentos da corretagem", True),
    ("Ética, LGPD e compartilhamento de dados", True),
    ("Documentação rural: matrícula, CAR, CCIR e ITR", True),
    ("Solo e fertilidade", False),
    ("Cafeicultura", False),
    ("Grãos e irrigação", False),
    ("Pecuária de corte e leite", False),
    ("Silvicultura", False),
    ("Recursos hídricos e outorgas", False),
    ("APP, Reserva Legal e CAR", False),
    ("Georreferenciamento", False),
    ("Avaliação e comparáveis", False),
    ("Financiamento de aquisição", False),
    ("Tributos e sucessão", False),
    ("Negociação", False),
    ("Fotografia e drone", False),
    ("CRM e gestão de funil", False),
    ("Prevenção a fraudes", False),
    ("Atendimento e pós-venda", False),
]


def criar(apps, schema_editor):
    Configuracao = apps.get_model("core", "Configuracao")
    ParametroNivel = apps.get_model("core", "ParametroNivel")
    Trilha = apps.get_model("contas", "Trilha")
    Configuracao.objects.get_or_create(pk=1)
    for nivel, capt, venda, mensal, volume in NIVEIS:
        ParametroNivel.objects.get_or_create(
            nivel=nivel,
            defaults={
                "pct_captacao": Decimal(capt),
                "pct_venda": Decimal(venda),
                "mensalidade": Decimal(mensal),
                "volume_min_12m": Decimal(volume),
            },
        )
    for ordem, (nome, obrigatoria) in enumerate(TRILHAS):
        Trilha.objects.get_or_create(
            nome=nome, defaults={"ordem": ordem, "obrigatoria_ingresso": obrigatoria}
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
        ("contas", "0001_initial"),
    ]

    operations = [migrations.RunPython(criar, migrations.RunPython.noop)]
