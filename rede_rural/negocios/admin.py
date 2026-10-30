from django.contrib import admin

from negocios.models import (
    ApuracaoComissao,
    Atividade,
    Comprador,
    Conflito,
    Demanda,
    EncaminhamentoCredito,
    Negociacao,
    ParticipacaoComissao,
    Visita,
)


class ParticipacaoInline(admin.TabularInline):
    model = ParticipacaoComissao
    extra = 0


@admin.register(ApuracaoComissao)
class ApuracaoAdmin(admin.ModelAdmin):
    list_display = ("negociacao", "valor_venda", "comissao_total", "status")
    inlines = [ParticipacaoInline]


@admin.register(Negociacao)
class NegociacaoAdmin(admin.ModelAdmin):
    list_display = ("imovel", "comprador", "corretor_vendedor", "etapa", "situacao", "atualizado_em")
    list_filter = ("etapa", "situacao")


@admin.register(Comprador)
class CompradorAdmin(admin.ModelAdmin):
    list_display = ("nome", "corretor", "origem", "protecao_ate", "duplicidade_de")
    search_fields = ("nome", "email", "telefone")


admin.site.register(Demanda)
admin.site.register(Atividade)
admin.site.register(Visita)
admin.site.register(Conflito)
admin.site.register(EncaminhamentoCredito)
