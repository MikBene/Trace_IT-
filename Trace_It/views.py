import uuid
import csv
import json
import logging
import traceback
import math
from datetime import datetime, timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.hashers import check_password, make_password
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.db import models, transaction
from django.db.models import Q

from .models import Animal, Species, TrackingTag, Deployment, Location, Alert, Geofence, UserProfile, AuditLog, BiometricReading
from .forms import AnimalForm, TrackingTagForm, GeofenceForm

logger = logging.getLogger(__name__)


# ===== AUTO-GENERATED ANIMAL ID =====

def generate_animal_id():
    """Generate next auto-incrementing animal ID like ANM-2026-0001"""
    year = datetime.now().year
    prefix = f"ANM-{year}-"

    existing = Animal.objects.filter(animal_id__startswith=prefix).order_by('-animal_id').first()

    if existing:
        try:
            last_num = int(existing.animal_id.split('-')[-1])
            next_num = last_num + 1
        except (ValueError, IndexError):
            next_num = 1
    else:
        next_num = 1

    return f"{prefix}{next_num:04d}"


# ===== UTILITY FUNCTIONS =====

def log_action(user, action, details):
    try:
        AuditLog.objects.create(user=user, action=action, details=details)
    except Exception:
        pass


def get_user_by_email(email):
    try:
        return User.objects.get(email__iexact=email.strip().lower())
    except User.DoesNotExist:
        return None


def parse_sentinel(val):
    """Parse IoT sentinel values (-999) to None."""
    if val is None or val == '' or val == -999 or val == '-999':
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def parse_int_sentinel(val):
    """Parse IoT sentinel integer values to None."""
    if val is None or val == '' or val == -999 or val == '-999':
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


# ===== DECORATORS =====

def admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('admin_login')
        try:
            profile = request.user.userprofile
            if not profile.is_admin():
                return HttpResponseForbidden("Admin access required.")
        except UserProfile.DoesNotExist:
            return HttpResponseForbidden("Admin access required.")
        return view_func(request, *args, **kwargs)
    return wrapper


def ranger_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('ranger_login')
        try:
            profile = request.user.userprofile
            if not profile.is_ranger() and not profile.is_admin():
                return HttpResponseForbidden("Access denied.")
        except UserProfile.DoesNotExist:
            return HttpResponseForbidden("Access denied.")
        return view_func(request, *args, **kwargs)
    return wrapper


# ===== HEALTH ALERT CHECKING =====

def check_health_alerts(tag, hr, spo2, temp, sensor_status):
    """Check biometrics and create health alerts."""
    deployment = Deployment.objects.filter(tag=tag, is_active=True).first()
    if not deployment:
        return

    animal = deployment.animal

    if sensor_status and sensor_status != 'OK':
        Alert.objects.get_or_create(
            animal=animal,
            alert_type='SENSOR',
            is_resolved=False,
            defaults={
                'message': f'{animal.nickname}: IoT sensor error - {sensor_status}',
                'severity': 'MEDIUM',
            }
        )
        return

    if hr is not None:
        if hr < 30 or hr > 150:
            Alert.objects.get_or_create(
                animal=animal,
                alert_type='HEALTH',
                is_resolved=False,
                defaults={
                    'message': f'{animal.nickname}: Critical heart rate {hr} BPM detected!',
                    'severity': 'CRITICAL',
                }
            )
        elif hr < 40 or hr > 120:
            Alert.objects.get_or_create(
                animal=animal,
                alert_type='HEALTH',
                is_resolved=False,
                defaults={
                    'message': f'{animal.nickname}: Abnormal heart rate {hr} BPM',
                    'severity': 'HIGH',
                }
            )

    if spo2 is not None:
        if spo2 < 85:
            Alert.objects.get_or_create(
                animal=animal,
                alert_type='HEALTH',
                is_resolved=False,
                defaults={
                    'message': f'{animal.nickname}: Critical low blood oxygen {spo2}%',
                    'severity': 'CRITICAL',
                }
            )
        elif spo2 < 90:
            Alert.objects.get_or_create(
                animal=animal,
                alert_type='HEALTH',
                is_resolved=False,
                defaults={
                    'message': f'{animal.nickname}: Low blood oxygen {spo2}%',
                    'severity': 'HIGH',
                }
            )

    if temp is not None:
        if temp > 42 or temp < 32:
            Alert.objects.get_or_create(
                animal=animal,
                alert_type='HEALTH',
                is_resolved=False,
                defaults={
                    'message': f'{animal.nickname}: Critical body temperature {temp}°C',
                    'severity': 'CRITICAL',
                }
            )
        elif temp > 40 or temp < 35:
            Alert.objects.get_or_create(
                animal=animal,
                alert_type='HEALTH',
                is_resolved=False,
                defaults={
                    'message': f'{animal.nickname}: Abnormal body temperature {temp}°C',
                    'severity': 'HIGH',
                }
            )


def check_geofence_violations(animal, location):
    geofences = Geofence.objects.filter(is_active=True)

    for geofence in geofences:
        is_inside = geofence.check_location_inside(
            float(location.latitude), float(location.longitude)
        )

        if not is_inside:
            alert, created = Alert.objects.get_or_create(
                animal=animal,
                alert_type='GEOFENCE',
                is_resolved=False,
                defaults={
                    'message': f'{animal.nickname} has left the {geofence.name} geofence.',
                    'severity': 'HIGH',
                }
            )

            if created:
                send_email_alert(animal, geofence, alert)


def check_stationary_alert(animal):
    if animal.is_stationary_minutes(minutes=90):
        Alert.objects.get_or_create(
            animal=animal,
            alert_type='STATIONARY',
            is_resolved=False,
            defaults={
                'message': f'{animal.nickname} has been stationary for over 90 minutes.',
                'severity': 'MEDIUM',
            }
        )


def send_email_alert(animal, geofence, alert):
    subject = f'ALERT: {animal.nickname} - Geofence Breach'
    message = f"""Critical Alert for {animal.nickname}

Alert Type: Geofence Breach
Geofence: {geofence.name}
Time: {alert.timestamp}

{animal.nickname} has left the designated safe area.
Please investigate immediately.

---
Trace_It Wildlife Monitoring System
"""

    admin_emails = User.objects.filter(
        userprofile__role='ADMIN'
    ).values_list('email', flat=True)

    if admin_emails:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=list(admin_emails),
            fail_silently=True,
        )


# ===== GEOFENCING CONTAINMENT VALIDATION ALGORITHM =====

def check_geofence_breach(animal, location):
    """
    Calculates the distance between the animal's new coordinates and all active geofences.
    Triggers an Alert system record if a breach rule is violated using the Haversine formula.
    """
    geofences = Geofence.objects.filter(is_active=True)

    lat2 = float(location.latitude)
    lon2 = float(location.longitude)

    for fence in geofences:
        lat1 = float(fence.center_latitude)
        lon1 = float(fence.center_longitude)
        radius = float(fence.radius_meters)

        # Haversine Formula to compute real-world distance in meters over the Earth's surface
        R = 6371000  # Radius of Earth in meters
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = (math.sin(delta_phi / 2) ** 2) + \
            (math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2) ** 2))
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance = R * c

        is_outside = distance > radius

        if fence.fence_type == 'exclusion' and not is_outside:
            Alert.objects.get_or_create(
                animal=animal,
                alert_type='GEOFENCE',
                is_resolved=False,
                defaults={
                    'severity': 'CRITICAL',
                    'message': f"Exclusion zone breach! {animal.nickname} has entered protected area '{fence.name}' (Distance: {distance:.1f}m)."
                }
            )
        elif fence.fence_type == 'inclusion' and is_outside:
            Alert.objects.get_or_create(
                animal=animal,
                alert_type='GEOFENCE',
                is_resolved=False,
                defaults={
                    'severity': 'HIGH',
                    'message': f"Inclusion zone escape! {animal.nickname} has wandered out of safe perimeter '{fence.name}' (Distance: {distance:.1f}m)."
                }
            )


# ===== AUTH & LANDING =====

def landing_page(request):
    return render(request, 'Trace_It/landing_page.html')


def ranger_login(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')

        if not email or not password:
            messages.error(request, 'Please enter both email and password.')
            return render(request, 'Trace_It/ranger_login.html')

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            messages.error(request, 'No account found with this email address.')
            return render(request, 'Trace_It/ranger_login.html')

        if not check_password(password, user.password):
            messages.error(request, 'Invalid password.')
            return render(request, 'Trace_It/ranger_login.html')

        profile, created = UserProfile.objects.get_or_create(
            user=user,
            defaults={'role': 'RANGER', 'phone': ''}
        )

        if not (profile.is_ranger() or profile.is_admin()):
            messages.error(request, 'This account is not authorized as Staff.')
            return render(request, 'Trace_It/ranger_login.html')

        login(request, user)
        messages.success(request, f'Welcome back, {user.first_name or user.email}! You are now logged in as Staff.')
        return redirect('index')

    return render(request, 'Trace_It/ranger_login.html')


def admin_login(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')

        if not email or not password:
            messages.error(request, 'Please enter both email and password.')
            return render(request, 'Trace_It/admin_login.html')

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            messages.error(request, 'No account found with this email address.')
            return render(request, 'Trace_It/admin_login.html')

        if not check_password(password, user.password):
            messages.error(request, 'Invalid password.')
            return render(request, 'Trace_It/admin_login.html')

        profile, created = UserProfile.objects.get_or_create(
            user=user,
            defaults={'role': 'ADMIN', 'phone': ''}
        )

        if not profile.is_admin():
            messages.error(request, 'This account does not have Admin privileges.')
            return render(request, 'Trace_It/admin_login.html')

        login(request, user)
        messages.success(request, f'Welcome back, Admin {user.first_name or user.email}! You are now logged in as Admin.')
        return redirect('dashboard')

    return render(request, 'Trace_It/admin_login.html')


def logout_view(request):
    if request.user.is_authenticated:
        messages.info(request, 'You have been logged out successfully.')
    logout(request)
    request.session.flush()
    return redirect('landing_page')


# ===== MAIN PAGES =====


@login_required
def index(request):
    """Home page showing all animals with their latest data."""
    animal_data = []
    total_animals = 0

    try:
        animals = Animal.objects.all().select_related('species')
        total_animals = animals.count()
    except Exception as e:
        logger.error(f"Error fetching animals: {e}")
        messages.error(request, 'Database error loading animals. Please try again.')
        return render(request, 'Trace_It/index.html', {
            'animal_data': [],
            'total_animals': 0,
            'active_trackers': 0,
            'alerts_today': 0,
            'total_geofences': 0,
            'debug': settings.DEBUG
        })

    for animal in animals:
        try:
            latest_location = animal.get_latest_location()

            deployment = animal.deployment_set.filter(is_active=True).first()
            has_tracker = deployment is not None
            tracker_id = deployment.tag.tag_serial_number if (deployment and deployment.tag) else None
            battery_level = deployment.tag.battery_level if (deployment and deployment.tag) else None

            if latest_location:
                time_diff = timezone.now() - latest_location.timestamp
                if time_diff.total_seconds() < 3600:
                    status = 'active'
                else:
                    status = 'inactive'
            else:
                status = 'inactive'

            animal_data.append({
                'animal_id': animal.animal_id,
                'name': animal.nickname,
                'species_name': animal.species.common_name if animal.species else 'Unknown',
                'status': status,
                'has_tracker': has_tracker,
                'tracker_id': tracker_id,
                'battery_level': battery_level,
                'last_seen': latest_location.timestamp if latest_location else None,
                'health_status': animal.health_status or 'Unknown',
            })
        except Exception as e:
            logger.error(f"Error processing animal {animal.animal_id}: {e}")
            continue

    active_trackers = sum(1 for a in animal_data if a['has_tracker'])
    alerts_today = Alert.objects.filter(
        timestamp__date=timezone.now().date(),
        is_resolved=False
    ).count()
    total_geofences = Geofence.objects.filter(is_active=True).count()

    context = {
        'animal_data': animal_data,
        'total_animals': total_animals,
        'active_trackers': active_trackers,
        'alerts_today': alerts_today,
        'total_geofences': total_geofences,
        'debug': settings.DEBUG
    }
    return render(request, 'Trace_It/index.html', context)


@login_required
@admin_required
def dashboard(request):
    """Admin dashboard with stats and overview."""
    context = {
        'total_animals': 0,
        'total_tags': 0,
        'active_deployments': 0,
        'total_locations': 0,
        'unresolved_alerts': 0,
        'recent_alerts': [],
        'recent_locations': [],
        'recent_logs': [],
        'low_battery_tags': 0,
        'recent_biometrics': [],
        'sensor_errors': 0,
        'critical_health_alerts': 0,
    }

    try:
        context['total_animals'] = Animal.objects.count()
        context['total_tags'] = TrackingTag.objects.count()
        context['active_deployments'] = Deployment.objects.filter(is_active=True).count()
        context['total_locations'] = Location.objects.count()
        context['unresolved_alerts'] = Alert.objects.filter(is_resolved=False).count()
        context['recent_alerts'] = Alert.objects.filter(is_resolved=False).order_by('-timestamp')[:10]
        context['recent_locations'] = Location.objects.all().select_related('tag').order_by('-timestamp')[:10]
        context['recent_logs'] = AuditLog.objects.all().order_by('-timestamp')[:20]
        context['low_battery_tags'] = TrackingTag.objects.filter(battery_level__lt=20).count()
        context['recent_biometrics'] = BiometricReading.objects.all().order_by('-timestamp')[:10]
        context['sensor_errors'] = BiometricReading.objects.exclude(sensor_status='OK').count()
        context['critical_health_alerts'] = Alert.objects.filter(
            alert_type='HEALTH', 
            is_resolved=False,
            severity__in=['HIGH', 'CRITICAL']
        ).count()
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        messages.error(request, f'Dashboard error: {str(e)}')

    return render(request, 'Trace_It/dashboard.html', context)


@login_required
@ranger_required
def animal_detail(request, animal_id):
    try:
        animal = get_object_or_404(Animal, animal_id=animal_id)
        locations = []
        latest_biometrics = None
        tags = []
        alerts = []
        biometric_history = []

        try:
            locations = animal.get_all_locations(limit=50)
        except Exception as e:
            logger.error(f"animal_detail locations error: {e}")

        try:
            latest_biometrics = animal.get_latest_biometrics()
        except Exception as e:
            logger.error(f"animal_detail biometrics error: {e}")

        try:
            deployment = animal.deployment_set.filter(is_active=True).first()
            tags = [deployment.tag] if deployment else []
        except Exception as e:
            logger.error(f"animal_detail deployment error: {e}")

        try:
            alerts = Alert.objects.filter(animal=animal).order_by('-timestamp')[:10]
        except Exception as e:
            logger.error(f"animal_detail alerts error: {e}")

        try:
            biometric_history = BiometricReading.objects.filter(
                tag__deployment__animal=animal
            ).order_by('-timestamp')[:50]
        except Exception as e:
            logger.error(f"animal_detail biometric_history error: {e}")

        context = {
            'animal': animal,
            'locations': locations,
            'tags': tags,
            'alerts': alerts,
            'latest_biometrics': latest_biometrics,
            'biometric_history': biometric_history,
        }
        return render(request, 'Trace_It/animal_detail.html', context)
    except Exception as e:
        logger.error(f"animal_detail critical error: {e}")
        messages.error(request, f'Error loading animal details: {str(e)}')
        return redirect('index')


@login_required
@admin_required
def add_animal(request):
    if request.method == 'POST':
        form = AnimalForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                with transaction.atomic():
                    animal = form.save(commit=False)
                    # Auto-generate animal_id if not provided
                    if not animal.animal_id:
                        animal.animal_id = generate_animal_id()
                    animal.save()

                    # Handle tag from form (user-selected) - form.save() already handles tag assignment
                    # Only auto-attach if user didn't select a tag AND unassigned tags exist
                    esp32_tag = form.cleaned_data.get('esp32_tag')
                    if not esp32_tag:
                        unassigned_tag = TrackingTag.objects.filter(is_assigned=False).first()
                        if unassigned_tag:
                            Deployment.objects.create(
                                animal=animal,
                                tag=unassigned_tag,
                                is_active=True
                            )
                            unassigned_tag.is_assigned = True
                            unassigned_tag.save()
                            messages.info(request, f'Auto-attached tag {unassigned_tag.tag_serial_number} to {animal.nickname}.')

                log_action(request.user, 'CREATE_ANIMAL', f'Added animal {animal.nickname} (ID: {animal.animal_id})')
                messages.success(request, f'Animal "{animal.nickname}" added successfully.')
                return redirect('animal_list')
            except Exception as e:
                logger.error(f"Error saving animal: {e}")
                messages.error(request, f'Error saving animal: {str(e)}')
        else:
            messages.error(request, 'Please fix the errors below.')
    else:
        form = AnimalForm(user=request.user)
        # Show preview of next auto-generated ID
        form = AnimalForm(user=request.user, initial={'animal_id': generate_animal_id()})

    return render(request, 'Trace_It/add_animal.html', {'form': form})


@login_required
@admin_required
def edit_animal(request, animal_id):
    animal = get_object_or_404(Animal, animal_id=animal_id)

    if request.method == 'POST':
        form = AnimalForm(request.POST, instance=animal, user=request.user)
        if form.is_valid():
            try:
                animal = form.save()
                log_action(request.user, 'UPDATE_ANIMAL', f'Updated animal {animal.nickname} (ID: {animal.animal_id})')
                messages.success(request, f'Animal "{animal.nickname}" updated successfully.')
                return redirect('animal_list')
            except Exception as e:
                logger.error(f"SAVE ERROR: {e}")
                messages.error(request, f'Error saving: {str(e)}')
        else:
            logger.error(f"FORM ERRORS: {form.errors}")
            messages.error(request, f'Please fix the errors below: {form.errors}')
    else:
        form = AnimalForm(instance=animal, user=request.user)

    return render(request, 'Trace_It/edit_animal.html', {'form': form, 'animal': animal})


@login_required
@admin_required
def delete_animal(request, animal_id):
    animal = get_object_or_404(Animal, animal_id=animal_id)

    if request.method == 'POST':
        try:
            nickname = animal.nickname or f"Animal {animal.animal_id}"

            # Deactivate deployments instead of deleting (keep history)
            deployments = Deployment.objects.filter(animal=animal, is_active=True)
            for dep in deployments:
                dep.is_active = False
                dep.end_date = timezone.now()
                dep.save()
                if dep.tag:
                    dep.tag.is_assigned = False
                    dep.tag.save()

            animal.delete()
            log_action(request.user, 'DELETE_ANIMAL', f'Deleted {nickname} (ID: {animal_id})')
            messages.success(request, f'Animal "{nickname}" deleted successfully.')
            return redirect('animal_list')
        except Exception as e:
            logger.error(f"DELETE ERROR: {e}")
            messages.error(request, f'Could not delete: {str(e)}')
            return redirect('animal_list')

    # GET request - show confirmation page
    return render(request, 'Trace_It/delete_animal.html', {'animal': animal})


@login_required
@admin_required
def animal_list(request):
    animals = Animal.objects.all().select_related('species')
    species_list = Species.objects.all()

    status_filter = request.GET.get('status', '')
    species_filter = request.GET.get('species', '')

    if status_filter:
        animals = animals.filter(health_status__icontains=status_filter)
    if species_filter:
        animals = animals.filter(species_id=species_filter)

    context = {
        'animals': animals,
        'species_list': species_list,
        'status_filter': status_filter,
        'species_filter': species_filter,
    }
    return render(request, 'Trace_It/animal_list.html', context)


@login_required
@admin_required
def tag_list(request):
    tags = TrackingTag.objects.all()
    status_filter = request.GET.get('status', '')

    if status_filter:
        tags = tags.filter(battery_level__lt=20) if status_filter == 'low_battery' else tags

    context = {
        'tags': tags,
        'status_filter': status_filter,
    }
    return render(request, 'Trace_It/tag_list.html', context)


@login_required
@admin_required
def add_tag(request):
    if request.method == 'POST':
        form = TrackingTagForm(request.POST)
        if form.is_valid():
            tag = form.save()
            log_action(request.user, 'CREATE_TAG', f'Created tag {tag.tag_serial_number}')
            messages.success(request, f'Tracking tag "{tag.tag_serial_number}" added successfully.')
            return redirect('tag_list')
    else:
        form = TrackingTagForm()

    return render(request, 'Trace_It/add_tag.html', {'form': form})


@login_required
@admin_required
def assign_tag(request, tag_id):
    tag = get_object_or_404(TrackingTag, tag_id=tag_id)

    if request.method == 'POST':
        animal_id = request.POST.get('animal')
        if animal_id:
            animal = get_object_or_404(Animal, animal_id=animal_id)

            # Deactivate any existing active deployments for this tag and animal
            Deployment.objects.filter(tag=tag, is_active=True).update(is_active=False, end_date=timezone.now())
            Deployment.objects.filter(animal=animal, is_active=True).update(is_active=False, end_date=timezone.now())

            # Create new active deployment
            Deployment.objects.create(
                tag=tag,
                animal=animal,
                is_active=True
            )

            tag.is_assigned = True
            tag.save()

            log_action(request.user, 'ASSIGN_TAG', f'Assigned tag {tag.tag_serial_number} to {animal.nickname}')
            messages.success(request, f'Tag assigned to {animal.nickname}. Animal is now ACTIVE and tracking.')
            return redirect('tag_list')

    assigned_animal_ids = Deployment.objects.filter(is_active=True).values_list('animal_id', flat=True)
    available_animals = Animal.objects.exclude(animal_id__in=assigned_animal_ids)

    context = {
        'tag': tag,
        'available_animals': available_animals,
    }
    return render(request, 'Trace_It/assign_tag.html', context)


@login_required
@ranger_required
def geofence_list(request):
    geofences = Geofence.objects.all()
    return render(request, 'Trace_It/geofence_list.html', {'geofences': geofences})


@login_required
@admin_required
def add_geofence(request):
    if request.method == 'POST':
        form = GeofenceForm(request.POST)
        if form.is_valid():
            try:
                geofence = form.save()
                log_action(request.user, 'CREATE_GEOFENCE', f'Created geofence {geofence.name}')
                messages.success(request, f'Geofence "{geofence.name}" created successfully.')
                return redirect('map_view')
            except Exception as e:
                messages.error(request, f'Error saving geofence: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = GeofenceForm()

    return render(request, 'Trace_It/add_geofence.html', {'form': form})


@login_required
@admin_required
def edit_geofence(request, geofence_id):
    geofence = get_object_or_404(Geofence, geofence_id=geofence_id)

    if request.method == 'POST':
        form = GeofenceForm(request.POST, instance=geofence)
        if form.is_valid():
            try:
                form.save()
                log_action(request.user, 'UPDATE_GEOFENCE', f'Updated geofence {geofence.name}')
                messages.success(request, f'Geofence "{geofence.name}" updated successfully.')
                return redirect('map_view')
            except Exception as e:
                messages.error(request, f'Error updating geofence: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = GeofenceForm(instance=geofence)

    return render(request, 'Trace_It/edit_geofence.html', {'form': form, 'geofence': geofence})


@login_required
@admin_required
def delete_geofence(request, geofence_id):
    geofence = get_object_or_404(Geofence, geofence_id=geofence_id)

    if request.method == 'POST':
        log_action(request.user, 'DELETE_GEOFENCE', f'Deleted geofence {geofence.name}')
        geofence.delete()
        messages.success(request, 'Geofence deleted. Map and dashboard counts updated automatically.')
        return redirect('map_view')

    return render(request, 'Trace_It/delete_geofence.html', {'geofence': geofence})


@login_required
@ranger_required
def alerts(request):
    all_alerts = Alert.objects.all().order_by('-timestamp')
    unresolved_alerts = Alert.objects.filter(is_resolved=False).order_by('-timestamp')
    status_filter = request.GET.get('status', '')

    if status_filter == 'unresolved':
        display_alerts = unresolved_alerts
    elif status_filter == 'resolved':
        display_alerts = all_alerts.filter(is_resolved=True)
    else:
        display_alerts = all_alerts

    context = {
        'alerts': display_alerts,
        'unresolved_alerts': unresolved_alerts,
        'status_filter': status_filter,
    }
    return render(request, 'Trace_It/alerts.html', context)


@login_required
@ranger_required
def resolve_alert(request, alert_id):
    alert = get_object_or_404(Alert, alert_id=alert_id)

    if request.method == 'POST':
        alert.is_resolved = True
        alert.resolved_by = request.user
        alert.resolved_at = timezone.now()
        alert.save()

        log_action(request.user, 'RESOLVE_ALERT', f'Resolved alert {alert.alert_id} for {alert.animal.nickname}')
        messages.success(request, 'Alert resolved.')

    return redirect('alerts')


@login_required
@ranger_required
def location_history(request, animal_id):
    animal = get_object_or_404(Animal, animal_id=animal_id)
    locations = animal.get_all_locations()

    date_from = request.GET.get('from', '')
    date_to = request.GET.get('to', '')

    if date_from:
        locations = locations.filter(timestamp__date__gte=date_from)
    if date_to:
        locations = locations.filter(timestamp__date__lte=date_to)

    context = {
        'animal': animal,
        'locations': locations[:500],
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'Trace_It/location_history.html', context)


@login_required
@ranger_required
def map_view(request):
    """Show ALL animals on the map with proper counts — dynamic center based on actual GPS data."""
    try:
        animals = Animal.objects.all().select_related('species')
        locations_data = []
        animals_with_gps = 0

        for animal in animals:
            try:
                loc = animal.get_latest_location()
                # Exclude sentinel values (-999) which mean no GPS fix from ESP32
                if loc and loc.latitude and loc.longitude and float(loc.latitude) != -999 and float(loc.longitude) != -999:
                    animals_with_gps += 1
                    locations_data.append({
                        'id': animal.animal_id,
                        'nickname': animal.nickname,
                        'species': animal.species.common_name if animal.species else 'Unknown',
                        'latitude': float(loc.latitude),
                        'longitude': float(loc.longitude),
                        'speed': float(loc.speed) if loc.speed else 0,
                        'timestamp': loc.timestamp.strftime('%Y-%m-%d %H:%M:%S') if loc.timestamp else 'N/A',
                        'stationary': animal.is_stationary_minutes(90),
                    })
                # Animals without GPS or with sentinel values are NOT added to locations_data
                # They won't appear on map until ESP32 sends valid GPS data
            except Exception as e:
                logger.error(f"map_view error for animal {animal.animal_id}: {e}")
                continue

        geofences = Geofence.objects.filter(is_active=True)
        demo_geofences = Geofence.objects.filter(name__startswith='Demo Fence').exists()
        locations_json = json.dumps(locations_data)

        context = {
            'locations_data': locations_json,
            'geofences': geofences,
            'demo_geofences': demo_geofences,
            'total_animals': animals.count(),
            'animals_with_gps': animals_with_gps,
        }
        return render(request, 'Trace_It/map_view.html', context)
    except Exception as e:
        logger.error(f"map_view critical error: {e}")
        messages.error(request, f'Map error: {str(e)}')
        return render(request, 'Trace_It/map_view.html', {
            'locations_data': '[]',
            'geofences': [],
            'demo_geofences': False,
            'total_animals': 0,
            'animals_with_gps': 0,
        })


@login_required
@admin_required
def export_locations_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="locations.csv"'

    writer = csv.writer(response)
    writer.writerow(['Animal', 'Species', 'Latitude', 'Longitude', 'Timestamp', 'Temperature', 'Speed'])

    locations = Location.objects.all().select_related('tag').order_by('-timestamp')[:1000]

    for loc in locations:
        deployment = Deployment.objects.filter(tag=loc.tag, is_active=True).first()
        animal = deployment.animal if deployment else None

        writer.writerow([
            animal.nickname if animal else 'Unknown',
            animal.species.common_name if animal and animal.species else 'Unknown',
            loc.latitude,
            loc.longitude,
            loc.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            loc.temperature or 'N/A',
            loc.speed or 'N/A',
        ])

    log_action(request.user, 'EXPORT_CSV', 'Exported location data to CSV')
    return response


# ===== API STATUS TELEMETRY LOOKUP ENGINES =====

def get_tag_latest_data(request, tag_serial):
    """
    Retrieve structured dynamic operational metrics for maps, dashboard charts,
    and asynchronous AJAX frontend updates.
    """
    try:
        tag = TrackingTag.objects.get(tag_serial_number=tag_serial)
    except TrackingTag.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Tag tracking record not registered'}, status=404)

    deployment = Deployment.objects.filter(tag=tag, is_active=True).first()
    animal_name = deployment.animal.nickname if deployment else None
    animal_id = deployment.animal.animal_id if deployment else None

    latest_loc = Location.objects.filter(tag=tag).order_by('-timestamp').first()
    latest_bio = BiometricReading.objects.filter(tag=tag).order_by('-timestamp').first()

    return JsonResponse({
        'status': 'ok',
        'tag_serial': tag.tag_serial_number,
        'battery_level': tag.battery_level,
        'is_assigned': tag.is_assigned,
        'animal_id': animal_id,
        'animal_name': animal_name,
        'latest_location': {
            'lat': float(latest_loc.latitude) if latest_loc else None,
            'lon': float(latest_loc.longitude) if latest_loc else None,
            'timestamp': latest_loc.timestamp.isoformat() if latest_loc else None,
        },
        'latest_biometrics': {
            'heart_rate': latest_bio.heart_rate if latest_bio else None,
            'spo2': latest_bio.spo2 if latest_bio else None,
            'temperature': float(latest_bio.temperature) if latest_bio and latest_bio.temperature else None,
            'timestamp': latest_bio.timestamp.isoformat() if latest_bio else None,
        }
    })


@login_required
@admin_required
def export_alerts_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="alerts.csv"'

    writer = csv.writer(response)
    writer.writerow(['Alert ID', 'Animal', 'Type', 'Severity', 'Message', 'Timestamp', 'Status', 'Resolved By'])

    alerts_list = Alert.objects.all().select_related('animal', 'resolved_by').order_by('-timestamp')[:1000]

    for alert in alerts_list:
        writer.writerow([
            alert.alert_id,
            alert.animal.nickname if alert.animal else 'Unknown',
            alert.alert_type,
            alert.severity,
            alert.message,
            alert.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'Resolved' if alert.is_resolved else 'Unresolved',
            alert.resolved_by.email if alert.resolved_by else 'N/A',
        ])

    log_action(request.user, 'EXPORT_CSV', 'Exported alerts data to CSV')
    return response


@login_required
@admin_required
def export_alerts(request):
    """JSON output mapping for external data visualizations interfaces integration"""
    alerts_list = Alert.objects.filter(is_resolved=False).order_by('-timestamp')[:50]
    data = []
    for a in alerts_list:
        data.append({
            'id': a.alert_id,
            'timestamp': a.timestamp.isoformat(),
            'animal': a.animal.nickname if a.animal else 'Unknown',
            'type': a.alert_type,
            'severity': a.severity,
            'message': a.message
        })
    return JsonResponse(data, safe=False)


@login_required
@admin_required
def audit_log(request):
    """Render system-wide tracking actions and operational logs for compliance auditing."""
    logs = AuditLog.objects.all().select_related('user').order_by('-timestamp')[:500]
    return render(request, 'Trace_It/audit_log.html', {'logs': logs})


@login_required
@admin_required
def manage_users(request):
    """Provide administrative view for managing infrastructure profiles, staff roles, and access controls."""
    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'create_ranger':
            email = request.POST.get('email', '').strip().lower()
            password = request.POST.get('password', '')
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            phone = request.POST.get('phone', '').strip()
            role = request.POST.get('role', 'RANGER')

            if not email or not password:
                messages.error(request, 'Email and password are required.')
                return redirect('manage_users')

            if User.objects.filter(email__iexact=email).exists():
                messages.error(request, 'A user with this email already exists.')
                return redirect('manage_users')

            username = email.split('@')[0]
            base_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1

            try:
                with transaction.atomic():
                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        password=password,
                        first_name=first_name,
                        last_name=last_name
                    )
                    UserProfile.objects.create(user=user, role=role, phone=phone)
                log_action(request.user, 'CREATE_USER', f'Created {role.lower()} account for {email}')
                messages.success(request, f'{role.title()} account for {email} created successfully.')
            except Exception as e:
                messages.error(request, f'Error creating user: {str(e)}')
            return redirect('manage_users')

        elif action == 'edit_ranger':
            user_id = request.POST.get('user_id')
            if not user_id:
                messages.error(request, 'User ID is required.')
                return redirect('manage_users')

            target_user = get_object_or_404(User, pk=user_id)
            email = request.POST.get('email', '').strip().lower()
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            phone = request.POST.get('phone', '').strip()
            password = request.POST.get('password', '')

            if email and email != target_user.email:
                if User.objects.filter(email__iexact=email).exclude(pk=target_user.pk).exists():
                    messages.error(request, 'Another user with this email already exists.')
                    return redirect('manage_users')
                target_user.email = email

            target_user.first_name = first_name
            target_user.last_name = last_name

            if password:
                target_user.password = make_password(password)

            try:
                target_user.save()
                profile = target_user.userprofile
                profile.phone = phone
                profile.save()
                log_action(request.user, 'UPDATE_USER', f'Updated user {target_user.email}')
                messages.success(request, f'User {target_user.email} updated successfully.')
            except Exception as e:
                messages.error(request, f'Error updating user: {str(e)}')
            return redirect('manage_users')

    # Ensure all existing users have a UserProfile before rendering
    for user in User.objects.all():
        UserProfile.objects.get_or_create(
            user=user,
            defaults={'role': 'ADMIN' if user.is_superuser else 'RANGER', 'phone': ''}
        )

    # Use prefetch_related to avoid INNER JOIN filtering out users
    users = User.objects.all().prefetch_related('userprofile').order_by('email')
    return render(request, 'Trace_It/manage_users.html', {'users': users})


@login_required
@admin_required
def create_ranger(request):
    """Handle administrative registration of standard security field team personnel accounts."""
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        phone = request.POST.get('phone', '').strip()

        if not username or not email or not password:
            messages.error(request, 'Missing required parameters inside deployment form.')
            return redirect('manage_users')

        if User.objects.filter(username=username).exists() or User.objects.filter(email=email).exists():
            messages.error(request, 'A user account with this username identity string or email address already exists.')
            return redirect('manage_users')

        try:
            with transaction.atomic():
                user = User.objects.create_user(username=username, email=email, password=password)
                UserProfile.objects.create(user=user, role='RANGER', phone=phone)
            log_action(request.user, 'CREATE_USER', f'Created ranger staff node assignment profile for target email: {email}')
            messages.success(request, f'Ranger access identity account for {email} created successfully.')
        except Exception as e:
            messages.error(request, f'Error generating authenticating user node sequence: {str(e)}')

    return redirect('manage_users')


@login_required
@admin_required
def toggle_user_role(request, user_id):
    """Switch user permissions clearance level between RANGER and ADMIN roles safely."""
    target_user = get_object_or_404(User, pk=user_id)
    if target_user == request.user:
        messages.error(request, 'You cannot modify your own current authorization administrative clearance level loop.')
        return redirect('manage_users')

    try:
        profile = target_user.userprofile
        old_role = profile.role
        new_role = 'ADMIN' if old_role == 'RANGER' else 'RANGER'
        profile.role = new_role
        profile.save()

        log_action(request.user, 'TOGGLE_ROLE', f'Changed active execution clearance role of {target_user.email} from {old_role} to {new_role}')
        messages.success(request, f'Privilege mapping schema schema matrix for {target_user.email} successfully updated to {new_role}.')
    except UserProfile.DoesNotExist:
        messages.error(request, 'Profile schema registration record could not be mapped to the database topology.')

    return redirect('manage_users')


@login_required
@admin_required
def toggle_user_status(request, user_id):
    """Toggle a user's operational active flag status flag to terminate or enable platform access capability."""
    target_user = get_object_or_404(User, pk=user_id)
    if target_user == request.user:
        messages.error(request, 'You cannot trigger a self-termination account lock on your own session context loop.')
        return redirect('manage_users')

    target_user.is_active = not target_user.is_active
    target_user.save()

    status_str = 'activated' if target_user.is_active else 'deactivated'
    log_action(request.user, 'TOGGLE_STATUS', f'Toggled underlying platform profile access code availability of {target_user.email} to state: {status_str}')
    messages.info(request, f'User credential profile identity {target_user.email} has been {status_str} inside system topology.')
    return redirect('manage_users')


@login_required
@admin_required
def setup_demo_geofences(request):
    """Create 10-meter demo geofences around all animals for presentation testing."""
    try:
        animals = Animal.objects.all()
        created_count = 0

        for animal in animals:
            try:
                loc = animal.get_latest_location()
                if loc and loc.latitude and loc.longitude:
                    lat = float(loc.latitude)
                    lon = float(loc.longitude)
                else:
                    # Skip animals without GPS — no demo geofence for them
                    continue

                fence_name = f"Demo Fence - {animal.nickname} (10m)"

                existing = Geofence.objects.filter(name__startswith=f"Demo Fence - {animal.nickname}").first()
                if not existing:
                    Geofence.objects.create(
                        name=fence_name,
                        center_latitude=lat,
                        center_longitude=lon,
                        radius_meters=10,
                        is_active=True,
                    )
                    created_count += 1
                    log_action(request.user, 'CREATE_DEMO_GEOFENCE', 
                              f'Created 10m demo geofence for {animal.nickname} at ({lat}, {lon})')
            except Exception as e:
                logger.error(f"Demo geofence error for {animal.nickname}: {e}")
                continue

        if created_count > 0:
            messages.success(request, f'Created {created_count} demo geofence(s) with 10-meter radius.')
        else:
            messages.info(request, 'No demo geofences created — animals need GPS data first.')
    except Exception as e:
        logger.error(f"setup_demo_geofences error: {e}")
        messages.error(request, f'Error creating demo geofences: {str(e)}')

    return redirect('map_view')


# ===== IoT API ENDPOINTS =====

@csrf_exempt
def iot_ingest(request):
    """Receive GPS + biometric data from ESP32 tracker."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    serial = data.get('tag_serial')
    if not serial:
        return JsonResponse({'status': 'error', 'message': 'Missing tag_serial'}, status=400)

    try:
        tag = TrackingTag.objects.get(tag_serial_number=serial)
    except TrackingTag.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Tag not found'}, status=404)

    deployment = Deployment.objects.filter(tag=tag, is_active=True).first()
    if not deployment:
        return JsonResponse({'status': 'error', 'message': 'Tag not assigned to any animal'}, status=400)

    # Parse GPS coordinates - handle null/missing when no fix
    lat = parse_sentinel(data.get('latitude'))
    lon = parse_sentinel(data.get('longitude'))
    
    location = None
    if lat is not None and lon is not None:
        # Only save location if we have valid GPS data
        try:
            location = Location.objects.create(
                tag=tag,
                latitude=float(lat),
                longitude=float(lon),
                altitude=parse_sentinel(data.get('altitude')),
                speed=parse_sentinel(data.get('speed')),
                temperature=parse_sentinel(data.get('temperature')),
                timestamp=timezone.now(),
            )
        except Exception as e:
            logger.error(f"Location save failed: {e}")
            return JsonResponse({'status': 'error', 'message': f'Location save failed: {str(e)}'}, status=500)
    else:
        logger.info(f"No GPS fix for tag {serial}, skipping location save")

    # Always process biometrics if available
    hr = parse_int_sentinel(data.get('heart_rate'))
    spo2 = parse_int_sentinel(data.get('spo2'))
    body_temp = parse_sentinel(data.get('body_temperature'))
    sensor_status = data.get('sensor_status', 'OK')

    if hr is not None or spo2 is not None or body_temp is not None:
        try:
            BiometricReading.objects.create(
                tag=tag,
                heart_rate=hr,
                spo2=spo2,
                body_temperature=body_temp,
                sensor_status=sensor_status,
                timestamp=timezone.now(),
            )
        except Exception as e:
            logger.error(f"Biometric save failed: {e}")

    # Run checks regardless of location availability
    check_health_alerts(tag, hr, spo2, body_temp, sensor_status)
    if location:
        check_geofence_violations(deployment.animal, location)
    check_stationary_alert(deployment.animal)

    # Update battery level
    new_batt = data.get('battery_level')
    if new_batt is not None:
        try:
            tag.battery_level = int(float(new_batt))
            tag.save(update_fields=['battery_level'])
        except (ValueError, TypeError):
            pass

    return JsonResponse({
        'status': 'ok',
        'location_id': location.location_id if location else None,
        'animal_id': deployment.animal.animal_id,
        'gps_fix': location is not None,
    })


@csrf_exempt
def iot_register(request):
    """Register a new ESP32 tracker tag."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    serial = data.get('tag_serial')
    if not serial:
        return JsonResponse({'status': 'error', 'message': 'Missing tag_serial'}, status=400)

    tag, created = TrackingTag.objects.get_or_create(
        tag_serial_number=serial,
        defaults={
            'model': data.get('model', 'ESP32-GPS'),
            'battery_level': data.get('battery_level', 100),
        }
    )

    status_msg = 'created' if created else 'already_exists'
    return JsonResponse({
        'status': 'ok',
        'tag_id': tag.tag_id,
        'tag_serial': tag.tag_serial_number,
        'state': status_msg,
    })


def iot_status(request, tag_serial):
    """Get current status of a tracker tag."""
    try:
        tag = TrackingTag.objects.get(tag_serial_number=tag_serial)
    except TrackingTag.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Tag not found'}, status=404)

    deployment = Deployment.objects.filter(tag=tag, is_active=True).first()
    animal_name = deployment.animal.nickname if deployment else None
    animal_id = deployment.animal.animal_id if deployment else None

    latest_loc = Location.objects.filter(tag=tag).order_by('-timestamp').first()
    latest_bio = BiometricReading.objects.filter(tag=tag).order_by('-timestamp').first()

    return JsonResponse({
        'status': 'ok',
        'tag_serial': tag.tag_serial_number,
        'battery_level': tag.battery_level,
        'is_assigned': tag.is_assigned,
        'animal_id': animal_id,
        'animal_name': animal_name,
        'latest_location': {
            'lat': float(latest_loc.latitude) if latest_loc else None,
            'lon': float(latest_loc.longitude) if latest_loc else None,
            'timestamp': latest_loc.timestamp.isoformat() if latest_loc else None,
        },
        'latest_biometrics': {
            'heart_rate': latest_bio.heart_rate if latest_bio else None,
            'spo2': latest_bio.spo2 if latest_bio else None,
            'body_temperature': float(latest_bio.body_temperature) if latest_bio and latest_bio.body_temperature else None,
            'sensor_status': latest_bio.sensor_status if latest_bio else None,
        } if latest_bio else None,
    })