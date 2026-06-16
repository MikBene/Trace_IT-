from django.urls import path
from . import views

urlpatterns = [
    # Landing & Auth
    path('', views.landing_page, name='landing_page'),
    path('login/ranger/', views.ranger_login, name='ranger_login'),
    path('login/admin/', views.admin_login, name='admin_login'),
    path('logout/', views.logout_view, name='logout'),

    # Home / Dashboard
    path('home/', views.index, name='index'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('animal/<str:animal_id>/delete/', views.delete_animal, name='delete_animal'),

    # Animals - FIXED: animal_id is CharField (str), not int
    path('animal/<str:animal_id>/', views.animal_detail, name='animal_detail'),
    path('animal/<str:animal_id>/history/', views.location_history, name='location_history'),
    path('animal/<str:animal_id>/weather/', views.weather_data, name='weather_data'),
    path('animal/<str:animal_id>/predict/', views.predict_location, name='predict_location'),
    path('animals/', views.animal_list, name='animal_list'),
    path('add-animal/', views.add_animal, name='add_animal'),
    path('animal/<str:animal_id>/edit/', views.edit_animal, name='edit_animal'),
    path('animal/<str:animal_id>/delete/', views.delete_animal, name='delete_animal'),

    # Tags
    path('tags/', views.tag_list, name='tag_list'),
    path('add-tag/', views.add_tag, name='add_tag'),
    path('tag/<int:tag_id>/assign/', views.assign_tag, name='assign_tag'),

    # Geofences
    path('geofences/', views.geofence_list, name='geofence_list'),
    path('add-geofence/', views.add_geofence, name='add_geofence'),
    path('geofence/<int:geofence_id>/edit/', views.edit_geofence, name='edit_geofence'),
    path('geofence/<int:geofence_id>/delete/', views.delete_geofence, name='delete_geofence'),

    # Alerts
    path('alerts/', views.alerts, name='alerts'),
    path('alert/<int:alert_id>/resolve/', views.resolve_alert, name='resolve_alert'),

    # Map
    path('map/', views.map_view, name='map_view'),

    # GPS Simulation
    path('simulate-gps/', views.simulate_gps_data, name='simulate_gps'),

    # API Endpoints - FIXED: animal_id is CharField (str)
    path('api/location-update/', views.api_location_update, name='api_location_update'),
    path('api/biometric-update/', views.api_biometric_update, name='api_biometric_update'),
    path('api/animal-status/<str:animal_id>/', views.api_animal_status, name='api_animal_status'),
    path('api/locations/<str:animal_id>/', views.api_locations, name='api_locations'),
    path('api/weather/<str:animal_id>/', views.get_weather, name='get_weather'),
    path('api/predict/<str:animal_id>/', views.api_prediction_json, name='api_prediction_json'),
    path('api/vitals-stream/<str:animal_id>/', views.vitals_stream, name='vitals_stream'),

    # Admin / User Management
    path('admin/users/', views.manage_users, name='manage_users'),
    path('admin/create-ranger/', views.create_ranger, name='create_ranger'),
    path('admin/toggle-user/<int:user_id>/', views.toggle_user_status, name='toggle_user_status'),
    path('admin/toggle-role/<int:user_id>/', views.toggle_user_role, name='toggle_user_role'),
    path('admin/audit-log/', views.audit_log, name='audit_log'),

    # Exports
    path('export/locations/', views.export_locations_csv, name='export_locations'),
    path('export/alerts/', views.export_alerts_csv, name='export_alerts'),
]