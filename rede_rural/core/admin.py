from django.contrib import admin

from core.models import Configuracao, LeadPublico, LogAuditoria, ParametroNivel


@admin.register(LogAuditoria)
class LogAuditoriaAdmin(admin.ModelAdmin):
    list_display = ("criado_em", "usuario", "acao", "objeto_tipo", "objeto_id")
    list_filter = ("acao", "objeto_tipo")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Configuracao)
admin.site.register(ParametroNivel)
admin.site.register(LeadPublico)
