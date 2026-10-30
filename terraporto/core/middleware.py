from django.db import connection
from django.http import HttpResponse


class SaudeMiddleware:
    """Responde /saude/ antes da validação de host e do redirecionamento HTTPS,
    para o health check da hospedagem. Confirma que o banco responde."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/saude/":
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            return HttpResponse("ok", content_type="text/plain")
        return self.get_response(request)
