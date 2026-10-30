from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("entrar/", auth_views.LoginView.as_view(), name="login"),
    path("sair/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("core.urls")),
    path("", include("contas.urls")),
    path("", include("imoveis.urls")),
    path("", include("negocios.urls")),
]

admin.site.site_header = "Rede Rural — administração"
admin.site.site_title = "Rede Rural"
