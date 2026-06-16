from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import math


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('ADMIN', 'Admin'),
        ('RANGER', 'Ranger'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='RANGER')
    phone = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"

    def is_admin(self):
        return self.role == 'ADMIN'

    def is_ranger(self):
        return self.role == 'RANGER'


class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    action = models.CharField(max_length=100)
    details = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.action} at {self.timestamp}"

    class Meta:
        ordering = ['-timestamp']


class Species(models.Model):
    CONSERVATION_CHOICES = [
        ('Least Concern', 'Least Concern'),
        ('Vulnerable', 'Vulnerable'),
        ('Endangered', 'Endangered'),
        ('Critically Endangered', 'Critically Endangered'),
    ]

    species_id = models.AutoField(primary_key=True)
    common_name = models.CharField(max_length=100)
    scientific_name = models.CharField(max_length=100, blank=True, null=True)
    conservation_status = models.CharField(
        max_length=30,
        choices=CONSERVATION_CHOICES,
        default='Least Concern'
    )

    def __str__(self):
        return self.common_name


class Animal(models.Model):
    GENDER_CHOICES = [
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Unknown', 'Unknown'),
    ]

    animal_id = models.CharField(max_length=20, primary_key=True, editable=False, unique=True)
    nickname = models.CharField(max_length=50, blank=True, null=True)
    species = models.ForeignKey(Species, on_delete=models.CASCADE)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    birth_year = models.IntegerField(blank=True, null=True)
    health_status = models.CharField(max_length=255, default='Healthy')
    weight = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    photo = models.ImageField(upload_to='animal_photos/', blank=True, null=True)
    last_seen = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Templates using animal.id will now work
    @property
    def id(self):
        return self.animal_id

    def __str__(self):
        return f"{self.animal_id} - {self.nickname or 'Unnamed'}"

    def save(self, *args, **kwargs):
        if not self.animal_id:
            self.animal_id = self.generate_animal_id()
        super().save(*args, **kwargs)

    @staticmethod
    def generate_animal_id():
        from django.db.models import Max
        year = timezone.now().year
        prefix = f"ANI-{year}-"

        latest = Animal.objects.filter(animal_id__startswith=prefix).aggregate(
            max_id=Max('animal_id')
        )['max_id']

        if latest:
            try:
                last_num = int(latest.split('-')[-1])
                new_num = last_num + 1
            except (ValueError, IndexError):
                new_num = 1
        else:
            new_num = 1

        return f"{prefix}{new_num:04d}"

    def get_latest_location(self):
        deployment = self.deployment_set.filter(is_active=True).first()
        if deployment:
            return Location.objects.filter(tag=deployment.tag).order_by('-timestamp').first()
        return None

    def get_all_locations(self, limit=100):
        """Return list instead of QuerySet to avoid sliced QuerySet filter issues."""
        deployment = self.deployment_set.filter(is_active=True).first()
        if deployment:
            return list(Location.objects.filter(tag=deployment.tag).order_by('-timestamp')[:limit])
        return []

    def get_latest_biometrics(self):
        deployment = self.deployment_set.filter(is_active=True).first()
        if deployment:
            return BiometricReading.objects.filter(tag=deployment.tag).order_by('-timestamp').first()
        return None

    def is_stationary(self, minutes=90):
        """Check if animal has been stationary. Filters in Python to avoid QuerySet slice issues."""
        locations = self.get_all_locations(limit=10)
        if len(locations) < 2:
            return False
        
        latest = locations[0] if locations else None
        if not latest:
            return False
            
        time_threshold = timezone.now() - timezone.timedelta(minutes=minutes)
        recent_locations = [loc for loc in locations if loc.timestamp >= time_threshold]
        
        if len(recent_locations) < 2:
            return False
            
        first_loc = recent_locations[-1]
        last_loc = recent_locations[0]
        
        distance = self.calculate_distance(
            float(first_loc.latitude), float(first_loc.longitude),
            float(last_loc.latitude), float(last_loc.longitude)
        )
        
        return distance < 50

    @staticmethod
    def calculate_distance(lat1, lon1, lat2, lon2):
        R = 6371000
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c


class TrackingTag(models.Model):
    tag_id = models.AutoField(primary_key=True)
    tag_serial_number = models.CharField(max_length=50, unique=True)
    battery_level = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    manufacturer = models.CharField(max_length=100, blank=True, null=True)
    last_service_date = models.DateField(blank=True, null=True)
    is_assigned = models.BooleanField(default=False)

    def __str__(self):
        return self.tag_serial_number

    def is_battery_low(self):
        if self.battery_level and self.battery_level < 20:
            return True
        return False

    def get_current_animal(self):
        deployment = self.deployment_set.filter(is_active=True).first()
        return deployment.animal if deployment else None


class Deployment(models.Model):
    deployment_id = models.AutoField(primary_key=True)
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE)
    tag = models.ForeignKey(TrackingTag, on_delete=models.CASCADE)
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.animal} → {self.tag}"

    def save(self, *args, **kwargs):
        if self.is_active and not self.pk:
            self.tag.is_assigned = True
            self.tag.save()
        super().save(*args, **kwargs)


class Location(models.Model):
    location_id = models.BigAutoField(primary_key=True)
    tag = models.ForeignKey(TrackingTag, on_delete=models.CASCADE)
    latitude = models.DecimalField(max_digits=10, decimal_places=8)
    longitude = models.DecimalField(max_digits=11, decimal_places=8)
    altitude = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
    temperature = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    speed = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    accuracy_meters = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)

    def __str__(self):
        return f"{self.latitude}, {self.longitude}"

    class Meta:
        ordering = ['-timestamp']


class BiometricReading(models.Model):
    reading_id = models.BigAutoField(primary_key=True)
    tag = models.ForeignKey(TrackingTag, on_delete=models.CASCADE)
    location = models.ForeignKey(Location, on_delete=models.CASCADE, null=True, blank=True)
    
    heart_rate_bpm = models.IntegerField(null=True, blank=True)
    spo2_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    body_temperature_c = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    accel_x = models.IntegerField(null=True, blank=True)
    accel_y = models.IntegerField(null=True, blank=True)
    accel_z = models.IntegerField(null=True, blank=True)
    
    timestamp = models.DateTimeField(auto_now_add=True)
    sensor_status = models.CharField(max_length=50, default='OK')

    def __str__(self):
        return f"HR:{self.heart_rate_bpm} SpO2:{self.spo2_percent}% Temp:{self.body_temperature_c}°C"

    class Meta:
        ordering = ['-timestamp']


class Geofence(models.Model):
    geofence_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    center_latitude = models.DecimalField(max_digits=10, decimal_places=8)
    center_longitude = models.DecimalField(max_digits=11, decimal_places=8)
    radius_meters = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    def check_location_inside(self, lat, lon):
        R = 6371000
        lat1 = math.radians(float(self.center_latitude))
        lat2 = math.radians(float(lat))
        delta_lat = math.radians(float(lat) - float(self.center_latitude))
        delta_lon = math.radians(float(lon) - float(self.center_longitude))

        a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance = R * c

        return distance <= float(self.radius_meters)


class Alert(models.Model):
    ALERT_TYPES = [
        ('GEOFENCE', 'Geofence Breach'),
        ('BATTERY', 'Low Battery'),
        ('TEMPERATURE', 'Temperature Alert'),
        ('SPEED', 'Speed Alert'),
        ('STATIONARY', 'Stationary Alert'),
        ('HEALTH', 'Health Alert'),
        ('SENSOR', 'Sensor Error'),
    ]

    SEVERITY_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('CRITICAL', 'Critical'),
    ]

    alert_id = models.AutoField(primary_key=True)
    animal = models.ForeignKey(Animal, on_delete=models.CASCADE)
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='MEDIUM')
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)
    resolved_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.alert_type} - {self.animal.nickname}"

    class Meta:
        ordering = ['-timestamp']


class WeatherData(models.Model):
    weather_id = models.AutoField(primary_key=True)
    location = models.ForeignKey(Location, on_delete=models.CASCADE)
    temperature = models.DecimalField(max_digits=5, decimal_places=2)
    humidity = models.IntegerField()
    wind_speed = models.DecimalField(max_digits=5, decimal_places=2)
    description = models.CharField(max_length=100)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.temperature}°C - {self.description}"