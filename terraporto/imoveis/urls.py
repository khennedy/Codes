from django.urls import path

from imoveis import views

app_name = "imoveis"

urlpatterns = [
    path("proprietarios/", views.proprietarios, name="proprietarios"),
    path("proprietarios/novo/", views.proprietario_form, name="proprietario_novo"),
    path("proprietarios/<int:pk>/editar/", views.proprietario_form, name="proprietario_editar"),
    path("imoveis/", views.lista, name="lista"),
    path("imoveis/novo/", views.imovel_form, name="novo"),
    path("imoveis/<int:pk>/", views.detalhe, name="detalhe"),
    path("imoveis/<int:pk>/editar/", views.imovel_form, name="editar"),
    path("imoveis/<int:pk>/checklist/", views.checklist, name="checklist"),
    path("imoveis/<int:pk>/fotos/nova/", views.foto_nova, name="foto_nova"),
    path("imoveis/fotos/<int:pk>/remover/", views.foto_remover, name="foto_remover"),
    path("imoveis/<int:pk>/autorizacao/nova/", views.contrato_form, name="contrato_novo"),
    path("imoveis/<int:pk>/autorizacao/<int:contrato_pk>/", views.contrato_form, name="contrato_editar"),
    path("imoveis/<int:pk>/enviar-validacao/", views.enviar_validacao, name="enviar_validacao"),
    path("imoveis/<int:pk>/avaliar/", views.avaliar, name="avaliar"),
    path("imoveis/<int:pk>/dossie/", views.dossie, name="dossie"),
    path("catalogo/", views.catalogo, name="catalogo"),
    path("catalogo/<int:pk>/", views.catalogo_detalhe, name="catalogo_detalhe"),
]
