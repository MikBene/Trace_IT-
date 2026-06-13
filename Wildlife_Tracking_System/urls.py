from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('', include('Trace_It.urls')),
    path('admin/', admin.site.urls),
]