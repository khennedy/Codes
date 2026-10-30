from django.urls import path

from contas import views

app_name = "contas"

urlpatterns = [
    path("inscricao/", views.inscricao, name="inscricao"),
    path("aguardando-aprovacao/", views.aguardando, name="aguardando"),
    path("corretores/", views.corretores, name="corretores"),
    path("corretores/<int:pk>/", views.corretor_detalhe, name="corretor"),
    path("meu-perfil/", views.corretor_detalhe, name="meu_perfil"),
    path("universidade/", views.universidade, name="universidade"),
    path("universidade/<int:pk>/", views.trilha_acao, name="trilha_acao"),
    path("mensalidades/", views.mensalidades, name="mensalidades"),
    path("mensalidades/gerar/", views.gerar_mensalidades, name="gerar_mensalidades"),
    path("mensalidades/<int:pk>/status/", views.mensalidade_status, name="mensalidade_status"),
]
