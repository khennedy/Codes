from django.urls import path

from negocios import views

app_name = "negocios"

urlpatterns = [
    path("compradores/", views.compradores, name="compradores"),
    path("compradores/novo/", views.comprador_form, name="comprador_novo"),
    path("compradores/<int:pk>/", views.comprador_detalhe, name="comprador"),
    path("compradores/<int:pk>/editar/", views.comprador_form, name="comprador_editar"),
    path("compradores/<int:comprador_pk>/perfil-de-busca/", views.demanda_form, name="demanda_nova"),
    path("compradores/<int:comprador_pk>/perfil-de-busca/<int:pk>/", views.demanda_form, name="demanda_editar"),
    path("compradores/<int:comprador_pk>/credito/", views.credito_novo, name="credito_novo"),
    path("negociacoes/", views.funil, name="funil"),
    path("negociacoes/nova/", views.negociacao_nova, name="negociacao_nova"),
    path("negociacoes/<int:pk>/", views.negociacao_detalhe, name="negociacao"),
    path("negociacoes/<int:pk>/etapa/", views.negociacao_etapa, name="negociacao_etapa"),
    path("negociacoes/<int:pk>/atividade/", views.negociacao_atividade, name="negociacao_atividade"),
    path("negociacoes/<int:pk>/dossie/solicitar/", views.dossie_solicitar, name="dossie_solicitar"),
    path("negociacoes/<int:pk>/dossie/liberar/", views.dossie_liberar, name="dossie_liberar"),
    path("negociacoes/<int:pk>/visita/", views.visita_form, name="visita_nova"),
    path("negociacoes/<int:pk>/visita/<int:visita_pk>/", views.visita_form, name="visita_editar"),
    path("negociacoes/<int:pk>/comissao/", views.apuracao, name="apuracao"),
    path("visitas/<int:pk>/relatorio/", views.visita_relatorio, name="visita_relatorio"),
    path("conflitos/", views.conflitos, name="conflitos"),
    path("conflitos/novo/", views.conflito_novo, name="conflito_novo"),
    path("conflitos/<int:pk>/", views.conflito_detalhe, name="conflito"),
    path("credito/", views.credito, name="credito"),
    path("credito/<int:pk>/", views.credito_status, name="credito_status"),
]
