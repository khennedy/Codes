from django.conf import settings


def plataforma(request):
    contexto = {"PLATAFORMA_NOME": settings.PLATAFORMA_NOME}
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        contexto["eh_central"] = user.eh_central
        contexto["meu_corretor"] = user.perfil_corretor
    return contexto
