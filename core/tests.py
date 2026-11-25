"""
Comprehensive Automated Test Suite for ResQGrid
Tests all modules, business rules, workflows, security permissions, and the 5 demonstration scenarios.
"""

from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.urls import reverse
from django.core.cache import cache
from django.core.management import call_command, CommandError
from django.db import IntegrityError, transaction
from unittest.mock import patch

from core.models import (
    UserProfile, ResponderProfile, UserRole, VerificationStatus, AvailabilityStatus,
    Incident, EmergencyType, PriorityLevel, IncidentStatus, AccessDifficulty,
    Assignment, AssignmentStatus, IncidentEvent, EventType,
    Shelter, ShelterAllocation, ShelterStatus, Resource,
    ResourceCategory, ResourceStatus
)
from core.engines.priority_engine import PriorityEngine
from core.engines.matching_engine import MatchingEngine
from core.engines.workflow_engine import WorkflowEngine
from core.templatetags.resqgrid_tags import priority_badge_class


class ResQGridBaseTestCase(TestCase):
    """Base setup with seeded test users and responders."""

    def setUp(self):
        # Admin User
        self.admin_user = User.objects.create_superuser(
            username='test_admin',
            email='admin@test.com',
            password='password123'
        )
        UserProfile.objects.create(
            user=self.admin_user,
            role=UserRole.ADMIN,
            phone='+8801700000001',
            is_verified=True
        )

        # Citizen User
        self.citizen_user = User.objects.create_user(
            username='test_citizen',
            email='citizen@test.com',
            password='password123'
        )
        UserProfile.objects.create(
            user=self.citizen_user,
            role=UserRole.CITIZEN,
            phone='+8801700000002',
            is_verified=True
        )

        # Responder 1: Water Rescue with Boat (Verified, Available)
        self.resp_boat = User.objects.create_user(
            username='resp_boat',
            email='boat@test.com',
            password='password123'
        )
        UserProfile.objects.create(
            user=self.resp_boat,
            role=UserRole.RESPONDER,
            phone='+8801700000003',
            is_verified=True
        )
        self.resp_boat_profile = ResponderProfile.objects.create(
            user=self.resp_boat,
            verification_status=VerificationStatus.VERIFIED,
            availability=AvailabilityStatus.AVAILABLE,
            skills='WATER_RESCUE,FIRST_AID',
            equipment='RESCUE_BOAT,FIRST_AID_KIT',
            latitude=23.8103,
            longitude=90.4125,
            service_radius_km=30.0,
            max_active_capacity=2,
            current_active_assignments=0
        )

        # Responder 2: Water Rescue but NO Boat (Has FIRST_AID_KIT only)
        self.resp_no_boat = User.objects.create_user(
            username='resp_no_boat',
            email='noboat@test.com',
            password='password123'
        )
        UserProfile.objects.create(
            user=self.resp_no_boat,
            role=UserRole.RESPONDER,
            phone='+8801700000004',
            is_verified=True
        )
        self.resp_no_boat_profile = ResponderProfile.objects.create(
            user=self.resp_no_boat,
            verification_status=VerificationStatus.VERIFIED,
            availability=AvailabilityStatus.AVAILABLE,
            skills='WATER_RESCUE,FIRST_AID',
            equipment='FIRST_AID_KIT', # Missing RESCUE_BOAT!
            latitude=23.8103,
            longitude=90.4125,
            service_radius_km=30.0,
            max_active_capacity=2,
            current_active_assignments=0
        )

        # Responder 3: Backup Water Rescue with Boat
        self.resp_backup_boat = User.objects.create_user(
            username='resp_backup_boat',
            email='backup@test.com',
            password='password123'
        )
        UserProfile.objects.create(
            user=self.resp_backup_boat,
            role=UserRole.RESPONDER,
            phone='+8801700000005',
            is_verified=True
        )
        self.resp_backup_boat_profile = ResponderProfile.objects.create(
            user=self.resp_backup_boat,
            verification_status=VerificationStatus.VERIFIED,
            availability=AvailabilityStatus.AVAILABLE,
            skills='WATER_RESCUE,FIRST_AID',
            equipment='RESCUE_BOAT,FIRST_AID_KIT',
            latitude=23.8200,
            longitude=90.4200,
            service_radius_km=30.0,
            max_active_capacity=2,
            current_active_assignments=0
        )

        self.client = Client()


class Scenario1PriorityEngineTests(ResQGridBaseTestCase):
    """
    Scenario 1: A critical emergency receives higher priority than a normal emergency.
    Also validates Module B transparent factor scoring and explanations.
    """

    def test_scenario_1_critical_emergency_higher_priority_than_normal(self):
        # Critical Emergency: Building collapse with trapped, injured, life-threat, vulnerable
        critical_incident = Incident.objects.create(
            reporter=self.citizen_user,
            emergency_type=EmergencyType.BUILDING_COLLAPSE,
            description="Collapsed building with trapped workers.",
            contact_name="Karim",
            contact_phone="+8801700000000",
            location_name="Mirpur, Dhaka",
            latitude=23.8103,
            longitude=90.4125,
            immediate_threat_to_life=True,
            affected_count=15,
            injured_count=5,
            trapped_count=3,
            has_vulnerable_people=True,
            vulnerable_details="Infants present",
            access_difficulty=AccessDifficulty.DIFFICULT
        )

        # Normal / Minor Emergency: Single person minor issue, no injuries or threat
        normal_incident = Incident.objects.create(
            reporter=self.citizen_user,
            emergency_type=EmergencyType.OTHER,
            description="Ankle deep water on driveway.",
            contact_name="Karim",
            contact_phone="+8801700000000",
            location_name="Gulshan, Dhaka",
            latitude=23.7900,
            longitude=90.4000,
            immediate_threat_to_life=False,
            affected_count=1,
            injured_count=0,
            trapped_count=0,
            has_vulnerable_people=False,
            access_difficulty=AccessDifficulty.EASY
        )

        crit_score, crit_level, crit_exp = PriorityEngine.evaluate(critical_incident)
        norm_score, norm_level, norm_exp = PriorityEngine.evaluate(normal_incident)

        # Verification of Scenario 1
        self.assertGreater(crit_score, norm_score, "Critical emergency score must exceed normal emergency score.")
        self.assertEqual(crit_level, PriorityLevel.CRITICAL)
        self.assertEqual(norm_level, PriorityLevel.LOW)
        self.assertIn("Active immediate threat to human life", crit_exp)
        self.assertIn("physically trapped", crit_exp)
        self.assertIn("High-vulnerability individuals present", crit_exp)

    def test_waiting_penalty_only_applies_while_incident_is_unassigned(self):
        waiting = Incident.objects.create(
            reporter=self.citizen_user,
            emergency_type=EmergencyType.OTHER,
            description="Waiting report.",
            contact_name="Citizen",
            contact_phone="+8801700000000",
            location_name="Dhaka",
            status=IncidentStatus.UNASSIGNED,
        )
        assigned = Incident.objects.create(
            reporter=self.citizen_user,
            emergency_type=EmergencyType.OTHER,
            description="Assigned report.",
            contact_name="Citizen",
            contact_phone="+8801700000000",
            location_name="Dhaka",
            status=IncidentStatus.ASSIGNED,
        )

        waiting_score, _, waiting_explanation = PriorityEngine.evaluate(
            waiting, waiting_minutes=30
        )
        assigned_score, _, assigned_explanation = PriorityEngine.evaluate(
            assigned, waiting_minutes=30
        )

        self.assertEqual(waiting_score - assigned_score, 4)
        self.assertIn("Unassigned delay penalty", waiting_explanation)
        self.assertNotIn("Unassigned delay penalty", assigned_explanation)


class Scenario2MatchingEngineTests(ResQGridBaseTestCase):
    """
    Scenario 2: A responder without the required equipment is rejected by the matching engine.
    """

    def test_scenario_2_responder_without_equipment_is_rejected(self):
        # Create flood incident that requires RESCUE_BOAT equipment
        flood_incident = Incident.objects.create(
            reporter=self.citizen_user,
            emergency_type=EmergencyType.FLOOD,
            description="Flash flood in char area. Boat required.",
            contact_name="Citizen",
            contact_phone="+8801700000000",
            location_name="Turag River Basin",
            latitude=23.8103,
            longitude=90.4125,
            immediate_threat_to_life=True,
            affected_count=5,
            access_difficulty=AccessDifficulty.DIFFICULT
        )

        required_equipment = flood_incident.get_required_equipment()
        self.assertIn('RESCUE_BOAT', required_equipment)

        # Find eligible matches
        matches, _ = MatchingEngine.find_matches(flood_incident)
        matched_user_ids = [m['responder'].id for m in matches]

        # Verification of Scenario 2:
        # resp_boat HAS RESCUE_BOAT -> Must be matched
        self.assertIn(self.resp_boat.id, matched_user_ids)
        # resp_no_boat LACKS RESCUE_BOAT -> Must be strictly rejected!
        self.assertNotIn(self.resp_no_boat.id, matched_user_ids)


class Scenario3ReassignmentWorkflowTests(ResQGridBaseTestCase):
    """
    Scenario 3: A responder rejects an assignment and the system automatically tries the next eligible responder.
    """

    def test_scenario_3_rejection_triggers_automatic_reassignment(self):
        flood_incident = Incident.objects.create(
            reporter=self.citizen_user,
            emergency_type=EmergencyType.FLOOD,
            description="Rising water, family stranded.",
            contact_name="Citizen",
            contact_phone="+8801700000000",
            location_name="Mirpur, Dhaka",
            latitude=23.8103,
            longitude=90.4125,
            status=IncidentStatus.TRIAGED
        )

        # Step 1: Initial dispatch matches top candidate (resp_boat)
        assignment1, _ = WorkflowEngine.dispatch_top_responder(flood_incident)
        self.assertIsNotNone(assignment1)
        self.assertEqual(assignment1.responder, self.resp_boat)
        self.assertEqual(assignment1.status, AssignmentStatus.PENDING)
        self.assertEqual(flood_incident.status, IncidentStatus.ASSIGNED)

        # Step 2: Responder 1 declines / rejects assignment
        new_assignment, msg = WorkflowEngine.reject_assignment(
            assignment1,
            self.resp_boat,
            reason="Equipment undergoing maintenance."
        )

        # Verification of Scenario 3:
        # 1. Previous assignment is REJECTED
        assignment1.refresh_from_db()
        self.assertEqual(assignment1.status, AssignmentStatus.REJECTED)
        self.assertEqual(assignment1.rejection_reason, "Equipment undergoing maintenance.")

        # 2. System automatically created a new assignment with the next eligible responder (resp_backup_boat)
        self.assertIsNotNone(new_assignment, "Workflow must automatically assign next candidate.")
        self.assertEqual(new_assignment.responder, self.resp_backup_boat)
        self.assertEqual(new_assignment.status, AssignmentStatus.PENDING)

        flood_incident.refresh_from_db()
        self.assertEqual(flood_incident.assigned_responder, self.resp_backup_boat)
        self.assertEqual(flood_incident.status, IncidentStatus.ASSIGNED)

        # 3. Audit event logged
        auto_event = IncidentEvent.objects.filter(
            incident=flood_incident,
            event_type=EventType.AUTO_REASSIGNED
        ).first()
        self.assertIsNotNone(auto_event)
        self.assertIn("Automated workflow failover", auto_event.description)


class Scenario4NoEligibleResponderTests(ResQGridBaseTestCase):
    """
    Scenario 4: No eligible responder exists, so the incident remains unassigned with an explanation.
    """

    def test_scenario_4_no_eligible_responder_remains_unassigned_with_explanation(self):
        # Create an emergency requiring HYDRAULIC_CUTTER and SEARCH_RESCUE
        collapse_incident = Incident.objects.create(
            reporter=self.citizen_user,
            emergency_type=EmergencyType.BUILDING_COLLAPSE,
            description="Collapsed structure requiring heavy hydraulic cutters.",
            contact_name="Citizen",
            contact_phone="+8801700000000",
            location_name="Remote Zone",
            latitude=23.8103,
            longitude=90.4125,
            status=IncidentStatus.TRIAGED
        )

        # In our setUp, neither resp_boat nor resp_no_boat has SEARCH_RESCUE or HYDRAULIC_CUTTER
        assignment, msg = WorkflowEngine.dispatch_top_responder(collapse_incident)

        # Verification of Scenario 4:
        self.assertIsNone(assignment)
        collapse_incident.refresh_from_db()
        self.assertEqual(collapse_incident.status, IncidentStatus.UNASSIGNED)
        self.assertIsNone(collapse_incident.assigned_responder)
        self.assertIn("Automatic matching found zero eligible responders", collapse_incident.unassigned_reason)

        # Event log
        event = IncidentEvent.objects.filter(
            incident=collapse_incident,
            event_type=EventType.UNASSIGNED_ALERT
        ).first()
        self.assertIsNotNone(event)
        self.assertIn("Auto-dispatch failed", event.description)


class Scenario5ShelterCapacityTests(ResQGridBaseTestCase):
    """
    Scenario 5: A shelter cannot accept more people than its remaining capacity.
    """

    def test_scenario_5_shelter_cannot_exceed_capacity(self):
        # Shelter with total capacity 50, occupied 45 -> Only 5 spots available
        shelter = Shelter.objects.create(
            name="Community Evacuation Center",
            address="Dhaka",
            total_capacity=50,
            occupied_capacity=45,
            status=ShelterStatus.OPEN
        )

        self.assertEqual(shelter.available_capacity, 5)

        # Valid allocation: 4 people (4 <= 5) -> Succeeds!
        shelter.allocate_people(4)
        shelter.refresh_from_db()
        self.assertEqual(shelter.occupied_capacity, 49)
        self.assertEqual(shelter.available_capacity, 1)

        # Invalid allocation: Attempting to allocate 3 people when only 1 spot remains!
        with self.assertRaises(ValidationError) as context:
            shelter.allocate_people(3)

        self.assertIn("Cannot allocate 3 people", str(context.exception))
        # Ensure occupied capacity did NOT increase past limit
        shelter.refresh_from_db()
        self.assertEqual(shelter.occupied_capacity, 49)

        # Allocate exactly 1 to fill shelter -> status becomes FULL
        shelter.allocate_people(1)
        shelter.refresh_from_db()
        self.assertEqual(shelter.occupied_capacity, 50)
        self.assertEqual(shelter.status, ShelterStatus.FULL)


class WorkflowIntegrityAndTransitionTests(ResQGridBaseTestCase):
    """
    Tests state machine transition validation, duplicate assignment guards, and full lifecycle.
    """

    def test_prevent_invalid_status_transitions(self):
        incident = Incident.objects.create(
            reporter=self.citizen_user,
            emergency_type=EmergencyType.OTHER,
            description="Testing state transitions.",
            contact_name="Citizen",
            contact_phone="+8801700000000",
            location_name="Dhaka",
            status=IncidentStatus.REPORTED
        )

        # REPORTED cannot jump directly to RESOLVED without response
        with self.assertRaises(ValidationError):
            incident.validate_transition(IncidentStatus.RESOLVED)

    def test_prevent_duplicate_active_assignment(self):
        incident = Incident.objects.create(
            reporter=self.citizen_user,
            emergency_type=EmergencyType.FLOOD,
            description="Flood distress.",
            contact_name="Citizen",
            contact_phone="+8801700000000",
            location_name="Dhaka",
            status=IncidentStatus.TRIAGED
        )

        # First dispatch
        WorkflowEngine.dispatch_top_responder(incident)

        # Second dispatch attempt on same active incident must raise ValidationError
        with self.assertRaises(ValidationError):
            WorkflowEngine.dispatch_top_responder(incident)

    def test_database_rejects_multiple_active_assignments_for_one_incident(self):
        incident = Incident.objects.create(
            reporter=self.citizen_user,
            emergency_type=EmergencyType.FLOOD,
            description="Flood distress.",
            contact_name="Citizen",
            contact_phone="+8801700000000",
            location_name="Dhaka",
        )
        Assignment.objects.create(
            incident=incident,
            responder=self.resp_boat,
            status=AssignmentStatus.PENDING,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Assignment.objects.create(
                    incident=incident,
                    responder=self.resp_backup_boat,
                    status=AssignmentStatus.ACCEPTED,
                )

    def test_complete_end_to_end_lifecycle(self):
        # 1. Report SOS
        incident = Incident.objects.create(
            reporter=self.citizen_user,
            emergency_type=EmergencyType.FLOOD,
            description="Rising water.",
            contact_name="Citizen",
            contact_phone="+8801700000000",
            location_name="Dhaka"
        )
        # 2 & 3 & 4. Process new incident (triage + dispatch)
        WorkflowEngine.process_new_incident(incident, actor=self.citizen_user, auto_dispatch=True)
        incident.refresh_from_db()
        self.assertEqual(incident.status, IncidentStatus.ASSIGNED)

        assignment = Assignment.objects.filter(incident=incident, status=AssignmentStatus.PENDING).first()
        self.assertIsNotNone(assignment)

        # 5. Responder Accepts
        WorkflowEngine.accept_assignment(assignment, assignment.responder)
        incident.refresh_from_db()
        self.assertEqual(incident.status, IncidentStatus.ACCEPTED)

        # 8. Responder En Route
        WorkflowEngine.update_to_responding(incident, assignment.responder, progress_notes="In transit.")
        incident.refresh_from_db()
        self.assertEqual(incident.status, IncidentStatus.RESPONDING)

        # 9. Responder Resolves
        WorkflowEngine.resolve_incident(incident, assignment.responder, resolution_notes="Evacuated safely.")
        incident.refresh_from_db()
        self.assertEqual(incident.status, IncidentStatus.RESOLVED)
        self.assertIsNotNone(incident.resolved_at)

    def test_acceptance_rolls_back_all_changes_when_audit_event_write_fails(self):
        incident = Incident.objects.create(
            reporter=self.citizen_user,
            emergency_type=EmergencyType.FLOOD,
            description="Flood response.",
            contact_name="Citizen",
            contact_phone="+8801700000000",
            location_name="Dhaka",
            status=IncidentStatus.TRIAGED,
        )
        assignment, _ = WorkflowEngine.dispatch_top_responder(incident)
        responder_profile = ResponderProfile.objects.get(user=assignment.responder)
        original_capacity = responder_profile.current_active_assignments

        with patch.object(
            IncidentEvent.objects,
            'create',
            side_effect=RuntimeError('simulated audit store failure'),
        ):
            with self.assertRaises(RuntimeError):
                WorkflowEngine.accept_assignment(assignment, assignment.responder)

        incident.refresh_from_db()
        assignment.refresh_from_db()
        responder_profile.refresh_from_db()
        self.assertEqual(incident.status, IncidentStatus.ASSIGNED)
        self.assertEqual(assignment.status, AssignmentStatus.PENDING)
        self.assertEqual(responder_profile.current_active_assignments, original_capacity)

    def test_dispatch_rolls_back_assignment_when_audit_event_write_fails(self):
        incident = Incident.objects.create(
            reporter=self.citizen_user,
            emergency_type=EmergencyType.FLOOD,
            description="Flood response.",
            contact_name="Citizen",
            contact_phone="+8801700000000",
            location_name="Dhaka",
            status=IncidentStatus.TRIAGED,
        )

        with patch.object(
            IncidentEvent.objects,
            'create',
            side_effect=RuntimeError('simulated audit store failure'),
        ):
            with self.assertRaises(RuntimeError):
                WorkflowEngine.dispatch_top_responder(incident)

        incident.refresh_from_db()
        self.assertEqual(incident.status, IncidentStatus.TRIAGED)
        self.assertIsNone(incident.assigned_responder)
        self.assertFalse(Assignment.objects.filter(incident=incident).exists())


class SecurityAndRolePermissionTests(ResQGridBaseTestCase):
    """
    Tests server-side role access control and protections.
    """

    def test_citizen_cannot_access_admin_dashboard(self):
        self.client.login(username='test_citizen', password='password123')
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_access_admin_dashboard(self):
        self.client.login(username='test_admin', password='password123')
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Admin Command Center")

    def test_responder_can_access_responder_dashboard(self):
        self.client.login(username='resp_boat', password='password123')
        response = self.client.get(reverse('responder_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Responder Mission Terminal")

    def test_unauthorized_user_cannot_view_others_private_incident(self):
        # Create incident belonging to citizen_user
        inc = Incident.objects.create(
            reporter=self.citizen_user,
            emergency_type=EmergencyType.OTHER,
            description="Private emergency.",
            contact_name="Private",
            contact_phone="+8801999999999",
            location_name="Private Area",
            status=IncidentStatus.REPORTED
        )

        # Another unrelated citizen logs in
        other_citizen = User.objects.create_user(username='other_citizen', password='password123')
        UserProfile.objects.create(user=other_citizen, role=UserRole.CITIZEN)
        self.client.login(username='other_citizen', password='password123')

        response = self.client.get(reverse('incident_detail', kwargs={'incident_id': inc.incident_id}))
        self.assertEqual(response.status_code, 403)


class EnhancedFieldFeaturesTests(ResQGridBaseTestCase):
    """
    Tests operational field note updates, re-triage triggers, shelter-incident linking, and stats API.
    """

    def test_post_field_note_creates_audit_event(self):
        inc = Incident.objects.create(
            reporter=self.citizen_user,
            emergency_type=EmergencyType.FLOOD,
            description="Water rising.",
            contact_name="Karim",
            contact_phone="+8801700000000",
            location_name="Mirpur, Dhaka",
            status=IncidentStatus.ASSIGNED,
            assigned_responder=self.resp_boat
        )

        # Citizen posts note
        self.client.login(username='test_citizen', password='password123')
        resp = self.client.post(
            reverse('incident_post_note', kwargs={'incident_id': inc.incident_id}),
            {'note': 'Water has entered ground floor apartments.'}
        )
        self.assertEqual(resp.status_code, 302)

        event = IncidentEvent.objects.filter(
            incident=inc,
            event_type=EventType.STATUS_UPDATE,
            description__contains='Water has entered ground floor'
        ).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.actor, self.citizen_user)

    def test_admin_retrigger_triage(self):
        inc = Incident.objects.create(
            reporter=self.citizen_user,
            emergency_type=EmergencyType.FIRE,
            description="Factory fire spreading.",
            contact_name="Karim",
            contact_phone="+8801700000000",
            location_name="Dhaka",
            immediate_threat_to_life=True,
            affected_count=10,
            status=IncidentStatus.UNASSIGNED
        )
        self.client.login(username='test_admin', password='password123')
        resp = self.client.post(reverse('incident_retrigger_triage', kwargs={'incident_id': inc.incident_id}))
        self.assertEqual(resp.status_code, 302)
        inc.refresh_from_db()
        self.assertGreater(inc.priority_score, 0)

    def test_shelter_allocation_linked_to_incident(self):
        shelter = Shelter.objects.create(
            name="Flood Evac Station",
            address="Dhaka",
            total_capacity=100,
            occupied_capacity=10,
            status=ShelterStatus.OPEN
        )
        inc = Incident.objects.create(
            reporter=self.citizen_user,
            emergency_type=EmergencyType.FLOOD,
            description="Evacuees need lodging.",
            contact_name="Karim",
            contact_phone="+8801700000000",
            location_name="Dhaka",
            status=IncidentStatus.RESPONDING,
            assigned_responder=self.resp_boat
        )
        self.client.login(username='test_admin', password='password123')
        resp = self.client.post(
            reverse('shelter_allocate'),
            {
                'shelter': shelter.id,
                'incident': inc.id,
                'person_name': 'Ali Family',
                'family_count': 5,
                'contact_phone': '+8801700000000',
                'notes': 'Infant care required'
            }
        )
        self.assertEqual(resp.status_code, 302)
        shelter.refresh_from_db()
        self.assertEqual(shelter.occupied_capacity, 15)

        # Check event on incident
        event = IncidentEvent.objects.filter(incident=inc, event_type=EventType.SHELTER_ALLOCATED).first()
        self.assertIsNotNone(event)
        self.assertIn("Ali Family", event.description)

    def test_stats_api_endpoint(self):
        self.client.force_login(self.admin_user)
        resp = self.client.get(reverse('api_incident_stats'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('priorities', data)
        self.assertIn('statuses', data)
        self.assertIn('total_active', data)

    def test_stats_api_rejects_anonymous_and_non_admin_users(self):
        anonymous_response = self.client.get(reverse('api_incident_stats'))
        self.assertEqual(anonymous_response.status_code, 401)

        self.client.force_login(self.citizen_user)
        citizen_response = self.client.get(reverse('api_incident_stats'))
        self.assertEqual(citizen_response.status_code, 403)

    def test_resource_manager_can_allocate_shelter_capacity(self):
        resource_manager = User.objects.create_user(
            username='test_resource_manager',
            password='password123',
        )
        UserProfile.objects.create(user=resource_manager, role=UserRole.RESOURCE_MANAGER)
        shelter = Shelter.objects.create(
            name='Managed Shelter',
            address='Dhaka',
            total_capacity=20,
            occupied_capacity=2,
            status=ShelterStatus.OPEN,
        )
        self.client.force_login(resource_manager)

        response = self.client.post(reverse('shelter_allocate'), {
            'shelter': shelter.id,
            'person_name': 'Family',
            'family_count': 3,
            'contact_phone': '+8801700000000',
            'notes': '',
        })

        self.assertEqual(response.status_code, 302)
        shelter.refresh_from_db()
        self.assertEqual(shelter.occupied_capacity, 5)

    def test_responder_cannot_allocate_capacity_without_an_assigned_incident(self):
        shelter = Shelter.objects.create(
            name='Responder Test Shelter',
            address='Dhaka',
            total_capacity=20,
            occupied_capacity=2,
            status=ShelterStatus.OPEN,
        )
        self.client.force_login(self.resp_boat)

        response = self.client.post(reverse('shelter_allocate'), {
            'shelter': shelter.id,
            'person_name': 'Family',
            'family_count': 3,
            'contact_phone': '+8801700000000',
            'notes': '',
        })

        self.assertEqual(response.status_code, 403)
        shelter.refresh_from_db()
        self.assertEqual(shelter.occupied_capacity, 2)


class CriticalRepairRegressionTests(ResQGridBaseTestCase):
    def create_flood_incident(self, **overrides):
        data = {
            'reporter': self.citizen_user,
            'emergency_type': EmergencyType.FLOOD,
            'description': 'Flood response needed.',
            'contact_name': 'Citizen',
            'contact_phone': '+8801700000000',
            'location_name': 'Dhaka',
            'latitude': 23.8103,
            'longitude': 90.4125,
            'status': IncidentStatus.TRIAGED,
        }
        data.update(overrides)
        return Incident.objects.create(**data)

    @override_settings(DEBUG=False)
    def test_public_landing_page_hides_demo_credentials_outside_debug(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Quick Hackathon Testing Accounts')

    @override_settings(DEBUG=False, DEMO_PASSWORD='judge-only-password')
    def test_demo_password_is_never_rendered_in_production(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'judge-only-password')
        self.assertNotContains(response, '1-Click Hackathon Demo Credentials')

    @override_settings(DEBUG=True, DEMO_PASSWORD='temporarylocalpassword')
    def test_local_demo_login_uses_configured_password(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'temporarylocalpassword')

    @override_settings(DEBUG=True)
    @patch.dict('os.environ', {'RESQGRID_DEMO_PASSWORD': ''})
    def test_demo_seed_requires_explicit_password(self):
        with self.assertRaises(CommandError):
            call_command('seed_demo_data', stdout=None)

    @override_settings(DEBUG=True)
    @patch.dict('os.environ', {'RESQGRID_DEMO_PASSWORD': 'temporary-demo-password'})
    def test_demo_seed_creates_fictional_resources_and_uses_configured_password(self):
        call_command('seed_demo_data', stdout=None)

        demo_admin = User.objects.get(username='admin')
        self.assertTrue(demo_admin.check_password('temporary-demo-password'))
        self.assertEqual(Resource.objects.filter(name__contains='[SIMULATED]').count(), 4)
        self.assertTrue(UserProfile.objects.filter(role=UserRole.RESOURCE_MANAGER).exists())

    def test_priority_badge_palette_uses_severity_colors(self):
        self.assertEqual(priority_badge_class(PriorityLevel.CRITICAL), 'badge-priority-critical')
        self.assertEqual(priority_badge_class(PriorityLevel.HIGH), 'badge-priority-high')
        self.assertEqual(priority_badge_class(PriorityLevel.MEDIUM), 'badge-priority-medium')
        self.assertEqual(priority_badge_class(PriorityLevel.LOW), 'badge-priority-low')

    def test_sos_requires_login_and_persists_report_for_owner(self):
        url = reverse('incident_create')
        self.assertEqual(self.client.get(url).status_code, 302)

        self.client.force_login(self.citizen_user)
        response = self.client.post(url, {
            'reported_for': 'SELF',
            'emergency_type': EmergencyType.OTHER,
            'description': 'Smoke inside a residential building.',
            'contact_name': 'Citizen',
            'contact_phone': '+8801700000000',
            'affected_count': 1,
            'injured_count': 0,
            'trapped_count': 0,
            'has_vulnerable_people': '',
            'vulnerable_details': '',
            'access_difficulty': AccessDifficulty.EASY,
            'location_name': 'Dhaka',
            'latitude': '23.8103',
            'longitude': '90.4125',
            'is_gps_derived': 'false',
        })
        self.assertEqual(response.status_code, 302)
        incident = Incident.objects.get(reporter=self.citizen_user)
        self.assertEqual(incident.status, IncidentStatus.ASSIGNED)
        self.assertTrue(incident.events.filter(event_type=EventType.CREATED).exists())
        self.assertTrue(incident.events.filter(event_type=EventType.TRIAGED).exists())

    def test_login_preserves_whitespace_in_password(self):
        user = User.objects.create_user(username='space_password', password=' password123 ')
        UserProfile.objects.create(user=user, role=UserRole.CITIZEN)
        response = self.client.post(reverse('login'), {
            'username': 'space_password',
            'password': ' password123 ',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_registration_rejects_password_that_fails_configured_validator(self):
        from core.forms import CitizenRegistrationForm

        form = CitizenRegistrationForm(data={
            'username': 'new_citizen',
            'first_name': 'New',
            'last_name': 'Citizen',
            'email': 'new@example.com',
            'phone': '+8801700000000',
            'password': '123',
            'confirm_password': '123',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('password', form.errors)

    def test_logout_is_post_only(self):
        self.client.force_login(self.citizen_user)
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)
        response = self.client.post(reverse('logout'))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_incident_list_is_scoped_to_own_reports(self):
        own = self.create_flood_incident()
        other = self.create_flood_incident(
            reporter=self.resp_boat,
            location_name='Private location',
        )
        self.client.force_login(self.citizen_user)
        response = self.client.get(reverse('incident_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, own.incident_id)
        self.assertNotContains(response, other.incident_id)

    def test_workflow_action_get_requests_cannot_mutate_state(self):
        incident = self.create_flood_incident()
        assignment, _ = WorkflowEngine.dispatch_top_responder(incident)
        response = self.client.get(reverse('assignment_accept', args=[assignment.id]))
        self.assertEqual(response.status_code, 302)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, AssignmentStatus.PENDING)

        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('incident_retrigger_triage', args=[incident.incident_id]))
        self.assertEqual(response.status_code, 405)

    def test_matching_excludes_out_of_radius_and_capacity_reserved_responders(self):
        incident = self.create_flood_incident()
        self.resp_boat_profile.service_radius_km = 1
        self.resp_boat_profile.max_active_capacity = 1
        self.resp_boat_profile.save()
        self.resp_backup_boat_profile.service_radius_km = 1
        self.resp_backup_boat_profile.max_active_capacity = 1
        self.resp_backup_boat_profile.save()
        other_incident = self.create_flood_incident(location_name='Another incident')
        Assignment.objects.create(incident=other_incident, responder=self.resp_boat)

        matches, explanation = MatchingEngine.find_matches(
            incident,
            exclude_user_ids=[self.resp_no_boat.id],
        )
        self.assertNotIn(self.resp_boat.id, [match['responder'].id for match in matches])
        self.assertNotIn(self.resp_backup_boat.id, [match['responder'].id for match in matches])
        self.assertIn('capacity', explanation)

    def test_becoming_unavailable_reassigns_pending_mission(self):
        incident = self.create_flood_incident()
        first_assignment, _ = WorkflowEngine.dispatch_top_responder(incident)
        self.assertEqual(first_assignment.responder, self.resp_boat)

        self.resp_boat_profile.availability = AvailabilityStatus.OFFLINE
        self.resp_boat_profile.save()
        WorkflowEngine.reassign_pending_for_unavailable_responder(
            self.resp_boat, actor=self.admin_user
        )

        first_assignment.refresh_from_db()
        incident.refresh_from_db()
        next_assignment = Assignment.objects.get(
            incident=incident, status=AssignmentStatus.PENDING
        )
        self.assertEqual(first_assignment.status, AssignmentStatus.CANCELLED)
        self.assertEqual(next_assignment.responder, self.resp_backup_boat)
        self.assertEqual(incident.status, IncidentStatus.ASSIGNED)
        self.assertTrue(incident.events.filter(
            event_type=EventType.AUTO_REASSIGNED,
            description__contains='became unavailable',
        ).exists())

    def test_no_candidate_after_unavailability_leaves_incident_unassigned(self):
        incident = self.create_flood_incident()
        assignment, _ = WorkflowEngine.dispatch_top_responder(incident)
        self.resp_backup_boat_profile.availability = AvailabilityStatus.OFFLINE
        self.resp_backup_boat_profile.save()
        self.resp_boat_profile.availability = AvailabilityStatus.OFFLINE
        self.resp_boat_profile.save()

        WorkflowEngine.reassign_pending_for_unavailable_responder(
            assignment.responder, actor=self.admin_user
        )

        incident.refresh_from_db()
        self.assertEqual(incident.status, IncidentStatus.UNASSIGNED)
        self.assertIsNone(incident.assigned_responder)
        self.assertIn('zero eligible responders', incident.unassigned_reason.lower())

    def test_cancellation_cancels_pending_assignment_atomically(self):
        incident = self.create_flood_incident(status=IncidentStatus.ASSIGNED)
        assignment = Assignment.objects.create(
            incident=incident,
            responder=self.resp_boat,
            status=AssignmentStatus.PENDING,
        )
        incident.assigned_responder = self.resp_boat
        incident.save()

        WorkflowEngine.cancel_incident(incident, self.citizen_user, 'False alarm.')

        incident.refresh_from_db()
        assignment.refresh_from_db()
        self.assertEqual(incident.status, IncidentStatus.CANCELLED)
        self.assertIsNone(incident.assigned_responder)
        self.assertEqual(assignment.status, AssignmentStatus.CANCELLED)
        self.assertTrue(incident.events.filter(event_type=EventType.CANCELLED).exists())

    def test_retriage_preserves_existing_active_assignment_and_status(self):
        incident = self.create_flood_incident()
        assignment, _ = WorkflowEngine.dispatch_top_responder(incident)
        WorkflowEngine.process_new_incident(incident, actor=self.admin_user)

        incident.refresh_from_db()
        assignment.refresh_from_db()
        self.assertEqual(incident.status, IncidentStatus.ASSIGNED)
        self.assertEqual(incident.assigned_responder, assignment.responder)
        self.assertEqual(assignment.status, AssignmentStatus.PENDING)

    def test_responder_availability_post_reassigns_pending_assignment(self):
        incident = self.create_flood_incident()
        assignment, _ = WorkflowEngine.dispatch_top_responder(incident)
        self.client.force_login(self.resp_boat)

        response = self.client.post(reverse('responder_toggle_availability'), {
            'availability': AvailabilityStatus.OFFLINE,
        })

        self.assertEqual(response.status_code, 302)
        assignment.refresh_from_db()
        incident.refresh_from_db()
        self.assertEqual(assignment.status, AssignmentStatus.CANCELLED)
        self.assertEqual(incident.assigned_responder, self.resp_backup_boat)

    def test_assignment_acceptance_is_limited_to_assigned_responder(self):
        incident = self.create_flood_incident()
        assignment, _ = WorkflowEngine.dispatch_top_responder(incident)
        self.client.force_login(self.citizen_user)

        response = self.client.post(reverse('assignment_accept', args=[assignment.id]))

        self.assertEqual(response.status_code, 403)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, AssignmentStatus.PENDING)

    def test_unassigned_citizen_cannot_change_incident_status_or_post_notes(self):
        incident = self.create_flood_incident(reporter=self.resp_boat)
        self.client.force_login(self.citizen_user)

        status_response = self.client.post(
            reverse('incident_update_status', args=[incident.incident_id]),
            {'status': IncidentStatus.RESOLVED, 'notes': 'Unauthorized update'},
        )
        note_response = self.client.post(
            reverse('incident_post_note', args=[incident.incident_id]),
            {'note': 'Unauthorized note'},
        )

        self.assertEqual(status_response.status_code, 403)
        self.assertEqual(note_response.status_code, 403)
        incident.refresh_from_db()
        self.assertNotEqual(incident.status, IncidentStatus.RESOLVED)
        self.assertFalse(incident.events.filter(description__contains='Unauthorized note').exists())

    def test_anonymous_live_map_does_not_expose_operational_incidents(self):
        incident = self.create_flood_incident()
        response = self.client.get(reverse('map_view'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['incidents_json'], [])
        self.assertNotContains(response, incident.incident_id)

    def test_live_map_data_returns_current_database_records_for_admin(self):
        incident = self.create_flood_incident(description='Flooded road near the clinic.')
        shelter = Shelter.objects.create(
            name='Live Map Shelter',
            address='Sylhet',
            total_capacity=40,
            occupied_capacity=17,
            status=ShelterStatus.OPEN,
        )
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse('map_data'))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['incidents'][0]['id'], incident.incident_id)
        self.assertEqual(data['incidents'][0]['description'], incident.description)
        self.assertEqual(data['shelters'][0]['occupied'], shelter.occupied_capacity)
        boat_responder = next(item for item in data['responders'] if item['id'] == self.resp_boat_profile.id)
        self.assertEqual(boat_responder['availability'], AvailabilityStatus.AVAILABLE)
        self.assertEqual(boat_responder['phone'], '+8801700000003')

    def test_live_map_data_keeps_anonymous_incidents_private(self):
        incident = self.create_flood_incident()

        response = self.client.get(reverse('map_data'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['incidents'], [])
        self.assertNotContains(response, incident.incident_id)

    def test_responder_map_is_limited_to_assigned_incidents_and_redacts_other_contacts(self):
        assigned_incident = self.create_flood_incident(
            assigned_responder=self.resp_boat,
            status=IncidentStatus.ASSIGNED,
        )
        other_incident = self.create_flood_incident(
            assigned_responder=self.resp_backup_boat,
            status=IncidentStatus.ASSIGNED,
        )
        self.client.force_login(self.resp_boat)

        response = self.client.get(reverse('map_data'))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([item['id'] for item in data['incidents']], [assigned_incident.incident_id])
        self.assertNotIn(other_incident.incident_id, [item['id'] for item in data['incidents']])
        other_responder = next(
            item for item in data['responders'] if item['id'] == self.resp_backup_boat_profile.id
        )
        self.assertEqual(other_responder['phone'], '')
        self.assertEqual(other_responder['org'], '')

    def test_database_health_check_returns_ready(self):
        response = self.client.get(reverse('health_check'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_authorized_incident_detail_renders_its_map(self):
        incident = self.create_flood_incident(reporter=self.citizen_user)
        self.client.force_login(self.citizen_user)

        response = self.client.get(reverse('incident_detail', args=[incident.incident_id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="incident-map"')

    def test_citizen_cannot_allocate_shelter_capacity_to_another_users_incident(self):
        shelter = Shelter.objects.create(
            name='Test Shelter',
            address='Dhaka',
            total_capacity=20,
            occupied_capacity=2,
            status=ShelterStatus.OPEN,
        )
        other_incident = self.create_flood_incident(reporter=self.resp_boat)
        self.client.force_login(self.citizen_user)

        response = self.client.post(reverse('shelter_allocate'), {
            'shelter': shelter.id,
            'incident': other_incident.id,
            'person_name': 'Family',
            'family_count': 3,
            'contact_phone': '+8801700000000',
            'notes': '',
        })

        shelter.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(shelter.occupied_capacity, 2)
        self.assertFalse(shelter.allocations.exists())

    def test_admin_can_register_and_adjust_resources(self):
        self.client.force_login(self.admin_user)
        create_response = self.client.post(reverse('resource_create'), {
            'name': 'Water Purification Tablets',
            'category': ResourceCategory.WATER,
            'quantity': 100,
            'unit': 'packs',
            'location_name': 'Dhaka Central Warehouse',
            'latitude': '23.8103',
            'longitude': '90.4125',
            'shelter': '',
            'status': ResourceStatus.AVAILABLE,
        })
        self.assertEqual(create_response.status_code, 302)
        resource = Resource.objects.get(name='Water Purification Tablets')

        adjust_response = self.client.post(
            reverse('resource_adjust_quantity', args=[resource.id]),
            {'quantity_change': -25},
        )
        self.assertEqual(adjust_response.status_code, 302)
        resource.refresh_from_db()
        self.assertEqual(resource.quantity, 75)
        self.assertEqual(resource.status, ResourceStatus.RESERVED)

    def test_citizen_cannot_manage_resources(self):
        resource = Resource.objects.create(
            name='Blankets',
            category=ResourceCategory.BLANKETS_CLOTHING,
            quantity=20,
            unit='units',
        )
        self.client.force_login(self.citizen_user)

        list_response = self.client.get(reverse('resource_list'))
        adjust_response = self.client.post(
            reverse('resource_adjust_quantity', args=[resource.id]),
            {'quantity_change': -5},
        )

        self.assertEqual(list_response.status_code, 403)
        self.assertEqual(adjust_response.status_code, 403)
        resource.refresh_from_db()
        self.assertEqual(resource.quantity, 20)

    def test_resource_quantity_cannot_be_reduced_below_zero(self):
        resource = Resource.objects.create(
            name='Medical Kits',
            category=ResourceCategory.MEDICAL_SUPPLIES,
            quantity=2,
            unit='kits',
        )
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse('resource_adjust_quantity', args=[resource.id]),
            {'quantity_change': -3},
        )

        self.assertEqual(response.status_code, 302)
        resource.refresh_from_db()
        self.assertEqual(resource.quantity, 2)

    def test_login_throttles_repeated_failed_attempts(self):
        cache.clear()
        for _ in range(5):
            response = self.client.post(reverse('login'), {
                'username': 'test_citizen',
                'password': 'wrong-password',
            })
            self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse('login'), {
            'username': 'test_citizen',
            'password': 'password123',
        })
        self.assertContains(response, 'Too many unsuccessful login attempts')

    def test_admin_can_create_and_edit_shelter(self):
        self.client.force_login(self.admin_user)
        create_response = self.client.post(reverse('shelter_create'), {
            'name': 'Test Relief Shelter',
            'address': 'Dhaka',
            'latitude': '23.8103',
            'longitude': '90.4125',
            'total_capacity': 100,
            'occupied_capacity': 10,
            'has_food': 'on',
            'has_water': 'on',
            'has_medical': 'on',
            'status': ShelterStatus.OPEN,
            'contact_person': 'Test Manager',
            'contact_phone': '+8801700000000',
        })
        self.assertEqual(create_response.status_code, 302)
        shelter = Shelter.objects.get(name='Test Relief Shelter')

        edit_response = self.client.post(reverse('shelter_edit', args=[shelter.id]), {
            'name': 'Updated Relief Shelter',
            'address': 'Mirpur',
            'latitude': '23.8200',
            'longitude': '90.4200',
            'total_capacity': 125,
            'occupied_capacity': 20,
            'has_food': 'on',
            'has_water': '',
            'has_medical': 'on',
            'status': ShelterStatus.OPEN,
            'contact_person': 'Updated Manager',
            'contact_phone': '+8801700000099',
        })
        self.assertEqual(edit_response.status_code, 302)
        shelter.refresh_from_db()
        self.assertEqual(shelter.name, 'Updated Relief Shelter')
        self.assertEqual(shelter.total_capacity, 125)
        self.assertFalse(shelter.has_water)

    def test_citizen_cannot_create_or_edit_shelter(self):
        shelter = Shelter.objects.create(
            name='Private Shelter',
            address='Dhaka',
            total_capacity=50,
            occupied_capacity=5,
        )
        self.client.force_login(self.citizen_user)

        create_response = self.client.get(reverse('shelter_create'))
        edit_response = self.client.post(reverse('shelter_edit', args=[shelter.id]), {
            'name': 'Unauthorized Edit',
        })

        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(edit_response.status_code, 403)
        shelter.refresh_from_db()
        self.assertEqual(shelter.name, 'Private Shelter')

    def test_resource_manager_can_manage_resources_and_shelters(self):
        manager = User.objects.create_user(username='resource_manager_test', password='password123')
        UserProfile.objects.create(user=manager, role=UserRole.RESOURCE_MANAGER)
        self.client.force_login(manager)

        shelter_response = self.client.get(reverse('shelter_create'))
        resource_response = self.client.get(reverse('resource_create'))

        self.assertEqual(shelter_response.status_code, 200)
        self.assertEqual(resource_response.status_code, 200)

    def test_my_incident_status_api_is_scoped_to_caller(self):
        own = self.create_flood_incident(reporter=self.citizen_user)
        other = self.create_flood_incident(reporter=self.resp_boat)
        self.client.force_login(self.citizen_user)

        response = self.client.get(reverse('api_my_incident_status'))

        self.assertEqual(response.status_code, 200)
        ids = [item['id'] for item in response.json()['incidents']]
        self.assertIn(own.incident_id, ids)
        self.assertNotIn(other.incident_id, ids)

    def test_password_change_requires_login_and_changes_password(self):
        anonymous = self.client.get(reverse('password_change'))
        self.assertEqual(anonymous.status_code, 302)

        self.client.force_login(self.citizen_user)
        response = self.client.post(reverse('password_change'), {
            'old_password': 'password123',
            'new_password1': 'new-strong-password-789',
            'new_password2': 'new-strong-password-789',
        })
        self.assertEqual(response.status_code, 302)
        self.citizen_user.refresh_from_db()
        self.assertTrue(self.citizen_user.check_password('new-strong-password-789'))
