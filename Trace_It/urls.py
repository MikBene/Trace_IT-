from django.urls import path
from . import views

urlpatterns = [
    # Landing & Auth
    path('', views.landing_page, name='landing_page'),
    path('ranger/login/', views.ranger_login, name='ranger_login'),
    path('admin/login/', views.admin_login, name='admin_login'),
    path('logout/', views.logout_view, name='logout'),

    # Main Pages
    path('index/', views.index, name='index'),
    path('dashboard/', views.dashboard, name='dashboard'),

    # Animals
    path('animal/<int:animal_id>/', views.animal_detail, name='animal_detail'),
    path('animal/add/', views.add_animal, name='add_animal'),
    path('animal/<int:animal_id>/edit/', views.edit_animal, name='edit_animal'),
    path('animal/<int:animal_id>/delete/', views.delete_animal, name='delete_animal'),
    path('animals/', views.animal_list, name='animal_list'),

    # Location History
    path('animal/<int:animal_id>/history/', views.location_history, name='location_history'),

    # Map
    path('map/', views.map_view, name='map_view'),

    # Tags
    path('tags/', views.tag_list, name='tag_list'),
    path('tag/add/', views.add_tag, name='add_tag'),
    path('tag/<int:tag_id>/assign/', views.assign_tag, name='assign_tag'),

    # Geofences
    path('geofences/', views.geofence_list, name='geofence_list'),
    path('geofence/add/', views.add_geofence, name='add_geofence'),
    path('geofence/<int:geofence_id>/edit/', views.edit_geofence, name='edit_geofence'),
    path('geofence/<int:geofence_id>/delete/', views.delete_geofence, name='delete_geofence'),

    # Alerts
    path('alerts/', views.alerts, name='alerts'),
    path('alert/<int:alert_id>/resolve/', views.resolve_alert, name='resolve_alert'),

    # Export - both old and new names for compatibility
    path('export/locations/', views.export_locations_csv, name='export_locations_csv'),
    path('export/alerts/', views.export_alerts_csv, name='export_alerts_csv'),
    # Alias for templates that use old name
    path('export/locations/', views.export_locations_csv, name='export_locations'),
    path('export/alerts/', views.export_alerts_csv, name='export_alerts'),

    # Audit Log
    path('audit-log/', views.audit_log, name='audit_log'),

    # Users
    path('users/', views.manage_users, name='manage_users'),

    # IoT API Endpoints
    path('api/iot/ingest/', views.iot_ingest, name='iot_ingest'),
    path('api/iot/register/', views.iot_register, name='iot_register'),
    path('api/iot/status/<str:tag_serial>/', views.iot_status, name='iot_status'),
    path('run-migrations/', views.run_migrations),
]