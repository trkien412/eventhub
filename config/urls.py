from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.db import connection

admin.site.site_header = "Quản trị hệ thống sự kiện"
admin.site.site_title = "Hệ thống sự kiện"
admin.site.index_title = "Bảng quản trị"


def health_check(request):
    """Endpoint nội bộ cho Docker healthcheck và Nginx."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"status": "error", "database": "unavailable"}, status=503)
    return JsonResponse({"status": "ok", "database": "ok"})


urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("", include("django_prometheus.urls")),  # /metrics
    path("healthz", health_check, name="health_check"),
    path("accounts/", include("accounts.urls")),
    path("", include("events.urls")),
    path("dashboard/", include("dashboard.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler403 = "config.views.permission_denied"
handler404 = "config.views.page_not_found"
handler500 = "config.views.server_error"
