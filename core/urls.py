"""
URL Configuration for Core Application
"""

from django.urls import path
from django.contrib.auth import views as auth_views
from core import views

urlpatterns = [
    # Public & Auth
    path('', views.home_view, name='home'),
    path('health/', views.health_check_view, name='health_check'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('password/change/', auth_views.PasswordChangeView.as_view(
        template_name='core/password_change.html',
        success_url='/password/change/done/',
    ), name='password_change'),
    path('password/change/done/', auth_views.PasswordChangeDoneView.as_view(
        template_name='core/password_change_done.html',
    ), name='password_change_done'),
    path('register/citizen/', views.register_citizen_view, name='register_citizen'),
    path('register/responder/', views.register_responder_view, name='register_responder'),

    # Dashboards
    path('dashboard/', views.dashboard_router_view, name='dashboard'),
    path('dashboard/admin/', views.admin_dashboard_view, name='admin_dashboard'),
    path('dashboard/citizen/', views.citizen_dashboard_view, name='citizen_dashboard'),
    path('dashboard/responder/', views.responder_dashboard_view, name='responder_dashboard'),

    # Incidents
    path('incidents/', views.incident_list_view, name='incident_list'),
    path('incidents/report/', views.incident_create_view, name='incident_create'),
    path('incidents/<str:incident_id>/', views.incident_detail_view, name='incident_detail'),
    path('incidents/<str:incident_id>/update-status/', views.incident_update_status_view, name='incident_update_status'),
    path('incidents/<str:incident_id>/note/', views.incident_post_note_view, name='incident_post_note'),
    path('incidents/<str:incident_id>/re-triage/', views.incident_retrigger_triage_view, name='incident_retrigger_triage'),
    path('incidents/<str:incident_id>/manual-dispatch/', views.manual_dispatch_view, name='manual_dispatch'),

    # Responder Workflow Actions
    path('assignments/<int:assignment_id>/accept/', views.assignment_accept_view, name='assignment_accept'),
    path('assignments/<int:assignment_id>/reject/', views.assignment_reject_view, name='assignment_reject'),
    path('responder/toggle-availability/', views.responder_toggle_availability_view, name='responder_toggle_availability'),
    path('responder/<int:responder_id>/verify/', views.admin_verify_responder_view, name='admin_verify_responder'),

    # Map & Shelters
    path('map/', views.map_view, name='map_view'),
    path('map/data/', views.map_data_view, name='map_data'),
    path('shelters/', views.shelter_list_view, name='shelter_list'),
    path('shelters/create/', views.shelter_create_view, name='shelter_create'),
    path('shelters/<int:shelter_id>/edit/', views.shelter_edit_view, name='shelter_edit'),
    path('shelters/allocate/', views.shelter_allocate_view, name='shelter_allocate'),
    path('resources/', views.resource_list_view, name='resource_list'),
    path('resources/create/', views.resource_create_view, name='resource_create'),
    path('resources/<int:resource_id>/edit/', views.resource_edit_view, name='resource_edit'),
    path('resources/<int:resource_id>/update-status/', views.resource_update_status_view, name='resource_update_status'),
    path('resources/<int:resource_id>/adjust/', views.resource_adjust_quantity_view, name='resource_adjust_quantity'),

    # API Analytics
    path('api/stats/', views.api_incident_stats, name='api_incident_stats'),
    path('api/my-incidents/status/', views.api_my_incident_status, name='api_my_incident_status'),
]
