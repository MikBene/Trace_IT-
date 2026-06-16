from django.urls import path
from . import views

urlpatterns = [
    # Landing & Home
    path('', views.landing_page, name='landing_page'),
    path('home/', views.index, name='index'),
    
    # Dashboard & Map
    path('dashboard/', views.dashboard, name='dashboard'),
    path('map/', views.map_view, name='map_view'),
    
    # Alerts
    path('alerts/', views.alerts, name='alerts'),
    
    # Animal CRUD
    path('animal/add/', views.add_animal, name='add_animal'),
    path('animal/<str:animal_id>/', views.animal_detail, name='animal_detail'),
    path('animal/<str:animal_id>/edit/', views.edit_animal, name='edit_animal'),
    path('animal/<str:animal_id>/delete/', views.delete_animal, name='delete_animal'),
    path('animal/<str:animal_id>/history/', views.location_history, name='location_history'),
    
    # Tag Management
    path('tag/add/', views.add_tag, name='add_tag'),
    
    # API Endpoints
    path('api/weather/<str:animal_id>/', views.weather_api, name='weather_api'),
    path('api/predict/<str:animal_id>/', views.predict_api, name='predict_api'),
    path('api/vitals-stream/<str:animal_id>/', views.vitals_stream, name='vitals_stream'),
    
    # Authentication
    path('login/admin/', views.admin_login, name='admin_login'),
    path('login/ranger/', views.ranger_login, name='ranger_login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Admin Management
    path('admin/users/', views.manage_users, name='manage_users'),
    path('admin/audit-log/', views.audit_log, name='audit_log'),
]