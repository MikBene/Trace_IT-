from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', include('Trace_It.urls')),
    path('admin/', admin.site.urls),
]

# Serve MEDIA files (user uploads: animal photos, etc.)
# This is separate from STATIC files which are handled by WhiteNoise
if settings.MEDIA_ROOT:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)