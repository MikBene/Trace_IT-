import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Wildlife_Tracking_System.settings')
django.setup()

from django.contrib.auth.models import User
from Trace_It.models import UserProfile
from django.contrib.auth.hashers import make_password

# Delete any existing admin users
User.objects.filter(username='admin').delete()

# Create admin with CORRECT password hashing
admin = User.objects.create(
    username='admin',
    email='admin@traceit.com',
    first_name='Matovu',
    last_name='Kizito',
    is_staff=True,
    is_superuser=True,
    is_active=True,
    password=make_password('admin123')  # This properly hashes the password
)

# Create profile
UserProfile.objects.create(user=admin, role='ADMIN', phone='+255778014203')

print("=" * 50)
print("ADMIN CREATED SUCCESSFULLY")
print("=" * 50)
print("Email: admin@traceit.com")
print("Password: admin123")
print("Username (internal): admin")
print("=" * 50)

# Verify password works
from django.contrib.auth import authenticate
test = authenticate(username='admin', password='admin123')
if test:
    print("✓ Authentication test PASSED")
else:
    print("✗ Authentication test FAILED")