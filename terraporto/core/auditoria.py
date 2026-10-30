from core.models import LogAuditoria


def registrar(usuario, acao: str, objeto=None, descricao: str = ""):
    LogAuditoria.objects.create(
        usuario=usuario if getattr(usuario, "is_authenticated", False) else None,
        acao=acao,
        objeto_tipo=objeto._meta.model_name if objeto is not None else "",
        objeto_id=getattr(objeto, "pk", None),
        descricao=descricao,
    )


def historico(objeto, limite=30):
    return LogAuditoria.objects.filter(
        objeto_tipo=objeto._meta.model_name, objeto_id=objeto.pk
    ).select_related("usuario")[:limite]
