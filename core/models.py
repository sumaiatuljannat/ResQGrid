"""
Database Models for ResQGrid
Intelligent Emergency Response & Humanitarian Coordination Network
"""

import math
import uuid
from django.db import models, transaction
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError


# ---------------------------------------------------------
# User Profiles & Roles
# ---------------------------------------------------------

class UserRole(models.TextChoices):
    ADMIN = 'ADMIN', 'Administrator'
    CITIZEN = 'CITIZEN', 'Citizen'
    RESPONDER = 'RESPONDER', 'Emergency Responder'
    RESOURCE_MANAGER = 'RESOURCE_MANAGER', 'Resource Manager'


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.CITIZEN)
    phone = models.CharField(max_length=30, blank=True, default='')
    organization = models.CharField(max_length=150, blank=True, default='')
    address = models.CharField(max_length=255, blank=True, default='')
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"


class VerificationStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending Verification'
    VERIFIED = 'VERIFIED', 'Verified'
    REJECTED = 'REJECTED', 'Rejected'


class AvailabilityStatus(models.TextChoices):
    AVAILABLE = 'AVAILABLE', 'Available for Dispatch'
    BUSY = 'BUSY', 'Busy on Response'
    OFFLINE = 'OFFLINE', 'Offline / Off Duty'


class ResponderProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='responder_profile')
    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING
    )
    availability = models.CharField(
        max_length=20,
        choices=AvailabilityStatus.choices,
        default=AvailabilityStatus.AVAILABLE
    )

    # Skills and Equipment stored as comma-separated tags or JSON
    # Common Skills: FIRST_AID, WATER_RESCUE, FIRE_FIGHTING, SEARCH_RESCUE, MEDICAL_DOCTOR, HEAVY_LIFTING, EVACUATION_LOGISTICS
    skills = models.CharField(
        max_length=255,
        default='FIRST_AID',
        help_text='Comma-separated skills (e.g. FIRST_AID, WATER_RESCUE, FIRE_FIGHTING)'
    )
    # Common Equipment: AMBULANCE, RESCUE_BOAT, FIRE_PUMP, FIRST_AID_KIT, DRONE, HYDRAULIC_CUTTER, EMERGENCY_VAN
    equipment = models.CharField(
        max_length=255,
        default='FIRST_AID_KIT',
        help_text='Comma-separated equipment (e.g. AMBULANCE, RESCUE_BOAT, FIRST_AID_KIT)'
    )

    service_area_name = models.CharField(max_length=150, default='Dhaka Metro')
    latitude = models.FloatField(default=23.8103, help_text='Current base latitude')
    longitude = models.FloatField(default=90.4125, help_text='Current base longitude')
    service_radius_km = models.FloatField(default=30.0, help_text='Service coverage radius in km')

    max_active_capacity = models.PositiveIntegerField(default=2, help_text='Max simultaneous active assignments')
    current_active_assignments = models.PositiveIntegerField(default=0)

    notes = models.TextField(blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(service_radius_km__gte=0),
                name='responder_radius_nonnegative',
            ),
            models.CheckConstraint(
                condition=models.Q(max_active_capacity__gte=1),
                name='responder_capacity_positive',
            ),
            models.CheckConstraint(
                condition=models.Q(current_active_assignments__gte=0),
                name='responder_active_assignments_nonnegative',
            ),
            models.CheckConstraint(
                condition=models.Q(latitude__gte=-90, latitude__lte=90),
                name='responder_valid_latitude',
            ),
            models.CheckConstraint(
                condition=models.Q(longitude__gte=-180, longitude__lte=180),
                name='responder_valid_longitude',
            ),
        ]

    def __str__(self):
        return f"Responder: {self.user.get_full_name() or self.user.username} [{self.get_verification_status_display()}]"

    def get_skills_list(self):
        if not self.skills:
            return []
        return [s.strip().upper() for s in self.skills.split(',') if s.strip()]

    def get_equipment_list(self):
        if not self.equipment:
            return []
        return [e.strip().upper() for e in self.equipment.split(',') if e.strip()]

    def has_skills(self, required_skills):
        """Returns True if this responder has all required skills."""
        if not required_skills:
            return True
        my_skills = set(self.get_skills_list())
        return all(req.upper() in my_skills for req in required_skills)

    def has_equipment(self, required_equipment):
        """Returns True if this responder has all required equipment."""
        if not required_equipment:
            return True
        my_equip = set(self.get_equipment_list())
        return all(req.upper() in my_equip for req in required_equipment)

    def can_accept_assignment(self):
        """Checks verification, availability, and capacity."""
        if self.verification_status != VerificationStatus.VERIFIED:
            return False, "Responder is not verified by Admin."
        if self.availability != AvailabilityStatus.AVAILABLE:
            return False, f"Responder status is {self.get_availability_display()}."
        if self.current_active_assignments >= self.max_active_capacity:
            return False, f"Responder has reached maximum concurrent capacity ({self.max_active_capacity})."
        return True, "Eligible"

    def distance_to(self, lat, lon):
        """Calculates approximate distance in km using Haversine formula."""
        if lat is None or lon is None:
            return 9999.0
        r = 6371.0  # Earth radius in kilometers
        d_lat = math.radians(lat - self.latitude)
        d_lon = math.radians(lon - self.longitude)
        a = (math.sin(d_lat / 2) ** 2 +
             math.cos(math.radians(self.latitude)) * math.cos(math.radians(lat)) *
             math.sin(d_lon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return round(r * c, 2)


# ---------------------------------------------------------
# Incidents & Priority Engine Output
# ---------------------------------------------------------

class EmergencyType(models.TextChoices):
    FLOOD = 'FLOOD', 'Flood / Water Inundation'
    FIRE = 'FIRE', 'Fire Emergency'
    EARTHQUAKE = 'EARTHQUAKE', 'Earthquake / Collapse'
    MEDICAL = 'MEDICAL', 'Critical Medical Emergency'
    BUILDING_COLLAPSE = 'BUILDING_COLLAPSE', 'Building Collapse / Trapped'
    CYCLONE = 'CYCLONE', 'Cyclone / Storm Surge'
    TRAFFIC_ACCIDENT = 'TRAFFIC_ACCIDENT', 'Major Traffic / Vehicle Accident'
    OTHER = 'OTHER', 'Other Emergency'


class PriorityLevel(models.TextChoices):
    CRITICAL = 'CRITICAL', 'Critical Priority (Immediate Dispatch)'
    HIGH = 'HIGH', 'High Priority'
    MEDIUM = 'MEDIUM', 'Medium Priority'
    LOW = 'LOW', 'Low Priority'


class IncidentStatus(models.TextChoices):
    REPORTED = 'REPORTED', 'Reported'
    TRIAGED = 'TRIAGED', 'Triaged'
    ASSIGNED = 'ASSIGNED', 'Assigned'
    ACCEPTED = 'ACCEPTED', 'Accepted'
    RESPONDING = 'RESPONDING', 'Responding'
    RESOLVED = 'RESOLVED', 'Resolved'
    CANCELLED = 'CANCELLED', 'Cancelled'
    UNASSIGNED = 'UNASSIGNED', 'Unassigned / Needs Attention'


class AccessDifficulty(models.TextChoices):
    EASY = 'EASY', 'Paved Roads / Easy Vehicle Access'
    MODERATE = 'MODERATE', 'Narrow Roads / Partial Flooding'
    DIFFICULT = 'DIFFICULT', 'Deep Water / Blocked Debris / Hill Track'
    INACCESSIBLE = 'INACCESSIBLE', 'Cut Off / Boat or Aerial Only'


class Incident(models.Model):
    incident_id = models.CharField(max_length=30, unique=True, editable=False)
    reporter = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='reported_incidents')

    # Reporting Mode
    reported_for = models.CharField(
        max_length=10,
        choices=[('SELF', 'Reporting for Myself'), ('OTHER', 'Reporting for Someone Else')],
        default='SELF'
    )
    victim_name = models.CharField(max_length=150, blank=True, default='')
    contact_name = models.CharField(max_length=150)
    contact_phone = models.CharField(max_length=30)

    # Emergency Information
    emergency_type = models.CharField(max_length=30, choices=EmergencyType.choices, default=EmergencyType.OTHER)
    description = models.TextField()

    # Severity & Vulnerability Indicators
    immediate_threat_to_life = models.BooleanField(default=False, help_text='Is there an active, life-threatening danger?')
    affected_count = models.PositiveIntegerField(default=1, help_text='Number of people affected')
    injured_count = models.PositiveIntegerField(default=0, help_text='Number of people injured')
    trapped_count = models.PositiveIntegerField(default=0, help_text='Number of people physically trapped')
    has_vulnerable_people = models.BooleanField(default=False, help_text='Are there infants, elderly, pregnant, or disabled individuals?')
    vulnerable_details = models.CharField(max_length=255, blank=True, default='')
    access_difficulty = models.CharField(
        max_length=20,
        choices=AccessDifficulty.choices,
        default=AccessDifficulty.EASY
    )

    # Location
    location_name = models.CharField(max_length=255, help_text='Street address, landmark, or district name')
    latitude = models.FloatField(default=23.8103)
    longitude = models.FloatField(default=90.4125)
    is_gps_derived = models.BooleanField(default=False)

    # Priority Engine Evaluation (Module B)
    priority_score = models.FloatField(default=0.0)
    priority_level = models.CharField(max_length=20, choices=PriorityLevel.choices, default=PriorityLevel.MEDIUM)
    priority_explanation = models.TextField(blank=True, default='')

    # Status and State Management (Module A & D)
    status = models.CharField(max_length=20, choices=IncidentStatus.choices, default=IncidentStatus.REPORTED)
    unassigned_reason = models.TextField(blank=True, default='')

    # Assigned Responder
    assigned_responder = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='active_incident_missions'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(affected_count__gte=1),
                name='incident_affected_count_positive',
            ),
            models.CheckConstraint(
                condition=models.Q(injured_count__lte=models.F('affected_count')),
                name='incident_injured_within_affected',
            ),
            models.CheckConstraint(
                condition=models.Q(trapped_count__lte=models.F('affected_count')),
                name='incident_trapped_within_affected',
            ),
            models.CheckConstraint(
                condition=models.Q(latitude__gte=-90, latitude__lte=90),
                name='incident_valid_latitude',
            ),
            models.CheckConstraint(
                condition=models.Q(longitude__gte=-180, longitude__lte=180),
                name='incident_valid_longitude',
            ),
        ]

    def clean(self):
        super().clean()
        if self.affected_count < 1:
            raise ValidationError({'affected_count': 'Affected count must be at least 1.'})
        if self.injured_count > self.affected_count:
            raise ValidationError({'injured_count': 'Injured count cannot exceed affected count.'})
        if self.trapped_count > self.affected_count:
            raise ValidationError({'trapped_count': 'Trapped count cannot exceed affected count.'})
        if not -90 <= self.latitude <= 90:
            raise ValidationError({'latitude': 'Latitude must be between -90 and 90.'})
        if not -180 <= self.longitude <= 180:
            raise ValidationError({'longitude': 'Longitude must be between -180 and 180.'})

    def save(self, *args, **kwargs):
        if not self.incident_id:
            # Generate human-readable unique identifier e.g. RSQ-20261122-8A2F
            date_str = timezone.now().strftime('%Y%m%d')
            rand_suffix = uuid.uuid4().hex[:4].upper()
            self.incident_id = f"RSQ-{date_str}-{rand_suffix}"
            while Incident.objects.filter(incident_id=self.incident_id).exists():
                rand_suffix = uuid.uuid4().hex[:4].upper()
                self.incident_id = f"RSQ-{date_str}-{rand_suffix}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.incident_id}] {self.get_emergency_type_display()} - {self.get_priority_level_display()}"

    @property
    def waiting_time_minutes(self):
        """Returns minutes elapsed since report."""
        now = timezone.now()
        delta = now - self.created_at
        return max(0, int(delta.total_seconds() // 60))

    def get_required_skills(self):
        """Map emergency type to mandatory rescue skills."""
        skill_map = {
            EmergencyType.FLOOD: ['WATER_RESCUE'],
            EmergencyType.FIRE: ['FIRE_FIGHTING'],
            EmergencyType.MEDICAL: ['FIRST_AID'],
            EmergencyType.BUILDING_COLLAPSE: ['SEARCH_RESCUE'],
            EmergencyType.CYCLONE: ['EVACUATION_LOGISTICS'],
            EmergencyType.EARTHQUAKE: ['SEARCH_RESCUE'],
            EmergencyType.TRAFFIC_ACCIDENT: ['FIRST_AID'],
            EmergencyType.OTHER: ['FIRST_AID'],
        }
        skills = skill_map.get(self.emergency_type, ['FIRST_AID']).copy()
        if self.injured_count > 0 and 'FIRST_AID' not in skills:
            skills.append('FIRST_AID')
        if self.trapped_count > 0 and 'SEARCH_RESCUE' not in skills:
            skills.append('SEARCH_RESCUE')
        return skills

    def get_required_equipment(self):
        """Map emergency type and severity to mandatory responder equipment."""
        equip_map = {
            EmergencyType.FLOOD: ['RESCUE_BOAT'],
            EmergencyType.FIRE: ['FIRE_PUMP'],
            EmergencyType.MEDICAL: ['AMBULANCE'],
            EmergencyType.BUILDING_COLLAPSE: ['HYDRAULIC_CUTTER'],
            EmergencyType.CYCLONE: ['EMERGENCY_VAN'],
            EmergencyType.EARTHQUAKE: ['HYDRAULIC_CUTTER'],
            EmergencyType.TRAFFIC_ACCIDENT: ['AMBULANCE'],
            EmergencyType.OTHER: ['FIRST_AID_KIT'],
        }
        equipment = equip_map.get(self.emergency_type, ['FIRST_AID_KIT']).copy()
        if self.injured_count >= 3 and 'AMBULANCE' not in equipment:
            equipment.append('AMBULANCE')
        if self.access_difficulty in [AccessDifficulty.DIFFICULT, AccessDifficulty.INACCESSIBLE] and self.emergency_type == EmergencyType.FLOOD:
            if 'RESCUE_BOAT' not in equipment:
                equipment.append('RESCUE_BOAT')
        return equipment

    def validate_transition(self, target_status):
        """
        Validates legal state machine transitions.
        REPORTED -> TRIAGED -> ASSIGNED -> ACCEPTED -> RESPONDING -> RESOLVED
        Allowing transitions to CANCELLED and UNASSIGNED.
        """
        valid_transitions = {
            IncidentStatus.REPORTED: [IncidentStatus.TRIAGED, IncidentStatus.ASSIGNED, IncidentStatus.UNASSIGNED, IncidentStatus.CANCELLED],
            IncidentStatus.TRIAGED: [IncidentStatus.ASSIGNED, IncidentStatus.UNASSIGNED, IncidentStatus.CANCELLED],
            IncidentStatus.ASSIGNED: [IncidentStatus.ACCEPTED, IncidentStatus.UNASSIGNED, IncidentStatus.CANCELLED],
            IncidentStatus.ACCEPTED: [IncidentStatus.RESPONDING, IncidentStatus.UNASSIGNED, IncidentStatus.CANCELLED],
            IncidentStatus.RESPONDING: [IncidentStatus.RESOLVED, IncidentStatus.CANCELLED],
            IncidentStatus.UNASSIGNED: [IncidentStatus.ASSIGNED, IncidentStatus.TRIAGED, IncidentStatus.CANCELLED],
            IncidentStatus.RESOLVED: [],  # Terminal
            IncidentStatus.CANCELLED: [], # Terminal
        }
        allowed = valid_transitions.get(self.status, [])
        if target_status not in allowed:
            raise ValidationError(f"Invalid status transition from {self.status} to {target_status}.")
        return True


# ---------------------------------------------------------
# Assignments & Automated Workflow (Module C & D)
# ---------------------------------------------------------

class AssignmentStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending Responder Acceptance'
    ACCEPTED = 'ACCEPTED', 'Accepted by Responder'
    REJECTED = 'REJECTED', 'Rejected by Responder'
    COMPLETED = 'COMPLETED', 'Mission Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class Assignment(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name='assignments')
    responder = models.ForeignKey(User, on_delete=models.CASCADE, related_name='responder_assignments')
    assigned_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='dispatched_assignments')

    status = models.CharField(max_length=20, choices=AssignmentStatus.choices, default=AssignmentStatus.PENDING)
    match_score = models.FloatField(default=0.0)
    match_explanation = models.TextField(blank=True, default='')
    rejection_reason = models.TextField(blank=True, default='')

    assigned_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-assigned_at']
        constraints = [
            models.UniqueConstraint(
                fields=['incident'],
                condition=models.Q(status__in=[
                    AssignmentStatus.PENDING,
                    AssignmentStatus.ACCEPTED,
                ]),
                name='one_active_assignment_per_incident',
            ),
        ]

    def __str__(self):
        return f"Assignment {self.id}: {self.responder.username} -> {self.incident.incident_id} ({self.status})"


# ---------------------------------------------------------
# Event Audit Log (Module D)
# ---------------------------------------------------------

class EventType(models.TextChoices):
    CREATED = 'CREATED', 'Incident Created'
    TRIAGED = 'TRIAGED', 'Priority Calculated & Triaged'
    MATCH_SEARCH = 'MATCH_SEARCH', 'Responder Match Searched'
    ASSIGNED = 'ASSIGNED', 'Assigned to Responder'
    ACCEPTED = 'ACCEPTED', 'Assignment Accepted'
    REJECTED = 'REJECTED', 'Assignment Rejected'
    AUTO_REASSIGNED = 'AUTO_REASSIGNED', 'Automatically Reassigned to Next Eligible Responder'
    UNASSIGNED_ALERT = 'UNASSIGNED_ALERT', 'Marked Unassigned - No Responder Available'
    STATUS_UPDATE = 'STATUS_UPDATE', 'Status Updated'
    RESOLVED = 'RESOLVED', 'Incident Resolved'
    CANCELLED = 'CANCELLED', 'Incident Cancelled'
    SHELTER_ALLOCATED = 'SHELTER_ALLOCATED', 'Shelter Capacity Allocated'


class IncidentEvent(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name='events')
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='incident_actions')
    event_type = models.CharField(max_length=30, choices=EventType.choices, default=EventType.STATUS_UPDATE)
    from_status = models.CharField(max_length=30, blank=True, default='')
    to_status = models.CharField(max_length=30, blank=True, default='')
    description = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"[{self.timestamp.strftime('%H:%M:%S')}] {self.incident.incident_id}: {self.event_type} - {self.description[:40]}"


# ---------------------------------------------------------
# Shelter & Resource Management (Module E)
# ---------------------------------------------------------

class ShelterStatus(models.TextChoices):
    OPEN = 'OPEN', 'Open & Accepting Evacuees'
    FULL = 'FULL', 'At Maximum Capacity'
    CLOSED = 'CLOSED', 'Temporarily Closed / Inactive'


class Shelter(models.Model):
    name = models.CharField(max_length=150)
    address = models.CharField(max_length=255)
    latitude = models.FloatField(default=23.8103)
    longitude = models.FloatField(default=90.4125)

    total_capacity = models.PositiveIntegerField(help_text='Total maximum individual shelter capacity')
    occupied_capacity = models.PositiveIntegerField(default=0)

    has_food = models.BooleanField(default=True)
    has_water = models.BooleanField(default=True)
    has_medical = models.BooleanField(default=True)

    status = models.CharField(max_length=20, choices=ShelterStatus.choices, default=ShelterStatus.OPEN)
    contact_person = models.CharField(max_length=150, default='Shelter Manager')
    contact_phone = models.CharField(max_length=30, default='+8801700000000')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(total_capacity__gte=0),
                name='shelter_total_capacity_nonnegative',
            ),
            models.CheckConstraint(
                condition=models.Q(occupied_capacity__gte=0),
                name='shelter_occupied_capacity_nonnegative',
            ),
            models.CheckConstraint(
                condition=models.Q(occupied_capacity__lte=models.F('total_capacity')),
                name='shelter_occupied_within_total',
            ),
            models.CheckConstraint(
                condition=models.Q(latitude__gte=-90, latitude__lte=90),
                name='shelter_valid_latitude',
            ),
            models.CheckConstraint(
                condition=models.Q(longitude__gte=-180, longitude__lte=180),
                name='shelter_valid_longitude',
            ),
        ]

    def clean(self):
        super().clean()
        if self.occupied_capacity > self.total_capacity:
            raise ValidationError({'occupied_capacity': 'Occupied capacity cannot exceed total capacity.'})

    def __str__(self):
        return f"{self.name} ({self.available_capacity}/{self.total_capacity} spots free)"

    @property
    def available_capacity(self):
        return max(0, self.total_capacity - self.occupied_capacity)

    @property
    def occupancy_percentage(self):
        if self.total_capacity == 0:
            return 100
        return min(100, int((self.occupied_capacity / self.total_capacity) * 100))

    def can_accommodate(self, count):
        return (self.occupied_capacity + count) <= self.total_capacity and self.status != ShelterStatus.CLOSED

    @transaction.atomic
    def allocate_people(self, count):
        """Safely updates shelter occupancy with DB row locking."""
        # Refresh with lock
        shelter = Shelter.objects.select_for_update().get(id=self.id)
        if shelter.status == ShelterStatus.CLOSED:
            raise ValidationError(f"Shelter '{shelter.name}' is closed.")
        if (shelter.occupied_capacity + count) > shelter.total_capacity:
            raise ValidationError(
                f"Cannot allocate {count} people. Shelter '{shelter.name}' only has {shelter.available_capacity} free spots (Total: {shelter.total_capacity}, Occupied: {shelter.occupied_capacity})."
            )
        shelter.occupied_capacity += count
        if shelter.occupied_capacity >= shelter.total_capacity:
            shelter.status = ShelterStatus.FULL
        shelter.save()
        self.occupied_capacity = shelter.occupied_capacity
        self.status = shelter.status
        return shelter.occupied_capacity


class ShelterAllocation(models.Model):
    shelter = models.ForeignKey(Shelter, on_delete=models.CASCADE, related_name='allocations')
    incident = models.ForeignKey(Incident, null=True, blank=True, on_delete=models.SET_NULL, related_name='shelter_allocations')
    allocated_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shelter_allocations_made')

    person_name = models.CharField(max_length=150, help_text='Head of household or individual name')
    family_count = models.PositiveIntegerField(default=1, help_text='Number of people in this party')
    contact_phone = models.CharField(max_length=30, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    allocated_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(family_count__gte=1),
                name='shelter_allocation_positive_family_count',
            ),
        ]

    def __str__(self):
        return f"{self.person_name} ({self.family_count} persons) -> {self.shelter.name}"


class ResourceCategory(models.TextChoices):
    FOOD = 'FOOD', 'Food & Rations'
    WATER = 'WATER', 'Drinking Water & Purification'
    MEDICAL_SUPPLIES = 'MEDICAL_SUPPLIES', 'Medical Supplies & First Aid'
    RESCUE_EQUIPMENT = 'RESCUE_EQUIPMENT', 'Rescue Equipment'
    BLANKETS_CLOTHING = 'BLANKETS_CLOTHING', 'Blankets & Emergency Clothing'
    OTHER = 'OTHER', 'Other Relief Items'


class ResourceStatus(models.TextChoices):
    AVAILABLE = 'AVAILABLE', 'Available'
    RESERVED = 'RESERVED', 'Reserved'
    DEPLETED = 'DEPLETED', 'Depleted'


class Resource(models.Model):
    name = models.CharField(max_length=150)
    category = models.CharField(max_length=30, choices=ResourceCategory.choices, default=ResourceCategory.FOOD)
    quantity = models.PositiveIntegerField(default=100)
    unit = models.CharField(max_length=50, default='Units')
    location_name = models.CharField(max_length=150, default='Central Warehouse')
    latitude = models.FloatField(default=23.8103)
    longitude = models.FloatField(default=90.4125)
    shelter = models.ForeignKey(Shelter, null=True, blank=True, on_delete=models.SET_NULL, related_name='resources')
    status = models.CharField(max_length=20, choices=ResourceStatus.choices, default=ResourceStatus.AVAILABLE)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=0),
                name='resource_quantity_nonnegative',
            ),
            models.CheckConstraint(
                condition=models.Q(latitude__gte=-90, latitude__lte=90),
                name='resource_valid_latitude',
            ),
            models.CheckConstraint(
                condition=models.Q(longitude__gte=-180, longitude__lte=180),
                name='resource_valid_longitude',
            ),
        ]

    def __str__(self):
        return f"{self.name}: {self.quantity} {self.unit} ({self.get_status_display()})"
