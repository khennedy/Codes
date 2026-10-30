"""Cria o primeiro usuário da central a partir de variáveis de ambiente.

Variáveis: CENTRAL_USUARIO, CENTRAL_EMAIL e CENTRAL_SENHA. Se o usuário já existe,
nada muda (a senha não é sobrescrita). Roda a cada deploy sem efeito colateral.
"""
import os

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management import BaseCommand, CommandError

from contas.models import Usuario


class Command(BaseCommand):
    help = "Cria o usuário administrador da central (CENTRAL_USUARIO, CENTRAL_EMAIL, CENTRAL_SENHA)."

    def handle(self, *args, **opcoes):
        login = os.environ.get("CENTRAL_USUARIO", "").strip()
        email = os.environ.get("CENTRAL_EMAIL", "").strip()
        senha = os.environ.get("CENTRAL_SENHA", "")
        if not login or not senha:
            self.stdout.write("CENTRAL_USUARIO/CENTRAL_SENHA não definidos: nenhum usuário criado.")
            return
        if Usuario.objects.filter(username=login).exists():
            self.stdout.write(f"Usuário '{login}' já existe: nada a fazer.")
            return
        usuario = Usuario(username=login, email=email, papel=Usuario.Papel.CENTRAL, is_staff=True, is_superuser=True)
        try:
            validate_password(senha, usuario)
        except ValidationError as erro:
            raise CommandError("Senha da central fraca: " + " ".join(erro.messages)) from erro
        usuario.set_password(senha)
        usuario.save()
        self.stdout.write(self.style.SUCCESS(f"Usuário da central '{login}' criado."))
