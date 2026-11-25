"""
Django Admin Configuration for ResQGrid
"""

from django.contrib import admin
from core.models import (
    UserProfile, ResponderProfile, Incident,
    Assignment, IncidentEvent, Shelter, ShelterAllocation, Resource
)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'phone', 'organization', 'is_verified', 'created_at')
    list_filter = ('role', 'is_verified')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'phone', 'organization')


@admin.register(ResponderProfile)
class ResponderProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'verification_status', 'availability', 'skills', 'equipment', 'service_area_name', 'current_active_assignments', 'max_active_capacity')
    list_filter = ('verification_status', 'availability')
    search_fields = ('user__username', 'service_area_name', 'skills', 'equipment')


class AssignmentInline(admin.TabularInline):
    model = Assignment
    extra = 0
    readonly_fields = ('assigned_at', 'responded_at')


class IncidentEventInline(admin.TabularInline):
    model = IncidentEvent
    extra = 0
    readonly_fields = ('timestamp',)


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ('incident_id', 'emergency_type', 'priority_level', 'priority_score', 'status', 'location_name', 'assigned_responder', 'created_at')
    list_filter = ('status', 'priority_level', 'emergency_type', 'immediate_threat_to_life')
    search_fields = ('incident_id', 'location_name', 'description', 'contact_name', 'contact_phone')
    inlines = [AssignmentInline, IncidentEventInline]


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'incident', 'responder', 'status', 'match_score', 'assigned_at', 'responded_at')
    list_filter = ('status',)
    search_fields = ('incident__incident_id', 'responder__username')


@admin.register(IncidentEvent)
class IncidentEventAdmin(admin.ModelAdmin):
    list_display = ('incident', 'event_type', 'from_status', 'to_status', 'actor', 'timestamp')
    list_filter = ('event_type',)
    search_fields = ('incident__incident_id', 'description')


@admin.register(Shelter)
class ShelterAdmin(admin.ModelAdmin):
    list_display = ('name', 'address', 'total_capacity', 'occupied_capacity', 'status', 'has_food', 'has_water', 'has_medical')
    list_filter = ('status', 'has_food', 'has_water', 'has_medical')
    search_fields = ('name', 'address', 'contact_person')


@admin.register(ShelterAllocation)
class ShelterAllocationAdmin(admin.ModelAdmin):
    list_display = ('person_name', 'family_count', 'shelter', 'allocated_by', 'allocated_at', 'is_active')
    list_filter = ('is_active', 'shelter')
    search_fields = ('person_name', 'shelter__name', 'contact_phone')


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'quantity', 'unit', 'location_name', 'shelter', 'status')
    list_filter = ('category', 'status')
    search_fields = ('name', 'location_name')
