from django.urls import path

from core import views

app_name = "core"

urlpatterns = [
    path("", views.vitrine, name="vitrine"),
    path("vitrine/<str:codigo>/", views.vitrine_detalhe, name="vitrine_detalhe"),
    path("quero-vender/", views.quero_vender, name="quero_vender"),
    path("painel/", views.painel, name="painel"),
    path("simulador/", views.simulador, name="simulador"),
    path("leads/", views.leads, name="leads"),
    path("leads/<int:pk>/atribuir/", views.lead_atribuir, name="lead_atribuir"),
    path("configuracoes/", views.configuracoes, name="configuracoes"),
    path("auditoria/", views.auditoria, name="auditoria"),
    path("arquivos/foto/<int:pk>/", views.arquivo_foto, name="arquivo_foto"),
    path("arquivos/documento/<int:pk>/", views.arquivo_documento, name="arquivo_documento"),
    path("minutas/associacao/<int:pk>/", views.minuta_associacao, name="minuta_associacao"),
    path("minutas/representacao/<int:pk>/", views.minuta_representacao, name="minuta_representacao"),
]
