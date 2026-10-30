from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from contas.models import Corretor, Mensalidade, ProgressoTrilha, Trilha, Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Rede", {"fields": ("papel", "telefone")}),)
    list_display = ("username", "first_name", "last_name", "email", "papel", "is_active")
    list_filter = ("papel", "is_active", "is_superuser")


@admin.register(Corretor)
class CorretorAdmin(admin.ModelAdmin):
    list_display = ("usuario", "creci", "creci_uf", "nivel", "status", "creci_verificado")
    list_filter = ("nivel", "status", "creci_verificado")
    search_fields = ("usuario__first_name", "usuario__last_name", "creci")


admin.site.register(Trilha)
admin.site.register(ProgressoTrilha)
admin.site.register(Mensalidade)
