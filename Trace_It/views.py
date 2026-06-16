from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.contrib.auth.hashers import check_password
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse, StreamingHttpResponse
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.db import models
from .models import Animal, Species, TrackingTag, Deployment, Location, Alert, Geofence, UserProfile, AuditLog, WeatherData, BiometricReading
from .forms import AnimalForm, TrackingTagForm, GeofenceForm
import random
import math
import csv
import requests
import json
import time
import logging
import traceback
logger = logging.getLogger(__name__)


# ===== UTILITY FUNCTIONS =====

def log_action(user, action, details):
    AuditLog.objects.create(user=user, action=action, details=details)


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

    # Sensor error alert
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
        return  # Don't check other vitals if sensor is bad

    # Critical HR
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

    # Low SpO2
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

    # Temperature
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
    if animal.is_stationary(minutes=90):
        latest = animal.get_latest_location()
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
            messages.error(request, 'This account is not authorized as a Ranger.')
            return render(request, 'Trace_It/ranger_login.html')

        login(request, user)
        messages.success(request, f'Welcome back, {user.first_name or user.email}! You are now logged in as Ranger.')
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
    try:
        animals = Animal.objects.all()
        animal_data = []
        
        for animal in animals:
            try:
                latest_location = animal.get_latest_location()
                latest_biometrics = animal.get_latest_biometrics()
                battery_level = None
                if latest_location:
                    tag = latest_location.tag
                    battery_level = tag.battery_level if tag else None

                animal_data.append({
                    'animal': animal,
                    'latest_location': latest_location,
                    'latest_biometrics': latest_biometrics,
                    'battery_level': battery_level,
                    'status': 'Active' if animal.get_latest_location() else 'Inactive',
                    'health_status': animal.health_status,
                })
            except Exception as e:
                print(f"ERROR processing animal {animal.animal_id}: {e}")
                traceback.print_exc()
                # Skip this animal but continue with others
                continue

        context = {
            'animal_data': animal_data,
            'total_animals': len(animals),
        }
        return render(request, 'Trace_It/index.html', context)
    except Exception as e:
        print(f"ERROR in index view: {e}")
        traceback.print_exc()
        raise


@login_required
@ranger_required
def animal_detail(request, animal_id):
    animal = get_object_or_404(Animal, animal_id=animal_id)
    locations = animal.get_all_locations(limit=50)
    latest_biometrics = animal.get_latest_biometrics()

    deployment = animal.deployment_set.filter(is_active=True).first()
    tags = [deployment.tag] if deployment else []

    alerts = Alert.objects.filter(animal=animal).order_by('-timestamp')[:10]
    biometric_history = BiometricReading.objects.filter(
        tag__deployment__animal=animal
    ).order_by('-timestamp')[:50]

    context = {
        'animal': animal,
        'locations': locations,
        'tags': tags,
        'alerts': alerts,
        'latest_biometrics': latest_biometrics,
        'biometric_history': biometric_history,
    }
    return render(request, 'Trace_It/animal_detail.html', context)


@login_required
@admin_required
def dashboard(request):
    total_animals = Animal.objects.count()
    total_tags = TrackingTag.objects.count()
    active_deployments = Deployment.objects.filter(is_active=True).count()
    total_locations = Location.objects.count()
    unresolved_alerts = Alert.objects.filter(is_resolved=False).count()
    recent_alerts = Alert.objects.filter(is_resolved=False).order_by('-timestamp')[:10]
    recent_locations = Location.objects.all().select_related('tag').order_by('-timestamp')[:10]
    recent_logs = AuditLog.objects.all().order_by('-timestamp')[:20]
    low_battery_tags = TrackingTag.objects.filter(battery_level__lt=20).count()

    recent_biometrics = BiometricReading.objects.all().order_by('-timestamp')[:10]
    sensor_errors = BiometricReading.objects.exclude(sensor_status='OK').count()
    critical_health_alerts = Alert.objects.filter(
        alert_type='HEALTH', 
        is_resolved=False,
        severity__in=['HIGH', 'CRITICAL']
    ).count()

    context = {
        'total_animals': total_animals,
        'total_tags': total_tags,
        'active_deployments': active_deployments,
        'total_locations': total_locations,
        'unresolved_alerts': unresolved_alerts,
        'recent_alerts': recent_alerts,
        'recent_locations': recent_locations,
        'recent_logs': recent_logs,
        'low_battery_tags': low_battery_tags,
        'recent_biometrics': recent_biometrics,
        'sensor_errors': sensor_errors,
        'critical_health_alerts': critical_health_alerts,
    }
    return render(request, 'Trace_It/dashboard.html', context)


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
def add_animal(request):
    if request.method == 'POST':
        form = AnimalForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            animal = form.save()
            log_action(request.user, 'CREATE_ANIMAL', f'Created animal {animal.nickname} (ID: {animal.animal_id})')
            messages.success(request, f'Animal "{animal.nickname}" added successfully with ID {animal.animal_id}.')
            return redirect('animal_list')
    else:
        form = AnimalForm(user=request.user)

    return render(request, 'Trace_It/add_animal.html', {'form': form})


@login_required
@admin_required
def edit_animal(request, animal_id):
    animal = get_object_or_404(Animal, animal_id=animal_id)

    if request.method == 'POST':
        try:
            form = AnimalForm(request.POST, request.FILES, instance=animal, user=request.user)
            if form.is_valid():
                try:
                    form.save()
                    log_action(request.user, 'UPDATE_ANIMAL', f'Updated animal {animal.nickname} (ID: {animal.animal_id})')
                    messages.success(request, f'Animal "{animal.nickname}" updated successfully.')
                    return redirect('animal_list')
                except Exception as e:
                    import traceback
                    print(f"ERROR saving animal {animal_id}: {e}")
                    traceback.print_exc()
                    messages.error(request, f'Error saving: {str(e)}')
            else:
                print(f"Form invalid: {form.errors}")
                messages.error(request, 'Please correct the errors below.')
        except Exception as e:
            import traceback
            print(f"ERROR creating form for {animal_id}: {e}")
            traceback.print_exc()
            messages.error(request, f'Form error: {str(e)}')
    else:
        try:
            form = AnimalForm(instance=animal, user=request.user)
        except Exception as e:
            import traceback
            print(f"ERROR loading form for {animal_id}: {e}")
            traceback.print_exc()
            messages.error(request, f'Error loading form: {str(e)}')
            form = None

    return render(request, 'Trace_It/edit_animal.html', {'form': form, 'animal': animal})


@login_required
@admin_required
def delete_animal(request, animal_id):
    animal = get_object_or_404(Animal, animal_id=animal_id)

    if request.method == 'POST':
        # Free up the tag before deleting
        Deployment.objects.filter(animal=animal, is_active=True).update(is_active=False, end_date=timezone.now())

        log_action(request.user, 'DELETE_ANIMAL', f'Deleted animal {animal.nickname} (ID: {animal.animal_id})')
        animal.delete()
        messages.success(request, f'Animal "{animal.nickname}" deleted successfully.')
        return redirect('animal_list')

    return render(request, 'Trace_It/delete_animal.html', {'animal': animal})


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

            # End existing deployment for this tag
            Deployment.objects.filter(tag=tag, is_active=True).update(is_active=False, end_date=timezone.now())

            # End existing deployment for this animal
            Deployment.objects.filter(animal=animal, is_active=True).update(is_active=False, end_date=timezone.now())

            Deployment.objects.create(
                tag=tag,
                animal=animal,
                is_active=True
            )

            tag.is_assigned = True
            tag.save()

            log_action(request.user, 'ASSIGN_TAG', f'Assigned tag {tag.tag_serial_number} to {animal.nickname}')
            messages.success(request, f'Tag assigned to {animal.nickname}.')
            return redirect('tag_list')

    # Only show animals without active tags
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
                return redirect('geofence_list')
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
                return redirect('geofence_list')
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
        messages.success(request, 'Geofence deleted.')
        return redirect('geofence_list')

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
    active_animals = Animal.objects.all()
    animal_locations = []

    for animal in active_animals:
        loc = animal.get_latest_location()
        if loc:
            animal_locations.append({
                'animal': animal,
                'location': loc,
            })

    geofences = Geofence.objects.filter(is_active=True)

    context = {
        'animal_locations': animal_locations,
        'geofences': geofences,
    }
    return render(request, 'Trace_It/map_view.html', context)


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


@login_required
@admin_required
def export_alerts_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="alerts.csv"'

    writer = csv.writer(response)
    writer.writerow(['Animal', 'Alert Type', 'Message', 'Created At', 'Resolved', 'Resolved By', 'Resolved At'])

    alerts = Alert.objects.all().select_related('animal', 'resolved_by').order_by('-timestamp')

    for alert in alerts:
        writer.writerow([
            alert.animal.nickname if alert.animal else 'N/A',
            alert.alert_type,
            alert.message,
            alert.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'Yes' if alert.is_resolved else 'No',
            alert.resolved_by.email if alert.resolved_by else 'N/A',
            alert.resolved_at.strftime('%Y-%m-%d %H:%M:%S') if alert.resolved_at else 'N/A',
        ])

    log_action(request.user, 'EXPORT_ALERTS_CSV', 'Exported alerts to CSV')
    return response


@login_required
@admin_required
def audit_log(request):
    logs = AuditLog.objects.all().order_by('-timestamp')
    user_filter = request.GET.get('user', '')
    action_filter = request.GET.get('action', '')

    if user_filter:
        logs = logs.filter(user__email__icontains=user_filter)
    if action_filter:
        logs = logs.filter(action__icontains=action_filter)

    context = {
        'logs': logs[:200],
        'user_filter': user_filter,
        'action_filter': action_filter,
    }
    return render(request, 'Trace_It/audit_log.html', context)


@login_required
@admin_required
def manage_users(request):
    if request.method == 'POST' and request.POST.get('action') == 'edit_ranger':
        user_id = request.POST.get('user_id')
        if user_id:
            try:
                user = User.objects.get(id=user_id)
                profile = user.userprofile

                user_role = profile.role
                role_label = 'Admin' if user_role == 'ADMIN' else 'Ranger'

                email = request.POST.get('email', '').strip().lower()
                first_name = request.POST.get('first_name', '').strip()
                last_name = request.POST.get('last_name', '').strip()
                phone = request.POST.get('phone', '').strip()
                new_password = request.POST.get('password', '')

                if not email:
                    messages.error(request, f"Email is required for {role_label.lower()} {user.email}.")
                elif '@' not in email or '.' not in email.split('@')[-1]:
                    messages.error(request, f"Please enter a valid email address for {role_label.lower()} {user.email}.")
                elif email != user.email and User.objects.filter(email__iexact=email).exists():
                    messages.error(request, f"A user with email '{email}' already exists.")
                else:
                    old_email = user.email
                    user.email = email
                    user.username = email
                    user.first_name = first_name
                    user.last_name = last_name
                    user.save()

                    profile.phone = phone
                    profile.save()

                    if new_password and len(new_password) >= 6:
                        user.set_password(new_password)
                        user.save()
                        messages.info(request, f"Password for {role_label} {email} updated successfully.")

                    log_action(request.user, 'UPDATE_USER', f'Updated {role_label.lower()} {old_email} -> {email}')
                    messages.success(request, f'{role_label} {email} updated successfully!')

            except User.DoesNotExist:
                messages.error(request, "User not found.")
            except Exception as e:
                messages.error(request, f'Error updating user: {str(e)}')

        return redirect('manage_users')

    if request.method == 'POST' and request.POST.get('action') == 'change_role':
        user_id = request.POST.get('user_id')
        if user_id:
            try:
                user = User.objects.get(id=user_id)
                profile = user.userprofile
                old_role = profile.role
                new_role = request.POST.get('role')

                if new_role in ['ADMIN', 'RANGER']:
                    profile.role = new_role
                    profile.save()

                    old_label = 'Admin' if old_role == 'ADMIN' else 'Ranger'
                    new_label = 'Admin' if new_role == 'ADMIN' else 'Ranger'

                    log_action(request.user, 'CHANGE_ROLE', f'Changed {user.email} from {old_label} to {new_label}')
                    messages.success(request, f'{old_label} {user.email} is now a {new_label}!')

            except User.DoesNotExist:
                messages.error(request, "User not found.")
            except Exception as e:
                messages.error(request, f'Error changing role: {str(e)}')

        return redirect('manage_users')

    if request.method == 'POST' and request.POST.get('action') == 'delete_user':
        user_id = request.POST.get('user_id')
        if user_id:
            try:
                user = User.objects.get(id=user_id)
                profile = user.userprofile
                role_label = 'Admin' if profile.role == 'ADMIN' else 'Ranger'
                user_email = user.email

                profile.delete()
                user.delete()

                log_action(request.user, 'DELETE_USER', f'Deleted {role_label.lower()} {user_email}')
                messages.success(request, f'{role_label} {user_email} has been deleted successfully.')

            except User.DoesNotExist:
                messages.error(request, "User not found.")
            except Exception as e:
                messages.error(request, f'Error deleting user: {str(e)}')

        return redirect('manage_users')

    edit_user_id = None
    if request.method == 'GET':
        edit_user_id = request.GET.get('edit')
        if edit_user_id:
            try:
                edit_user_id = int(edit_user_id)
            except ValueError:
                edit_user_id = None

    users = User.objects.all().select_related('userprofile')

    total_users = users.count()
    admin_count = sum(1 for u in users if u.userprofile.role == 'ADMIN')
    ranger_count = sum(1 for u in users if u.userprofile.role == 'RANGER')
    active_count = sum(1 for u in users if u.is_active)

    return render(request, 'Trace_It/create_ranger.html', {
        'users': users,
        'total_users': total_users,
        'admin_count': admin_count,
        'ranger_count': ranger_count,
        'active_count': active_count,
        'edit_user_id': edit_user_id,
    })


@login_required
@admin_required
def create_ranger(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        password = request.POST.get('password', '')
        phone = request.POST.get('phone', '').strip()

        errors = []

        if not email:
            errors.append("Email is required.")
        elif '@' not in email or '.' not in email.split('@')[-1]:
            errors.append("Please enter a valid email address (e.g., name@example.com).")

        if not password:
            errors.append("Password is required.")
        elif len(password) < 6:
            errors.append("Password must be at least 6 characters long.")

        if User.objects.filter(email__iexact=email).exists():
            errors.append(f"A user with email '{email}' already exists.")

        if User.objects.filter(username__iexact=email).exists():
            errors.append(f"A user with username '{email}' already exists.")

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'Trace_It/create_ranger.html')

        try:
            user = User.objects.create_user(
                username=email,
                email=email,
                first_name=first_name,
                last_name=last_name,
                password=password
            )

            UserProfile.objects.create(
                user=user,
                role='RANGER',
                phone=phone
            )

            log_action(request.user, 'CREATE_RANGER', f'Created ranger account for {email}')
            messages.success(request, f'Ranger account for {email} created successfully!')
            return redirect('manage_users')

        except Exception as e:
            messages.error(request, f'Error creating ranger: {str(e)}')
            return render(request, 'Trace_It/create_ranger.html')

    return render(request, 'Trace_It/create_ranger.html')


@login_required
@admin_required
def toggle_user_status(request, user_id):
    user = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        try:
            profile = user.userprofile
            profile.delete()
        except UserProfile.DoesNotExist:
            pass

        user_email = user.email
        user.delete()

        log_action(request.user, 'DELETE_USER', f'Deleted user {user_email}')
        messages.success(request, f'User {user_email} has been deleted successfully.')

    return redirect('manage_users')


@login_required
@admin_required
def toggle_user_role(request, user_id):
    user = get_object_or_404(User, id=user_id)
    profile = user.userprofile

    if request.method == 'POST':
        new_role = request.POST.get('role')
        if new_role in ['ADMIN', 'RANGER']:
            old_role = profile.role
            profile.role = new_role
            profile.save()
            log_action(request.user, 'CHANGE_ROLE', f'Changed {user.email} from {old_role} to {new_role}')
            messages.success(request, f'Role updated for {user.email} from {old_role} to {new_role}.')

    return redirect('manage_users')


@login_required
@ranger_required
def weather_data(request, animal_id):
    animal = get_object_or_404(Animal, animal_id=animal_id)
    latest_loc = animal.get_latest_location()

    weather = None
    if latest_loc:
        try:
            weather = WeatherData.objects.filter(location=latest_loc).latest('timestamp')
        except WeatherData.DoesNotExist:
            pass

    context = {
        'animal': animal,
        'latest_location': latest_loc,
        'weather': weather,
    }
    return render(request, 'Trace_It/weather_data.html', context)


@login_required
@ranger_required
def predict_location(request, animal_id):
    animal = get_object_or_404(Animal, animal_id=animal_id)
    locations = animal.get_all_locations(limit=100)

    prediction = None
    loc_list = list(locations)
    if len(loc_list) >= 2:
        recent = loc_list[:10]
        if len(recent) >= 2:
            avg_lat_change = sum(
                float(recent[i].latitude) - float(recent[i+1].latitude)
                for i in range(len(recent)-1)
            ) / (len(recent)-1)
            avg_lon_change = sum(
                float(recent[i].longitude) - float(recent[i+1].longitude)
                for i in range(len(recent)-1)
            ) / (len(recent)-1)

            latest = recent[0]
            prediction = {
                'predicted_latitude': float(latest.latitude) + avg_lat_change,
                'predicted_longitude': float(latest.longitude) + avg_lon_change,
                'confidence': min(len(loc_list) / 100.0, 0.95),
            }

    context = {
        'animal': animal,
        'prediction': prediction,
        'location_count': len(loc_list),
    }
    return render(request, 'Trace_It/ml_prediction.html', context)


@login_required
@admin_required
def edit_ranger(request, user_id):
    user = get_object_or_404(User, id=user_id)
    profile = get_object_or_404(UserProfile, user=user)

    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        new_password = request.POST.get('password', '')

        errors = []

        if not email:
            errors.append("Email is required.")
        elif '@' not in email or '.' not in email.split('@')[-1]:
            errors.append("Please enter a valid email address.")
        elif email != user.email and User.objects.filter(email__iexact=email).exists():
            errors.append(f"A user with email '{email}' already exists.")

        if errors:
            for error in errors:
                messages.error(request, error)
            return redirect('manage_users')

        try:
            old_email = user.email
            user.email = email
            user.username = email
            user.first_name = first_name
            user.last_name = last_name
            user.save()

            profile.phone = phone
            profile.save()

            if new_password and len(new_password) >= 6:
                user.set_password(new_password)
                user.save()
                messages.info(request, "Password updated successfully.")

            log_action(request.user, 'UPDATE_RANGER', f'Updated ranger {old_email} -> {email}')
            messages.success(request, f'Ranger {email} updated successfully!')

        except Exception as e:
            messages.error(request, f'Error updating ranger: {str(e)}')

    return redirect('manage_users')


@login_required
@admin_required
def simulate_gps_data(request):
    if request.method == 'POST':
        animal_id = request.POST.get('animal')
        num_points = int(request.POST.get('num_points', 10))

        animal = get_object_or_404(Animal, animal_id=animal_id)
        latest = animal.get_latest_location()

        deployment = animal.deployment_set.filter(is_active=True).first()
        if not deployment:
            messages.error(request, 'No active tag deployed on this animal.')
            return redirect('simulate_gps')

        tag = deployment.tag
        base_lat = float(latest.latitude) if latest else 0.0
        base_lon = float(latest.longitude) if latest else 0.0

        for i in range(num_points):
            lat_offset = random.uniform(-0.01, 0.01)
            lon_offset = random.uniform(-0.01, 0.01)

            new_lat = base_lat + lat_offset
            new_lon = base_lon + lon_offset

            battery = max(0, 100 - (i * 2) - random.randint(0, 5))
            temperature = random.uniform(15.0, 35.0)
            speed = random.uniform(0.0, 15.0)

            location = Location.objects.create(
                tag=tag,
                latitude=new_lat,
                longitude=new_lon,
                temperature=temperature,
                speed=speed,
            )

            tag.battery_level = battery
            tag.save()

            check_geofence_violations(animal, location)
            check_stationary_alert(animal)

            base_lat = new_lat
            base_lon = new_lon

        log_action(request.user, 'GPS_SIMULATION', f'Generated {num_points} simulated points for {animal.nickname}')
        messages.success(request, f'Generated {num_points} simulated GPS points for {animal.nickname}.')
        return redirect('map_view')

    animals = Animal.objects.all()
    return render(request, 'Trace_It/gps_simulation.html', {'animals': animals})


# ===== API ENDPOINTS =====

@login_required
@admin_required
def api_location_update(request):
    if request.method == 'POST':
        tag_serial = request.POST.get('tag_serial_number')
        latitude = request.POST.get('latitude')
        longitude = request.POST.get('longitude')
        battery = request.POST.get('battery_level')
        temperature = request.POST.get('temperature')
        speed = request.POST.get('speed')

        if not all([tag_serial, latitude, longitude]):
            return JsonResponse({'status': 'error', 'message': 'Missing required fields'}, status=400)

        try:
            tag = TrackingTag.objects.get(tag_serial_number=tag_serial)
            location = Location.objects.create(
                tag=tag,
                latitude=float(latitude),
                longitude=float(longitude),
                temperature=temperature,
                speed=speed,
            )

            if battery:
                tag.battery_level = float(battery)
                tag.save()

            deployment = Deployment.objects.filter(tag=tag, is_active=True).first()
            if deployment:
                check_geofence_violations(deployment.animal, location)
                check_stationary_alert(deployment.animal)

            return JsonResponse({'status': 'success', 'location_id': location.location_id})
        except TrackingTag.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Tag not found'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)


@csrf_exempt
def api_biometric_update(request):
    """Main IoT endpoint - receives all sensor data from ESP32 hardware securely via JSON."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'POST only allowed'}, status=405)

    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST

        tag_serial = data.get('tag_serial') or data.get('tag_serial_number')
        lat = data.get('lat') or data.get('latitude')
        lon = data.get('lon') or data.get('longitude')

        if not tag_serial or lat is None or lon is None:
            return JsonResponse({
                'status': 'error', 
                'message': 'Missing required fields: tag_serial, lat, lon'
            }, status=400)

        tag = TrackingTag.objects.get(tag_serial_number=tag_serial)

        # Explicit conversion safely handled via float definitions
        location = Location.objects.create(
            tag=tag,
            latitude=float(lat),
            longitude=float(lon),
            altitude=parse_sentinel(data.get('altitude')),
            temperature=parse_sentinel(data.get('temp')) or parse_sentinel(data.get('temperature')),
            speed=parse_sentinel(data.get('speed')),
        )

        hr = parse_int_sentinel(data.get('hr')) or parse_int_sentinel(data.get('heart_rate'))
        spo2 = parse_sentinel(data.get('spo2'))
        body_temp = parse_sentinel(data.get('body_temp')) or parse_sentinel(data.get('body_temperature'))
        accel_x = parse_int_sentinel(data.get('acc_x')) or parse_int_sentinel(data.get('accel_x'))
        accel_y = parse_int_sentinel(data.get('acc_y')) or parse_int_sentinel(data.get('accel_y'))
        accel_z = parse_int_sentinel(data.get('acc_z')) or parse_int_sentinel(data.get('accel_z'))

        # Update device tracking hardware power levels directly from hardware transmission if present
        battery = data.get('battery') or data.get('battery_level')
        if battery is not None:
            tag.battery_level = float(battery)
            tag.save()

        sensor_status = 'OK'
        if hr is None and spo2 is None and body_temp is None:
            sensor_status = 'ALL_SENSORS_DISCONNECTED'
        elif hr is None:
            sensor_status = 'HR_SENSOR_DISCONNECTED'
        elif spo2 is None:
            sensor_status = 'SPO2_SENSOR_DISCONNECTED'
        elif body_temp is None:
            sensor_status = 'TEMP_SENSOR_DISCONNECTED'

        bio = BiometricReading.objects.create(
            tag=tag,
            location=location,
            heart_rate_bpm=hr,
            spo2_percent=spo2,
            body_temperature_c=body_temp,
            accel_x=accel_x,
            accel_y=accel_y,
            accel_z=accel_z,
            sensor_status=sensor_status,
        )

        check_health_alerts(tag, hr, spo2, body_temp, sensor_status)

        deployment = Deployment.objects.filter(tag=tag, is_active=True).first()
        if deployment:
            check_geofence_violations(deployment.animal, location)
            check_stationary_alert(deployment.animal)

        return JsonResponse({
            'status': 'success',
            'location_id': location.location_id,
            'reading_id': bio.reading_id,
            'sensor_status': sensor_status,
        })


    except TrackingTag.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Tag not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON format'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def api_animal_status(request, animal_id):
    animal = get_object_or_404(Animal, animal_id=animal_id)
    latest = animal.get_latest_location()
    latest_bio = animal.get_latest_biometrics()

    battery = None
    if latest:
        deployment = animal.deployment_set.filter(is_active=True).first()
        if deployment:
            battery = deployment.tag.battery_level

    data = {
        'id': animal.animal_id,
        'name': animal.nickname,
        'status': 'Active' if latest else 'Inactive',
        'health_status': animal.health_status,
        'latest_location': {
            'latitude': float(latest.latitude) if latest else None,
            'longitude': float(latest.longitude) if latest else None,
            'timestamp': latest.timestamp.isoformat() if latest else None,
            'battery': float(battery) if battery else None,
        } if latest else None,
        'biometrics': {
            'heart_rate': latest_bio.heart_rate_bpm if latest_bio else None,
            'spo2': float(latest_bio.spo2_percent) if latest_bio and latest_bio.spo2_percent else None,
            'body_temp': float(latest_bio.body_temperature_c) if latest_bio and latest_bio.body_temperature_c else None,
            'accel_x': latest_bio.accel_x if latest_bio else None,
            'accel_y': latest_bio.accel_y if latest_bio else None,
            'accel_z': latest_bio.accel_z if latest_bio else None,
            'sensor_status': latest_bio.sensor_status if latest_bio else None,
        } if latest_bio else None,
    }
    return JsonResponse(data)


@login_required
def api_locations(request, animal_id):
    animal = get_object_or_404(Animal, animal_id=animal_id)
    locations = animal.get_all_locations(limit=100)

    data = [
        {
            'latitude': float(loc.latitude),
            'longitude': float(loc.longitude),
            'timestamp': loc.timestamp.isoformat(),
            'temperature': float(loc.temperature) if loc.temperature else None,
            'speed': float(loc.speed) if loc.speed else None,
        }
        for loc in locations
    ]
    return JsonResponse({'locations': data})


@login_required
def get_weather(request, animal_id):
    animal = get_object_or_404(Animal, animal_id=animal_id)
    latest = animal.get_latest_location()

    weather = None
    if latest:
        try:
            weather = WeatherData.objects.filter(location=latest).latest('timestamp')
        except WeatherData.DoesNotExist:
            pass

    if weather:
        data = {
            'temperature': float(weather.temperature),
            'humidity': weather.humidity,
            'wind_speed': float(weather.wind_speed),
            'conditions': weather.description,
            'recorded_at': weather.timestamp.isoformat(),
        }
    else:
        data = {'error': 'No weather data available'}

    return JsonResponse(data)


@login_required
def api_prediction_json(request, animal_id):
    animal = get_object_or_404(Animal, animal_id=animal_id)
    locations = animal.get_all_locations(limit=100)

    prediction = None
    loc_list = list(locations)
    if len(loc_list) >= 2:
        recent = loc_list[:10]
        if len(recent) >= 2:
            avg_lat_change = sum(
                float(recent[i].latitude) - float(recent[i+1].latitude)
                for i in range(len(recent)-1)
            ) / (len(recent)-1)
            avg_lon_change = sum(
                float(recent[i].longitude) - float(recent[i+1].longitude)
                for i in range(len(recent)-1)
            ) / (len(recent)-1)

            latest = recent[0]
            prediction = {
                'predicted_latitude': float(latest.latitude) + avg_lat_change,
                'predicted_longitude': float(latest.longitude) + avg_lon_change,
                'confidence': min(len(loc_list) / 100.0, 0.95),
                'based_on_points': len(loc_list),
            }

    return JsonResponse({'prediction': prediction})


# ===== SSE STREAMING =====

@login_required
def vitals_stream(request, animal_id):
    animal = get_object_or_404(Animal, animal_id=animal_id)

    def event_stream():
        last_reading_id = None
        while True:
            try:
                latest = BiometricReading.objects.filter(
                    tag__deployment__animal=animal
                ).order_by('-timestamp').first()

                if latest and latest.reading_id != last_reading_id:
                    last_reading_id = latest.reading_id
                    payload = json.dumps({
                        'hr': latest.heart_rate_bpm,
                        'spo2': float(latest.spo2_percent) if latest.spo2_percent else None,
                        'temp': float(latest.body_temperature_c) if latest.body_temperature_c else None,
                        'accel_x': latest.accel_x,
                        'accel_y': latest.accel_y,
                        'accel_z': latest.accel_z,
                        'sensor_status': latest.sensor_status,
                        'timestamp': latest.timestamp.isoformat(),
                    })
                    yield f"data: {payload}\n\n"

                time.sleep(2)

            except Exception:
                time.sleep(2)
                continue

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response