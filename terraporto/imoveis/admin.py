from django.contrib import admin

from imoveis.models import ContratoRepresentacao, DocumentoChecklist, FotoImovel, Imovel, Proprietario, VerificacaoBloco


class DocumentoInline(admin.TabularInline):
    model = DocumentoChecklist
    extra = 0


class ContratoInline(admin.TabularInline):
    model = ContratoRepresentacao
    extra = 0


@admin.register(Imovel)
class ImovelAdmin(admin.ModelAdmin):
    list_display = ("codigo", "titulo", "municipio", "uf", "status", "publicado", "captador")
    list_filter = ("status", "publicado", "uf", "aptidao_principal")
    search_fields = ("codigo", "titulo", "municipio", "matricula")
    inlines = [ContratoInline, DocumentoInline]


admin.site.register(Proprietario)
admin.site.register(FotoImovel)
admin.site.register(VerificacaoBloco)
