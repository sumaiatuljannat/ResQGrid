"""
Forms for ResQGrid Authentication, Incident Reporting, and Resource Management
"""

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from core.models import (
    UserProfile, ResponderProfile, UserRole,
    Incident, EmergencyType, AccessDifficulty,
    Shelter, ShelterAllocation, AvailabilityStatus, Resource
)

# Available standard rescue skills & equipment choices
SKILL_CHOICES = [
    ('FIRST_AID', 'First Aid & Trauma Care'),
    ('WATER_RESCUE', 'Water & Flood Rescue'),
    ('FIRE_FIGHTING', 'Fire Fighting & Suppression'),
    ('SEARCH_RESCUE', 'Urban Search & Rescue (USAR)'),
    ('MEDICAL_DOCTOR', 'Emergency Medicine / Physician'),
    ('HEAVY_LIFTING', 'Heavy Debris Clearing & Lifting'),
    ('EVACUATION_LOGISTICS', 'Evacuation & Crowd Logistics'),
]

EQUIPMENT_CHOICES = [
    ('AMBULANCE', 'Emergency Ambulance / Patient Transport'),
    ('RESCUE_BOAT', 'Inflatable Boat / Motorized Rescue Craft'),
    ('FIRE_PUMP', 'Water Pump / Fire Extinguishing Rig'),
    ('FIRST_AID_KIT', 'Comprehensive Trauma & First Aid Kit'),
    ('DRONE', 'Aerial Reconnaissance Drone'),
    ('HYDRAULIC_CUTTER', 'Hydraulic Jaws of Life / Cutters'),
    ('EMERGENCY_VAN', 'Evacuation Transport Van / 4WD Truck'),
    ('STRETCHERS', 'Spine Boards & Emergency Stretchers'),
]


def _validate_registration_password(form, cleaned_data):
    password = cleaned_data.get('password')
    if not password:
        return

    user = User(
        username=cleaned_data.get('username', ''),
        first_name=cleaned_data.get('first_name', ''),
        last_name=cleaned_data.get('last_name', ''),
        email=cleaned_data.get('email', ''),
    )
    try:
        validate_password(password, user)
    except DjangoValidationError as error:
        form.add_error('password', error)


class CitizenRegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Create strong password'}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm password'}))
    phone = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+880 1XXX-XXXXXX'}))
    address = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'City, District'}))

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Choose username'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'name@example.com'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password')
        p2 = cleaned_data.get('confirm_password')
        if p1 and p2 and p1 != p2:
            self.add_error('confirm_password', 'Passwords do not match.')
        _validate_registration_password(self, cleaned_data)
        return cleaned_data


class ResponderRegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Create password'}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm password'}))
    phone = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+880 1XXX-XXXXXX'}))
    organization = forms.CharField(max_length=150, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Bangladesh Red Crescent, Fire Service Volunteer, Civil Defense'}))

    # Skills & Equipment Multiple Selection
    skills_selected = forms.MultipleChoiceField(
        choices=SKILL_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=True,
        label="Certified Rescue Skills"
    )
    equipment_selected = forms.MultipleChoiceField(
        choices=EQUIPMENT_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=True,
        label="Available Ready Equipment"
    )

    service_area_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Dhaka Central / Chittagong Port Area'}))
    latitude = forms.FloatField(min_value=-90, max_value=90, initial=23.8103, widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001', 'id': 'id_latitude'}))
    longitude = forms.FloatField(min_value=-180, max_value=180, initial=90.4125, widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001', 'id': 'id_longitude'}))
    service_radius_km = forms.FloatField(min_value=0.1, initial=25.0, widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '1.0', 'min': '0.1'}))
    max_active_capacity = forms.IntegerField(initial=2, min_value=1, max_value=10, widget=forms.NumberInput(attrs={'class': 'form-control'}))

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'name@example.com'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password')
        p2 = cleaned_data.get('confirm_password')
        if p1 and p2 and p1 != p2:
            self.add_error('confirm_password', 'Passwords do not match.')
        _validate_registration_password(self, cleaned_data)
        return cleaned_data


class IncidentReportForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['affected_count'].min_value = 1
        self.fields['affected_count'].widget.attrs['min'] = '1'

    class Meta:
        model = Incident
        fields = [
            'reported_for', 'victim_name', 'contact_name', 'contact_phone',
            'emergency_type', 'description', 'immediate_threat_to_life',
            'affected_count', 'injured_count', 'trapped_count',
            'has_vulnerable_people', 'vulnerable_details', 'access_difficulty',
            'location_name', 'latitude', 'longitude', 'is_gps_derived'
        ]
        widgets = {
            'reported_for': forms.Select(attrs={'class': 'form-select', 'id': 'id_reported_for'}),
            'victim_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Name of person/family in distress (if reporting for others)', 'id': 'id_victim_name'}),
            'contact_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Primary contact person on scene'}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+880 1XXX-XXXXXX'}),
            'emergency_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Describe immediate danger, hazards, landmarks, water level, smoke, etc.'}),
            'immediate_threat_to_life': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'affected_count': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'injured_count': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'trapped_count': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'has_vulnerable_people': forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'id_has_vulnerable'}),
            'vulnerable_details': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 2 infants, 1 wheelchair-bound elder', 'id': 'id_vulnerable_details'}),
            'access_difficulty': forms.Select(attrs={'class': 'form-select'}),
            'location_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Sector 4, Uttara, Dhaka / Near Agrabad Fire Station'}),
            'latitude': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001', 'id': 'id_latitude'}),
            'longitude': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001', 'id': 'id_longitude'}),
            'is_gps_derived': forms.HiddenInput(),
        }

    def clean(self):
        cleaned_data = super().clean()
        reported_for = cleaned_data.get('reported_for')
        victim_name = cleaned_data.get('victim_name')
        if reported_for == 'OTHER' and not victim_name:
            self.add_error('victim_name', 'Please provide the name or identity of the person you are reporting for.')

        affected = cleaned_data.get('affected_count') or 0
        injured = cleaned_data.get('injured_count') or 0
        trapped = cleaned_data.get('trapped_count') or 0
        if injured > affected:
            self.add_error('injured_count', 'Injured count cannot exceed total affected count.')
        if trapped > affected:
            self.add_error('trapped_count', 'Trapped count cannot exceed total affected count.')
        latitude = cleaned_data.get('latitude')
        longitude = cleaned_data.get('longitude')
        if latitude is not None and not -90 <= latitude <= 90:
            self.add_error('latitude', 'Latitude must be between -90 and 90 degrees.')
        if longitude is not None and not -180 <= longitude <= 180:
            self.add_error('longitude', 'Longitude must be between -180 and 180 degrees.')
        return cleaned_data


class ShelterAllocationForm(forms.ModelForm):
    class Meta:
        model = ShelterAllocation
        fields = ['shelter', 'incident', 'person_name', 'family_count', 'contact_phone', 'notes']
        widgets = {
            'shelter': forms.Select(attrs={'class': 'form-select'}),
            'incident': forms.Select(attrs={'class': 'form-select'}),
            'person_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Family head or individual name'}),
            'family_count': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'value': '1'}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+880 1XXX-XXXXXX'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Medical needs, dietary requirements, infant care...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['incident'].required = False
        self.fields['incident'].empty_label = "-- None / Independent Evacuees --"
        self.fields['family_count'].min_value = 1
        self.fields['family_count'].widget.attrs['min'] = '1'

    def clean_family_count(self):
        family_count = self.cleaned_data['family_count']
        if family_count < 1:
            raise forms.ValidationError('At least one person must be allocated.')
        return family_count


class IncidentNoteForm(forms.Form):
    note = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Provide on-scene status update, rising water observation, or victim status...'}),
        required=True,
        label="Operational Update / Note"
    )


class ResponderAvailabilityForm(forms.ModelForm):
    class Meta:
        model = ResponderProfile
        fields = ['availability']
        widgets = {
            'availability': forms.Select(attrs={'class': 'form-select'}),
        }


class ResourceForm(forms.ModelForm):
    class Meta:
        model = Resource
        fields = ['name', 'category', 'quantity', 'unit', 'location_name', 'latitude', 'longitude', 'shelter', 'status']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'unit': forms.TextInput(attrs={'class': 'form-control'}),
            'location_name': forms.TextInput(attrs={'class': 'form-control'}),
            'latitude': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
            'longitude': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
            'shelter': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean_quantity(self):
        quantity = self.cleaned_data['quantity']
        if quantity < 0:
            raise forms.ValidationError('Resource quantity cannot be negative.')
        return quantity


class ShelterForm(forms.ModelForm):
    class Meta:
        model = Shelter
        fields = [
            'name', 'address', 'latitude', 'longitude', 'total_capacity',
            'occupied_capacity', 'has_food', 'has_water', 'has_medical',
            'status', 'contact_person', 'contact_phone',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
            'latitude': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
            'longitude': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
            'total_capacity': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'occupied_capacity': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'has_food': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'has_water': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'has_medical': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        total = cleaned_data.get('total_capacity')
        occupied = cleaned_data.get('occupied_capacity')
        if total is not None and occupied is not None and occupied > total:
            self.add_error('occupied_capacity', 'Occupied capacity cannot exceed total capacity.')
        return cleaned_data
