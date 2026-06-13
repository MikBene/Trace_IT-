from django.contrib import admin
from .models import UserProfile, AuditLog, Species, Animal, TrackingTag, Deployment, Location, Alert, Geofence, WeatherData, BiometricReading

admin.site.register(UserProfile)
admin.site.register(AuditLog)
admin.site.register(Species)
admin.site.register(Animal)
admin.site.register(TrackingTag)
admin.site.register(Deployment)
admin.site.register(Location)
admin.site.register(Alert)
admin.site.register(Geofence)
admin.site.register(WeatherData)
admin.site.register(BiometricReading)