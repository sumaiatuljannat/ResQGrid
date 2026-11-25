"""
Management Command: seed_demo_data
Populates database with realistic, clearly labeled fictional simulation data for Bangladesh
and sets up demonstration scenarios for Hackathon evaluation.
"""

import os
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from core.models import (
    UserProfile, ResponderProfile, UserRole, VerificationStatus, AvailabilityStatus,
    Incident, EmergencyType, PriorityLevel, IncidentStatus, AccessDifficulty,
    Assignment, AssignmentStatus, IncidentEvent, EventType,
    Shelter, ShelterAllocation, ShelterStatus, Resource, ResourceCategory, ResourceStatus
)
from core.engines.priority_engine import PriorityEngine
from core.engines.matching_engine import MatchingEngine
from core.engines.workflow_engine import WorkflowEngine


class Command(BaseCommand):
    help = "Seeds database with fictional demonstration data for ResQGrid"

    def add_arguments(self, parser):
        parser.add_argument(
            '--allow-production',
            action='store_true',
            help='Allow seeding in a production environment (use only in an isolated demo database)',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not getattr(settings, 'DEBUG', True) and os.environ.get('RESQGRID_DEMO_DATABASE') != '1':
            raise CommandError(
                'Production demo seeding requires RESQGRID_DEMO_DATABASE=1 to prove the target is an isolated demo database.'
            )
        if not settings.DEBUG and not options['allow_production']:
            raise CommandError(
                'Demo seeding is disabled outside development. Use --allow-production only for an isolated public demo database.'
            )
        demo_password = os.environ.get('RESQGRID_DEMO_PASSWORD', '').strip()
        if not demo_password:
            raise CommandError('Set RESQGRID_DEMO_PASSWORD before seeding demo accounts.')
        if len(demo_password) < 12:
            raise CommandError('RESQGRID_DEMO_PASSWORD must be at least 12 characters.')
        self.stdout.write("Initializing ResQGrid Demo Data Seeding...")

        # -------------------------------------------------------------
        # 1. Seed Users and Profiles
        # -------------------------------------------------------------
        users_data = [
            # Admin
            {
                'username': 'admin',
                'first_name': 'Admin',
                'last_name': 'Director',
                'email': 'admin@resqgrid.demo',
                'role': UserRole.ADMIN,
                'phone': '+880 1711-000001',
                'org': 'National Disaster Management Center (Simulated)',
                'is_super': True,
            },
            # Citizens
            {
                'username': 'citizen_karim',
                'first_name': 'Karim',
                'last_name': 'Chowdhury',
                'email': 'karim@example.com',
                'role': UserRole.CITIZEN,
                'phone': '+880 1812-111111',
                'org': 'Resident, Mirpur, Dhaka',
                'is_super': False,
            },
            {
                'username': 'citizen_fatima',
                'first_name': 'Fatima',
                'last_name': 'Begum',
                'email': 'fatima@example.com',
                'role': UserRole.CITIZEN,
                'phone': '+880 1913-222222',
                'org': 'Resident, Sylhet Sadar',
                'is_super': False,
            },
            {
                'username': 'resource_manager',
                'first_name': 'Mina',
                'last_name': 'Rahman',
                'email': 'resources@resqgrid.demo',
                'role': UserRole.RESOURCE_MANAGER,
                'phone': '+880 1814-333333',
                'org': 'Central Relief Logistics (Simulated)',
                'is_super': False,
            },
            # Responders
            {
                'username': 'responder_boat',
                'first_name': 'Tariq',
                'last_name': 'Islam (Boat & Water Rescue)',
                'email': 'tariq.rescue@example.com',
                'role': UserRole.RESPONDER,
                'phone': '+880 1714-333331',
                'org': 'Bangladesh Volunteer Flood Corps (Simulated)',
                'is_super': False,
                'responder': {
                    'status': VerificationStatus.VERIFIED,
                    'avail': AvailabilityStatus.AVAILABLE,
                    'skills': 'WATER_RESCUE,FIRST_AID,EVACUATION_LOGISTICS',
                    'equipment': 'RESCUE_BOAT,FIRST_AID_KIT,EMERGENCY_VAN',
                    'area': 'Dhaka & Central Basin',
                    'lat': 23.8103,
                    'lon': 90.4125,
                    'radius': 35.0,
                    'capacity': 3,
                }
            },
            {
                'username': 'responder_medical',
                'first_name': 'Dr. Nabila',
                'last_name': 'Rahman (Mobile Medic)',
                'email': 'dr.nabila@example.com',
                'role': UserRole.RESPONDER,
                'phone': '+880 1715-444442',
                'org': 'Emergency Trauma Response Unit (Simulated)',
                'is_super': False,
                'responder': {
                    'status': VerificationStatus.VERIFIED,
                    'avail': AvailabilityStatus.AVAILABLE,
                    'skills': 'FIRST_AID,MEDICAL_DOCTOR,EVACUATION_LOGISTICS',
                    'equipment': 'AMBULANCE,FIRST_AID_KIT,STRETCHERS',
                    'area': 'Dhaka Metro & Savar',
                    'lat': 23.7925,
                    'lon': 90.4078,
                    'radius': 25.0,
                    'capacity': 2,
                }
            },
            {
                'username': 'responder_usar',
                'first_name': 'Capt. Faruk',
                'last_name': 'Ahmed (USAR / Collapse)',
                'email': 'faruk.usar@example.com',
                'role': UserRole.RESPONDER,
                'phone': '+880 1716-555553',
                'org': 'Urban Search & Rescue Team (Simulated)',
                'is_super': False,
                'responder': {
                    'status': VerificationStatus.VERIFIED,
                    'avail': AvailabilityStatus.AVAILABLE,
                    'skills': 'SEARCH_RESCUE,HEAVY_LIFTING,FIRST_AID',
                    'equipment': 'HYDRAULIC_CUTTER,DRONE,FIRST_AID_KIT',
                    'area': 'Greater Dhaka & Narayanganj',
                    'lat': 23.8223,
                    'lon': 90.3654,
                    'radius': 30.0,
                    'capacity': 2,
                }
            },
            {
                'username': 'responder_fire',
                'first_name': 'Kamal',
                'last_name': 'Hossain (Fire Volunteer)',
                'email': 'kamal.fire@example.com',
                'role': UserRole.RESPONDER,
                'phone': '+880 1717-666664',
                'org': 'Community Fire Volunteer Unit (Simulated)',
                'is_super': False,
                'responder': {
                    'status': VerificationStatus.VERIFIED,
                    'avail': AvailabilityStatus.AVAILABLE,
                    'skills': 'FIRE_FIGHTING,FIRST_AID',
                    'equipment': 'FIRE_PUMP,FIRST_AID_KIT',
                    'area': 'Chittagong Port Zone',
                    'lat': 22.3569,
                    'lon': 91.7832,
                    'radius': 25.0,
                    'capacity': 2,
                }
            },
            {
                'username': 'responder_no_gear',
                'first_name': 'Rafiq',
                'last_name': 'Sardar (No Boat)',
                'email': 'rafiq.volunteer@example.com',
                'role': UserRole.RESPONDER,
                'phone': '+880 1718-777775',
                'org': 'Local Youth Volunteer (Simulated)',
                'is_super': False,
                'responder': {
                    'status': VerificationStatus.VERIFIED,
                    'avail': AvailabilityStatus.AVAILABLE,
                    'skills': 'WATER_RESCUE,FIRST_AID',
                    'equipment': 'FIRST_AID_KIT',  # Notice: Has WATER_RESCUE skill, but lacks RESCUE_BOAT equipment!
                    'area': 'Sylhet Flood Zone',
                    'lat': 24.8949,
                    'lon': 91.8687,
                    'radius': 20.0,
                    'capacity': 2,
                }
            },
            {
                'username': 'responder_pending',
                'first_name': 'Sumon',
                'last_name': 'Miah (Applicant)',
                'email': 'sumon.pending@example.com',
                'role': UserRole.RESPONDER,
                'phone': '+880 1719-888886',
                'org': 'New Applicant Group (Simulated)',
                'is_super': False,
                'responder': {
                    'status': VerificationStatus.PENDING,
                    'avail': AvailabilityStatus.AVAILABLE,
                    'skills': 'FIRST_AID,EVACUATION_LOGISTICS',
                    'equipment': 'FIRST_AID_KIT',
                    'area': 'Dhaka North',
                    'lat': 23.8300,
                    'lon': 90.4200,
                    'radius': 15.0,
                    'capacity': 1,
                }
            },
        ]

        created_users = {}
        for udata in users_data:
            user, created = User.objects.get_or_create(username=udata['username'])
            user.first_name = udata['first_name']
            user.last_name = udata['last_name']
            user.email = udata['email']
            user.set_password(demo_password)
            if udata.get('is_super'):
                user.is_superuser = True
                user.is_staff = True
            user.save()

            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role = udata['role']
            profile.phone = udata['phone']
            profile.organization = udata['org']
            profile.is_verified = True
            profile.save()

            if 'responder' in udata:
                r_info = udata['responder']
                r_prof, _ = ResponderProfile.objects.get_or_create(user=user)
                r_prof.verification_status = r_info['status']
                r_prof.availability = r_info['avail']
                r_prof.skills = r_info['skills']
                r_prof.equipment = r_info['equipment']
                r_prof.service_area_name = r_info['area']
                r_prof.latitude = r_info['lat']
                r_prof.longitude = r_info['lon']
                r_prof.service_radius_km = r_info['radius']
                r_prof.max_active_capacity = r_info['capacity']
                r_prof.save()

            created_users[udata['username']] = user

        self.stdout.write(self.style.SUCCESS("[OK] Seeded demo users, including a resource manager, and responder profiles."))

        # -------------------------------------------------------------
        # 2. Seed Shelters & Resources (Module E)
        # -------------------------------------------------------------
        shelters_data = [
            {
                'name': 'Dhaka Mirpur Indoor Stadium Relief Center [SIMULATED]',
                'address': 'Section 10, Mirpur, Dhaka-1216',
                'lat': 23.8070,
                'lon': 90.3686,
                'total': 300,
                'occupied': 120,
                'food': True,
                'water': True,
                'medical': True,
                'status': ShelterStatus.OPEN,
                'contact': 'Lt. Col. Mansoor',
                'phone': '+880 1711-223344',
            },
            {
                'name': 'Sylhet Osmani Nagar Flood Shelter [SIMULATED]',
                'address': 'Osmani Nagar Degree College, Sylhet',
                'lat': 24.8949,
                'lon': 91.8687,
                'total': 200,
                'occupied': 195,  # Only 5 spots remaining! (Used for Scenario 5)
                'food': True,
                'water': True,
                'medical': False,
                'status': ShelterStatus.OPEN,
                'contact': 'Prof. Anisur Rahman',
                'phone': '+880 1712-334455',
            },
            {
                'name': 'Agrabad Model High School Cyclone Shelter [SIMULATED]',
                'address': 'Agrabad C/A, Chattogram',
                'lat': 22.3275,
                'lon': 91.8122,
                'total': 400,
                'occupied': 45,
                'food': True,
                'water': True,
                'medical': True,
                'status': ShelterStatus.OPEN,
                'contact': 'Ms. Selina Akter',
                'phone': '+880 1713-445566',
            },
            {
                'name': 'Rupsha Riverbank Evacuation Point [SIMULATED]',
                'address': 'Rupsha Ghat, Khulna',
                'lat': 22.8055,
                'lon': 89.5694,
                'total': 100,
                'occupied': 100,  # FULL!
                'food': True,
                'water': True,
                'medical': False,
                'status': ShelterStatus.FULL,
                'contact': 'Abdul Halim',
                'phone': '+880 1714-556677',
            },
        ]

        created_shelters = {}
        for sdata in shelters_data:
            s, _ = Shelter.objects.get_or_create(
                name=sdata['name'],
                defaults={
                    'address': sdata['address'],
                    'latitude': sdata['lat'],
                    'longitude': sdata['lon'],
                    'total_capacity': sdata['total'],
                    'occupied_capacity': sdata['occupied'],
                    'has_food': sdata['food'],
                    'has_water': sdata['water'],
                    'has_medical': sdata['medical'],
                    'status': sdata['status'],
                    'contact_person': sdata['contact'],
                    'contact_phone': sdata['phone'],
                }
            )
            # Update fields in case they changed
            s.address = sdata['address']
            s.latitude = sdata['lat']
            s.longitude = sdata['lon']
            s.total_capacity = sdata['total']
            s.occupied_capacity = sdata['occupied']
            s.has_food = sdata['food']
            s.has_water = sdata['water']
            s.has_medical = sdata['medical']
            s.status = sdata['status']
            s.contact_person = sdata['contact']
            s.contact_phone = sdata['phone']
            s.save()
            created_shelters[sdata['name']] = s

        self.stdout.write(self.style.SUCCESS("[OK] Seeded 4 shelters with capacity limits."))

        resources_data = [
            ('Emergency Water Packs [SIMULATED]', ResourceCategory.WATER, 500, 'packs', 'Dhaka Central Warehouse', created_shelters['Dhaka Mirpur Indoor Stadium Relief Center [SIMULATED]']),
            ('Trauma Medical Kits [SIMULATED]', ResourceCategory.MEDICAL_SUPPLIES, 150, 'kits', 'Dhaka Central Warehouse', created_shelters['Dhaka Mirpur Indoor Stadium Relief Center [SIMULATED]']),
            ('Flood Rescue Boats [SIMULATED]', ResourceCategory.RESCUE_EQUIPMENT, 12, 'units', 'Sylhet Flood Depot', created_shelters['Sylhet Osmani Nagar Flood Shelter [SIMULATED]']),
            ('Emergency Blankets [SIMULATED]', ResourceCategory.BLANKETS_CLOTHING, 800, 'blankets', 'Chattogram Relief Depot', created_shelters['Agrabad Model High School Cyclone Shelter [SIMULATED]']),
        ]
        for name, category, quantity, unit, location, shelter in resources_data:
            Resource.objects.get_or_create(
                name=name,
                defaults={
                    'category': category,
                    'quantity': quantity,
                    'unit': unit,
                    'location_name': location,
                    'latitude': shelter.latitude,
                    'longitude': shelter.longitude,
                    'shelter': shelter,
                    'status': ResourceStatus.AVAILABLE if quantity > 0 else ResourceStatus.DEPLETED,
                }
            )
        self.stdout.write(self.style.SUCCESS("[OK] Seeded 4 fictional relief resource inventories."))

        # -------------------------------------------------------------
        # 3. Seed Demonstrable Incidents & Verified Scenarios
        # -------------------------------------------------------------
        admin_user = created_users['admin']
        karim_user = created_users['citizen_karim']
        fatima_user = created_users['citizen_fatima']
        boat_user = created_users['responder_boat']
        usar_user = created_users['responder_usar']
        medic_user = created_users['responder_medical']

        # Scenario 1 - Incident A: CRITICAL emergency
        inc_critical, _ = Incident.objects.get_or_create(
            incident_id='RSQ-DEMO-CRITICAL',
            defaults={
                'reporter': karim_user,
                'reported_for': 'SELF',
                'contact_name': 'Karim Chowdhury',
                'contact_phone': '+880 1812-111111',
                'emergency_type': EmergencyType.BUILDING_COLLAPSE,
                'description': '[SIMULATED - SCENARIO 1] 4-story garment worker residence partial collapse. Multiple families trapped under concrete slabs, live sparking wires.',
                'immediate_threat_to_life': True,
                'affected_count': 18,
                'injured_count': 6,
                'trapped_count': 4,
                'has_vulnerable_people': True,
                'vulnerable_details': '2 toddlers, 1 paralyzed elderly person',
                'access_difficulty': AccessDifficulty.DIFFICULT,
                'location_name': 'Sector 3, Uttara, Dhaka [SIMULATED]',
                'latitude': 23.8680,
                'longitude': 90.3980,
            }
        )
        score_crit, level_crit, exp_crit = PriorityEngine.evaluate(inc_critical)
        inc_critical.priority_score = score_crit
        inc_critical.priority_level = level_crit
        inc_critical.priority_explanation = exp_crit
        inc_critical.status = IncidentStatus.ASSIGNED
        inc_critical.assigned_responder = usar_user
        inc_critical.save()

        IncidentEvent.objects.get_or_create(
            incident=inc_critical,
            event_type=EventType.CREATED,
            defaults={'actor': karim_user, 'description': 'Critical emergency reported by citizen.'}
        )
        IncidentEvent.objects.get_or_create(
            incident=inc_critical,
            event_type=EventType.TRIAGED,
            defaults={'actor': admin_user, 'description': f'Triage Engine computed CRITICAL score: {score_crit}.'}
        )
        Assignment.objects.get_or_create(
            incident=inc_critical,
            responder=usar_user,
            defaults={
                'status': AssignmentStatus.PENDING,
                'match_score': 92.0,
                'match_explanation': 'Matched USAR specialist with hydraulic cutters and drone reconnaissance within 8km.'
            }
        )

        # Scenario 1 - Incident B: LOW emergency
        inc_low, _ = Incident.objects.get_or_create(
            incident_id='RSQ-DEMO-LOW',
            defaults={
                'reporter': karim_user,
                'reported_for': 'SELF',
                'contact_name': 'Karim Chowdhury',
                'contact_phone': '+880 1812-111111',
                'emergency_type': EmergencyType.OTHER,
                'description': '[SIMULATED - SCENARIO 1] Minor ankle-deep road waterlogging after heavy rain. Drain clogged. No danger or trapped individuals.',
                'immediate_threat_to_life': False,
                'affected_count': 2,
                'injured_count': 0,
                'trapped_count': 0,
                'has_vulnerable_people': False,
                'access_difficulty': AccessDifficulty.EASY,
                'location_name': 'Dhanmondi Road 27, Dhaka [SIMULATED]',
                'latitude': 23.7540,
                'longitude': 90.3750,
            }
        )
        score_low, level_low, exp_low = PriorityEngine.evaluate(inc_low)
        inc_low.priority_score = score_low
        inc_low.priority_level = level_low
        inc_low.priority_explanation = exp_low
        inc_low.status = IncidentStatus.TRIAGED
        inc_low.save()

        # Scenario 3 Incident: Responder rejection with automated reassignment
        inc_reassign, _ = Incident.objects.get_or_create(
            incident_id='RSQ-DEMO-REASSIGN',
            defaults={
                'reporter': fatima_user,
                'reported_for': 'OTHER',
                'victim_name': 'Jamil Hossain & Family',
                'contact_name': 'Fatima Begum',
                'contact_phone': '+880 1913-222222',
                'emergency_type': EmergencyType.MEDICAL,
                'description': '[SIMULATED - SCENARIO 3] Severe acute respiratory distress and trauma injuries following highway minibus collision.',
                'immediate_threat_to_life': True,
                'affected_count': 4,
                'injured_count': 3,
                'trapped_count': 0,
                'has_vulnerable_people': True,
                'access_difficulty': AccessDifficulty.EASY,
                'location_name': 'Airport Road, Kurmitola, Dhaka [SIMULATED]',
                'latitude': 23.8285,
                'longitude': 90.4150,
            }
        )
        score_reassign, level_reassign, exp_reassign = PriorityEngine.evaluate(inc_reassign)
        inc_reassign.priority_score = score_reassign
        inc_reassign.priority_level = level_reassign
        inc_reassign.priority_explanation = exp_reassign
        inc_reassign.status = IncidentStatus.ASSIGNED
        inc_reassign.assigned_responder = medic_user
        inc_reassign.save()

        # Assignment 1: Previously rejected by responder_boat because they were deployed on water rescue
        Assignment.objects.get_or_create(
            incident=inc_reassign,
            responder=boat_user,
            defaults={
                'status': AssignmentStatus.REJECTED,
                'rejection_reason': 'Team deployed on deep water rescue at Turag river. Redirecting to medical unit.',
                'match_score': 72.0,
                'match_explanation': 'Initial dispatch attempted based on proximity.'
            }
        )
        # Assignment 2: Successfully auto-reassigned to medic_user
        Assignment.objects.get_or_create(
            incident=inc_reassign,
            responder=medic_user,
            defaults={
                'status': AssignmentStatus.PENDING,
                'match_score': 95.0,
                'match_explanation': 'Automated workflow failover: Dispatched specialized medical doctor with ambulance.'
            }
        )
        IncidentEvent.objects.get_or_create(
            incident=inc_reassign,
            event_type=EventType.AUTO_REASSIGNED,
            defaults={
                'actor': None,
                'description': f'Automated failover: responder_boat declined. Dispatched next best match {medic_user.username}.'
            }
        )

        # Scenario 4 Incident: No eligible responder scenario -> Marked UNASSIGNED
        inc_unassigned, _ = Incident.objects.get_or_create(
            incident_id='RSQ-DEMO-UNASSIGNED',
            defaults={
                'reporter': fatima_user,
                'reported_for': 'SELF',
                'contact_name': 'Fatima Begum',
                'contact_phone': '+880 1913-222222',
                'emergency_type': EmergencyType.CYCLONE,
                'description': '[SIMULATED - SCENARIO 4] Coastal surge cut off isolated delta sandbar. Requires specialized heavy amphibious transport van no local responders currently possess.',
                'immediate_threat_to_life': True,
                'affected_count': 35,
                'injured_count': 4,
                'trapped_count': 0,
                'has_vulnerable_people': True,
                'access_difficulty': AccessDifficulty.INACCESSIBLE,
                'location_name': 'Hatiya Remote Delta Island, Noakhali [SIMULATED]',
                'latitude': 22.2850,
                'longitude': 91.1050,
            }
        )
        score_un, level_un, exp_un = PriorityEngine.evaluate(inc_unassigned)
        inc_unassigned.priority_score = score_un
        inc_unassigned.priority_level = level_un
        inc_unassigned.priority_explanation = exp_un
        inc_unassigned.status = IncidentStatus.UNASSIGNED
        inc_unassigned.unassigned_reason = (
            "Automatic matching found zero eligible responders within service range (distance > 150km). "
            "Required equipment: EMERGENCY_VAN. Administrator manual escalation or aerial aid required."
        )
        inc_unassigned.save()

        IncidentEvent.objects.get_or_create(
            incident=inc_unassigned,
            event_type=EventType.UNASSIGNED_ALERT,
            defaults={
                'actor': None,
                'description': inc_unassigned.unassigned_reason
            }
        )

        # Additional Incident: Resolved incident with full event history
        inc_resolved, _ = Incident.objects.get_or_create(
            incident_id='RSQ-DEMO-RESOLVED',
            defaults={
                'reporter': karim_user,
                'contact_name': 'Karim Chowdhury',
                'contact_phone': '+880 1812-111111',
                'emergency_type': EmergencyType.FIRE,
                'description': '[SIMULATED - RESOLVED DEMO] Small electrical fire in apartment basement. Extinguished successfully with volunteer pumps.',
                'immediate_threat_to_life': False,
                'affected_count': 6,
                'injured_count': 1,
                'trapped_count': 0,
                'access_difficulty': AccessDifficulty.EASY,
                'location_name': 'Mirpur 14, Dhaka [SIMULATED]',
                'latitude': 23.8050,
                'longitude': 90.3800,
                'status': IncidentStatus.RESOLVED,
                'resolved_at': timezone.now(),
            }
        )
        score_res, level_res, exp_res = PriorityEngine.evaluate(inc_resolved)
        inc_resolved.priority_score = score_res
        inc_resolved.priority_level = level_res
        inc_resolved.priority_explanation = exp_res
        inc_resolved.save()

        self.stdout.write(self.style.SUCCESS("[OK] Seeded demonstration incidents for Scenarios 1, 2, 3, 4, and 5."))
        self.stdout.write(self.style.SUCCESS("All demo accounts are ready."))
        self.stdout.write("Demo password configured via RESQGRID_DEMO_PASSWORD.")
