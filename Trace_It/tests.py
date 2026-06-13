from django.test import TestCase, Client
from django.contrib.auth.models import User
from .models import Species, Animal, TrackingTag, Deployment, Location, Geofence, Alert, UserProfile


class UserProfileModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('testuser', password='pass123')
        self.profile = UserProfile.objects.create(user=self.user, role='RANGER', phone='+254700000001')

    def test_profile_creation(self):
        self.assertEqual(str(self.profile), 'testuser (RANGER)')

    def test_is_ranger(self):
        self.assertTrue(self.profile.is_ranger())

    def test_is_admin(self):
        self.assertFalse(self.profile.is_admin())


class SpeciesModelTest(TestCase):
    def setUp(self):
        self.species = Species.objects.create(
            common_name='Spotted Hyena',
            scientific_name='Crocuta crocuta',
            conservation_status='Least Concern'
        )

    def test_species_creation(self):
        self.assertEqual(str(self.species), 'Spotted Hyena')


class AnimalModelTest(TestCase):
    def setUp(self):
        self.species = Species.objects.create(common_name='Spotted Hyena')
        self.animal = Animal.objects.create(
            nickname='Scar',
            species=self.species,
            gender='Male',
            birth_year=2018,
            health_status='Healthy'
        )

    def test_animal_creation(self):
        self.assertEqual(str(self.animal), 'Scar')

    def test_get_latest_location_no_deployment(self):
        self.assertIsNone(self.animal.get_latest_location())


class TrackingTagModelTest(TestCase):
    def setUp(self):
        self.tag = TrackingTag.objects.create(
            tag_serial_number='HYENA001',
            battery_level=85.50
        )

    def test_tag_creation(self):
        self.assertEqual(str(self.tag), 'HYENA001')

    def test_battery_not_low(self):
        self.assertFalse(self.tag.is_battery_low())

    def test_battery_low(self):
        self.tag.battery_level = 15
        self.assertTrue(self.tag.is_battery_low())


class DeploymentModelTest(TestCase):
    def setUp(self):
        self.species = Species.objects.create(common_name='Spotted Hyena')
        self.animal = Animal.objects.create(
            nickname='Scar',
            species=self.species,
            gender='Male'
        )
        self.tag = TrackingTag.objects.create(tag_serial_number='HYENA002')
        self.deployment = Deployment.objects.create(
            animal=self.animal,
            tag=self.tag
        )

    def test_deployment_active(self):
        self.assertTrue(self.deployment.is_active)


class LocationModelTest(TestCase):
    def setUp(self):
        self.tag = TrackingTag.objects.create(tag_serial_number='HYENA003')
        self.location = Location.objects.create(
            tag=self.tag,
            latitude=-0.4167,
            longitude=36.9500,
            altitude=1500.00,
            temperature=28.5,
            speed=5.2
        )

    def test_location_creation(self):
        self.assertEqual(str(self.location), '-0.41670000, 36.95000000')


class GeofenceModelTest(TestCase):
    def setUp(self):
        self.geofence = Geofence.objects.create(
            name='QENP Safe Zone',
            center_latitude=-0.4167,
            center_longitude=36.9500,
            radius_meters=5000
        )

    def test_location_inside(self):
        self.assertTrue(self.geofence.check_location_inside(-0.4167, 36.9500))

    def test_location_outside(self):
        self.assertFalse(self.geofence.check_location_inside(-0.5000, 37.0000))


class AlertModelTest(TestCase):
    def setUp(self):
        self.species = Species.objects.create(common_name='Spotted Hyena')
        self.animal = Animal.objects.create(
            nickname='Scar',
            species=self.species,
            gender='Male'
        )
        self.alert = Alert.objects.create(
            animal=self.animal,
            alert_type='GEOFENCE',
            severity='HIGH',
            message='Scar has left the safe zone!'
        )

    def test_alert_creation(self):
        self.assertEqual(str(self.alert), 'GEOFENCE - Scar')

    def test_alert_unresolved(self):
        self.assertFalse(self.alert.is_resolved)


class ViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('ranger', password='pass123')
        self.profile = UserProfile.objects.create(user=self.user, role='RANGER')
        self.admin_user = User.objects.create_user('admin', password='admin123')
        self.admin_profile = UserProfile.objects.create(user=self.admin_user, role='ADMIN')
        self.species = Species.objects.create(common_name='Spotted Hyena')
        self.animal = Animal.objects.create(
            nickname='Scar',
            species=self.species,
            gender='Male'
        )

    def test_landing_page(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_ranger_login_view(self):
        response = self.client.get('/login/ranger/')
        self.assertEqual(response.status_code, 200)

    def test_admin_login_view(self):
        response = self.client.get('/login/admin/')
        self.assertEqual(response.status_code, 200)

    def test_dashboard_requires_login(self):
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 302)

    def test_dashboard_admin_logged_in(self):
        self.client.login(username='admin', password='admin123')
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)

    def test_index_ranger_logged_in(self):
        self.client.login(username='ranger', password='pass123')
        response = self.client.get('/home/')
        self.assertEqual(response.status_code, 200)

    def test_logout_redirects_to_landing(self):
        self.client.login(username='ranger', password='pass123')
        response = self.client.get('/logout/')
        self.assertEqual(response.status_code, 302)