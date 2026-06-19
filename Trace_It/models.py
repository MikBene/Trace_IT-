from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import math


class Species(models.Model):
    species_id = models.AutoField(primary_key=True)
    common_name = models.CharField(max_length=100)
    scientific_name = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    conservation_status = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name_plural = 'Species'

    def __str__(self):
        return self.common_name


class Animal(models.Model):
    GENDER_CHOICES = [
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Unknown', 'Unknown'),
    ]

    animal_id = models.AutoField(primary_key=True)
    nickname = models.CharField(max_length=100)
    species = models.ForeignKey(Species, on_delete=models.SET_NULL, null=True, blank=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, default='Unknown')
    birth_year = models.PositiveIntegerField(null=True, blank=True)
    weight = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    health_status = models.CharField(max_length=50, default='Healthy')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.nickname} ({self.species.common_name if self.species else 'Unknown Species'})"

    @property
    def health_status_display(self):
        return self.health_status

    def get_latest_location(self):
        deployment = self.deployment_set.filter(is_active=True).first()
        if deployment and deployment.tag:
            return Location.objects.filter(tag=deployment.tag).order_by('-timestamp').first()
        return None

    def get_all_locations(self, limit=None):
        deployment = self.deployment_set.filter(is_active=True).first()
        if deployment and deployment.tag:
            qs = Location.objects.filter(tag=deployment.tag).order_by('-timestamp')
            if limit:
                return qs[:limit]
            return qs
        return Location.objects.none()

    def get_latest_biometrics(self):
        deployment = self.deployment_set.filter(is_active=True).first()
        if deployment and deployment.tag:
            return BiometricReading.objects.filter(tag=deployment.tag).order_by('-timestamp').first()
        return None

    @property
    def is_stationary(self):
        loc = self.get_latest_location()
        if not loc:
            return False
        time_diff = timezone.now() - loc.timestamp
        return time_diff.total_seconds() > 5400

    def is_stationary_minutes(self, minutes=90):
        loc = self.get_latest_location()
        if not loc:
            return False
        time_diff = timezone.now() - loc.timestamp
        return time_diff.total_seconds() > (minutes * 60)


class TrackingTag(models.Model):
    tag_id = models.AutoField(primary_key=True)
    tag_serial_number = models.CharField(max_length=50, unique=True)
    model = models.CharField(max_length=100, blank=True)
    manufacturer = models.CharField(max_length=100, blank=True)
    battery_level = models.PositiveIntegerField(default=100)
    last_service_date = models.DateField(null=True, blank=True)
    is_assigned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.tag_serial_number


class Deployment(models.Model):
    deployment_id = models.AutoField(primary_key=True)
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE)
    tag = models.ForeignKey(TrackingTag, on_delete=models.CASCADE)
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.tag.tag_serial_number} -> {self.animal.nickname}"


class Location(models.Model):
    location_id = models.AutoField(primary_key=True)
    tag = models.ForeignKey(TrackingTag, on_delete=models.CASCADE)
    latitude = models.DecimalField(max_digits=10, decimal_places=8)
    longitude = models.DecimalField(max_digits=11, decimal_places=8)
    altitude = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    speed = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    temperature = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.latitude}, {self.longitude} @ {self.timestamp}"


class BiometricReading(models.Model):
    reading_id = models.AutoField(primary_key=True)
    tag = models.ForeignKey(TrackingTag, on_delete=models.CASCADE)
    heart_rate = models.PositiveIntegerField(null=True, blank=True)
    spo2 = models.PositiveIntegerField(null=True, blank=True)
    body_temperature = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    sensor_status = models.CharField(max_length=20, default='OK')
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"HR:{self.heart_rate} SpO2:{self.spo2}% @ {self.timestamp}"

    @property
    def heart_rate_bpm(self):
        return self.heart_rate

    @property
    def spo2_percent(self):
        return self.spo2

    @property
    def body_temperature_c(self):
        return self.body_temperature

    @property
    def accel_x(self):
        return None

    @property
    def accel_y(self):
        return None

    @property
    def accel_z(self):
        return None


class Alert(models.Model):
    SEVERITY_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('CRITICAL', 'Critical'),
    ]

    ALERT_TYPES = [
        ('HEALTH', 'Health'),
        ('GEOFENCE', 'Geofence'),
        ('STATIONARY', 'Stationary'),
        ('SENSOR', 'Sensor'),
        ('BATTERY', 'Battery'),
    ]

    alert_id = models.AutoField(primary_key=True)
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE)
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='MEDIUM')
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.severity}] {self.alert_type}: {self.message[:50]}"


class Geofence(models.Model):
    geofence_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    center_latitude = models.DecimalField(max_digits=10, decimal_places=8)
    center_longitude = models.DecimalField(max_digits=11, decimal_places=8)
    radius_meters = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def check_location_inside(self, lat, lon):
        R = 6371000
        lat1 = math.radians(float(self.center_latitude))
        lat2 = math.radians(lat)
        dlat = math.radians(lat - float(self.center_latitude))
        dlon = math.radians(lon - float(self.center_longitude))

        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance = R * c

        return distance <= self.radius_meters


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('ADMIN', 'Admin'),
        ('RANGER', 'Ranger'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='RANGER')
    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} ({self.role})"

    def is_admin(self):
        return self.role == 'ADMIN'

    def is_ranger(self):
        return self.role == 'RANGER'


class AuditLog(models.Model):
    log_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=50)
    details = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.action} by {self.user} @ {self.timestamp}"


class WeatherData(models.Model):
    weather_id = models.AutoField(primary_key=True)
    location = models.ForeignKey(Location, on_delete=models.CASCADE)
    temperature = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    humidity = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    wind_speed = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    description = models.CharField(max_length=100, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.temperature}°C, {self.description} @ {self.timestamp}"