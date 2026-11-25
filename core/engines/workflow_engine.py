"""
Module D: Automated Emergency Workflow Engine (A07 Automated Multi-Step Workflow)
Orchestrates the entire multi-step emergency response lifecycle:
Creation -> Triage -> Match -> Dispatch -> Acceptance/Rejection -> Auto-Reassignment -> Response -> Resolution.
"""

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from core.models import (
    Incident, IncidentStatus, Assignment, AssignmentStatus,
    IncidentEvent, EventType, AvailabilityStatus,
    ResponderProfile, VerificationStatus
)
from core.engines.priority_engine import PriorityEngine
from core.engines.matching_engine import MatchingEngine


class WorkflowEngine:
    """
    Automated state machine and workflow coordinator.
    Enforces atomic transitions, duplicate assignment guards, automatic failover
    re-dispatching, and comprehensive event audit logging.
    """

    @classmethod
    @transaction.atomic
    def process_new_incident(cls, incident, actor=None, auto_dispatch=True):
        """
        Step 1 & 2: Evaluate priority and triage incident.
        Optionally step 3 & 4: Automatically find and dispatch top eligible responder.
        """
        original_incident = incident
        incident = Incident.objects.select_for_update().get(pk=incident.pk)
        previous_status = incident.status
        has_active_assignment = Assignment.objects.filter(
            incident=incident,
            status__in=[AssignmentStatus.PENDING, AssignmentStatus.ACCEPTED]
        ).exists()

        # Module B: Calculate Priority
        score, level, explanation = PriorityEngine.evaluate(incident)
        incident.priority_score = score
        incident.priority_level = level
        incident.priority_explanation = explanation
        if not has_active_assignment and incident.status in [
            IncidentStatus.REPORTED, IncidentStatus.TRIAGED, IncidentStatus.UNASSIGNED
        ]:
            incident.status = IncidentStatus.TRIAGED
        incident.save()
        cls._sync_incident(original_incident, incident)

        # Log Triage Event
        IncidentEvent.objects.create(
            incident=incident,
            actor=actor or incident.reporter,
            event_type=EventType.TRIAGED,
            from_status=previous_status,
            to_status=incident.status,
            description=f"Automated Triage Engine computed score {score} ({level}). Explanation: {explanation[:120]}..."
        )

        # Module C & D: Automated matching and dispatch
        if auto_dispatch and not has_active_assignment and incident.status == IncidentStatus.TRIAGED:
            cls.dispatch_top_responder(incident, actor=actor)

        cls._sync_incident(original_incident, incident)
        return original_incident

    @staticmethod
    def _sync_incident(target, source):
        for field in (
            'status', 'priority_score', 'priority_level', 'priority_explanation',
            'unassigned_reason', 'assigned_responder', 'resolved_at', 'updated_at'
        ):
            setattr(target, field, getattr(source, field))

    @classmethod
    def _find_locked_top_match(cls, incident, excluded_user_ids):
        matches, explanation = MatchingEngine.find_matches(
            incident, exclude_user_ids=excluded_user_ids
        )
        while matches:
            candidate = matches[0]
            ResponderProfile.objects.select_for_update().filter(
                user=candidate['responder']
            ).first()
            refreshed_matches, explanation = MatchingEngine.find_matches(
                incident, exclude_user_ids=excluded_user_ids
            )
            selected = next(
                (match for match in refreshed_matches
                 if match['responder'].id == candidate['responder'].id),
                None
            )
            if selected:
                return selected, explanation
            matches = refreshed_matches
        return None, explanation

    @classmethod
    @transaction.atomic
    def dispatch_top_responder(cls, incident, actor=None):
        """
        Dispatches the highest-ranked eligible responder.
        If no responder is eligible, marks the incident UNASSIGNED with a clear reason.
        """
        original_incident = incident
        incident = Incident.objects.select_for_update().get(pk=incident.pk)

        # Guard against duplicate active assignment
        active_assignment = Assignment.objects.filter(
            incident=incident,
            status__in=[AssignmentStatus.PENDING, AssignmentStatus.ACCEPTED]
        ).first()
        if active_assignment:
            raise ValidationError(f"Incident {incident.incident_id} already has an active assignment with {active_assignment.responder.username}.")

        # Find previously attempted or rejected responders for this incident
        dispatched_user_ids = list(Assignment.objects.filter(incident=incident).values_list('responder_id', flat=True))

        top_match, match_info = cls._find_locked_top_match(incident, dispatched_user_ids)

        if not top_match:
            # Step 7: Fallback to UNASSIGNED
            old_status = incident.status
            incident.status = IncidentStatus.UNASSIGNED
            incident.unassigned_reason = match_info
            incident.assigned_responder = None
            incident.save()
            cls._sync_incident(original_incident, incident)

            IncidentEvent.objects.create(
                incident=incident,
                actor=actor,
                event_type=EventType.UNASSIGNED_ALERT,
                from_status=old_status,
                to_status=IncidentStatus.UNASSIGNED,
                description=f"Auto-dispatch failed: {match_info}"
            )
            return None, match_info

        # Pick top ranked responder
        responder_user = top_match['responder']

        assignment = Assignment.objects.create(
            incident=incident,
            responder=responder_user,
            assigned_by=actor,
            status=AssignmentStatus.PENDING,
            match_score=top_match['score'],
            match_explanation=top_match['explanation']
        )

        old_status = incident.status
        incident.status = IncidentStatus.ASSIGNED
        incident.assigned_responder = responder_user
        incident.unassigned_reason = ''
        incident.save()
        cls._sync_incident(original_incident, incident)

        IncidentEvent.objects.create(
            incident=incident,
            actor=actor,
            event_type=EventType.ASSIGNED,
            from_status=old_status,
            to_status=IncidentStatus.ASSIGNED,
            description=(
                f"Dispatched to responder {responder_user.get_full_name() or responder_user.username}. "
                f"Match Score: {top_match['score']}. Distance: {top_match['distance_km']} km."
            )
        )

        return assignment, f"Successfully dispatched to {responder_user.username}."

    @classmethod
    @transaction.atomic
    def accept_assignment(cls, assignment, responder_user, notes=''):
        """
        Step 5 (Accept): Responder accepts the emergency assignment.
        Moves incident to ACCEPTED and updates responder active workload.
        """
        assignment = Assignment.objects.select_for_update().select_related('incident').get(pk=assignment.pk)
        if assignment.responder != responder_user:
            raise ValidationError("You are not authorized to accept this assignment.")

        if assignment.status != AssignmentStatus.PENDING:
            raise ValidationError(f"Assignment is not pending (current status: {assignment.status}).")

        incident = Incident.objects.select_for_update().get(pk=assignment.incident_id)
        incident.validate_transition(IncidentStatus.ACCEPTED)

        responder_profile = ResponderProfile.objects.select_for_update().filter(user=responder_user).first()
        if not responder_profile:
            raise ValidationError("This account does not have a responder profile.")
        if responder_profile.verification_status != VerificationStatus.VERIFIED:
            raise ValidationError("Only verified responders may accept assignments.")
        if responder_profile.availability != AvailabilityStatus.AVAILABLE:
            raise ValidationError("Set your availability to Available before accepting an assignment.")
        pending_elsewhere = Assignment.objects.filter(
            responder=responder_user,
            status=AssignmentStatus.PENDING
        ).exclude(pk=assignment.pk).count()
        if responder_profile.current_active_assignments + pending_elsewhere >= responder_profile.max_active_capacity:
            raise ValidationError("Accepting this assignment would exceed your active or reserved capacity.")

        # Update assignment
        assignment.status = AssignmentStatus.ACCEPTED
        assignment.responded_at = timezone.now()
        if notes:
            assignment.notes = f"{assignment.notes}\nAcceptance Notes: {notes}".strip()
        assignment.save()

        # Update incident
        old_status = incident.status
        incident.status = IncidentStatus.ACCEPTED
        incident.assigned_responder = responder_user
        incident.save()

        # Update responder capacity
        responder_profile.current_active_assignments += 1
        if responder_profile.current_active_assignments >= responder_profile.max_active_capacity:
            responder_profile.availability = AvailabilityStatus.BUSY
        responder_profile.save()

        # Event log
        IncidentEvent.objects.create(
            incident=incident,
            actor=responder_user,
            event_type=EventType.ACCEPTED,
            from_status=old_status,
            to_status=IncidentStatus.ACCEPTED,
            description=f"Responder {responder_user.get_full_name() or responder_user.username} accepted the assignment. Active mission initiated."
        )

        return assignment

    @classmethod
    @transaction.atomic
    def reject_assignment(cls, assignment, responder_user, reason=''):
        """
        Step 6: Responder rejects assignment.
        Triggers Step 6 & 7: Automated search and reassignment to next candidate.
        """
        assignment = Assignment.objects.select_for_update().select_related('incident').get(pk=assignment.pk)
        if assignment.responder != responder_user:
            raise ValidationError("You are not authorized to reject this assignment.")

        if assignment.status != AssignmentStatus.PENDING:
            raise ValidationError(f"Assignment is not in pending state (status: {assignment.status}).")

        incident = Incident.objects.select_for_update().get(pk=assignment.incident_id)

        # Update current assignment to REJECTED
        assignment.status = AssignmentStatus.REJECTED
        assignment.responded_at = timezone.now()
        assignment.rejection_reason = reason or "Responder declined without specific reason."
        assignment.save()

        # Log rejection event
        IncidentEvent.objects.create(
            incident=incident,
            actor=responder_user,
            event_type=EventType.REJECTED,
            from_status=incident.status,
            to_status=incident.status,
            description=f"Assignment declined by {responder_user.username}. Reason: {assignment.rejection_reason}"
        )

        # Step 6 & 7: Automated failover reassignment
        dispatched_user_ids = list(Assignment.objects.filter(incident=incident).values_list('responder_id', flat=True))
        next_match, match_info = cls._find_locked_top_match(incident, dispatched_user_ids)

        if next_match:
            # Reassign to next best candidate
            next_responder = next_match['responder']

            new_assignment = Assignment.objects.create(
                incident=incident,
                responder=next_responder,
                assigned_by=None,
                status=AssignmentStatus.PENDING,
                match_score=next_match['score'],
                match_explanation=next_match['explanation']
            )

            incident.assigned_responder = next_responder
            incident.status = IncidentStatus.ASSIGNED
            incident.unassigned_reason = ''
            incident.save()

            IncidentEvent.objects.create(
                incident=incident,
                actor=None,
                event_type=EventType.AUTO_REASSIGNED,
                from_status=IncidentStatus.ASSIGNED,
                to_status=IncidentStatus.ASSIGNED,
                description=(
                    f"Automated workflow failover: Dispatched next eligible responder "
                    f"{next_responder.get_full_name() or next_responder.username} "
                    f"(Score: {next_match['score']}, Distance: {next_match['distance_km']} km)."
                )
            )
            return new_assignment, f"Reassigned automatically to {next_responder.username}."
        else:
            # Step 7: No more candidates -> mark UNASSIGNED
            old_status = incident.status
            incident.status = IncidentStatus.UNASSIGNED
            incident.assigned_responder = None
            incident.unassigned_reason = (
                f"Previous responder ({responder_user.username}) rejected assignment. "
                f"Automated failover found no additional eligible responders: {match_info}"
            )
            incident.save()

            IncidentEvent.objects.create(
                incident=incident,
                actor=None,
                event_type=EventType.UNASSIGNED_ALERT,
                from_status=old_status,
                to_status=IncidentStatus.UNASSIGNED,
                description=f"Reassignment failed. Incident marked UNASSIGNED: {incident.unassigned_reason}"
            )
            return None, "No further eligible responders. Incident marked UNASSIGNED."

    @classmethod
    @transaction.atomic
    def update_to_responding(cls, incident, responder_user, progress_notes=''):
        """
        Step 8: Responder marks that they are en route / actively responding on scene.
        """
        incident = Incident.objects.select_for_update().get(pk=incident.pk)
        if incident.assigned_responder != responder_user and not responder_user.is_superuser:
            raise ValidationError("Only the assigned responder can update response progress.")

        incident.validate_transition(IncidentStatus.RESPONDING)

        old_status = incident.status
        incident.status = IncidentStatus.RESPONDING
        incident.save()

        active_assignment = Assignment.objects.filter(
            incident=incident,
            responder=responder_user,
            status=AssignmentStatus.ACCEPTED
        ).first()
        if active_assignment and progress_notes:
            active_assignment.notes = f"{active_assignment.notes}\nProgress Update: {progress_notes}".strip()
            active_assignment.save()

        IncidentEvent.objects.create(
            incident=incident,
            actor=responder_user,
            event_type=EventType.STATUS_UPDATE,
            from_status=old_status,
            to_status=IncidentStatus.RESPONDING,
            description=f"Responder deployed on-scene. Progress: {progress_notes or 'Active rescue/response underway.'}"
        )
        return incident

    @classmethod
    @transaction.atomic
    def resolve_incident(cls, incident, actor, resolution_notes=''):
        """
        Step 9: Mark incident RESOLVED.
        Releases responder capacity and updates final audit history.
        """
        incident = Incident.objects.select_for_update().get(pk=incident.pk)
        incident.validate_transition(IncidentStatus.RESOLVED)

        old_status = incident.status
        incident.status = IncidentStatus.RESOLVED
        incident.resolved_at = timezone.now()
        incident.save()

        # Update assignment to COMPLETED
        active_assignment = Assignment.objects.filter(
            incident=incident,
            status__in=[AssignmentStatus.ACCEPTED, AssignmentStatus.PENDING]
        ).first()

        if active_assignment:
            was_accepted = active_assignment.status == AssignmentStatus.ACCEPTED
            active_assignment.status = AssignmentStatus.COMPLETED
            if resolution_notes:
                active_assignment.notes = f"{active_assignment.notes}\nResolution: {resolution_notes}".strip()
            active_assignment.save()

            # Free responder capacity
            responder_profile = ResponderProfile.objects.select_for_update().filter(
                user=active_assignment.responder
            ).first()
            if responder_profile and was_accepted:
                responder_profile.current_active_assignments = max(0, responder_profile.current_active_assignments - 1)
                if responder_profile.availability == AvailabilityStatus.BUSY:
                    responder_profile.availability = AvailabilityStatus.AVAILABLE
                responder_profile.save()

        IncidentEvent.objects.create(
            incident=incident,
            actor=actor,
            event_type=EventType.RESOLVED,
            from_status=old_status,
            to_status=IncidentStatus.RESOLVED,
            description=f"Emergency marked RESOLVED by {actor.username}. Resolution notes: {resolution_notes or 'Mission successfully concluded.'}"
        )

        return incident

    @classmethod
    @transaction.atomic
    def cancel_incident(cls, incident, actor, reason=''):
        incident = Incident.objects.select_for_update().get(pk=incident.pk)
        incident.validate_transition(IncidentStatus.CANCELLED)
        previous_status = incident.status
        assignments = list(
            Assignment.objects.select_for_update().filter(
                incident=incident,
                status__in=[AssignmentStatus.PENDING, AssignmentStatus.ACCEPTED]
            ).select_related('responder')
        )
        for assignment in assignments:
            was_accepted = assignment.status == AssignmentStatus.ACCEPTED
            assignment.status = AssignmentStatus.CANCELLED
            assignment.notes = f"{assignment.notes}\nCancelled: {reason or 'Incident cancelled.'}".strip()
            assignment.save(update_fields=['status', 'notes'])
            if was_accepted:
                responder_profile = ResponderProfile.objects.select_for_update().filter(
                    user=assignment.responder
                ).first()
                if responder_profile:
                    responder_profile.current_active_assignments = max(
                        0, responder_profile.current_active_assignments - 1
                    )
                    if responder_profile.availability == AvailabilityStatus.BUSY:
                        responder_profile.availability = AvailabilityStatus.AVAILABLE
                    responder_profile.save()

        incident.status = IncidentStatus.CANCELLED
        incident.assigned_responder = None
        incident.save()
        IncidentEvent.objects.create(
            incident=incident,
            actor=actor,
            event_type=EventType.CANCELLED,
            from_status=previous_status,
            to_status=IncidentStatus.CANCELLED,
            description=f"Incident cancelled by {actor.username}. Reason: {reason or 'No longer required.'}"
        )
        return incident

    @classmethod
    @transaction.atomic
    def reassign_pending_for_unavailable_responder(cls, responder, actor=None):
        pending_assignments = list(
            Assignment.objects.select_for_update()
            .filter(responder=responder, status=AssignmentStatus.PENDING)
            .select_related('incident')
        )
        reassigned = 0
        for assignment in pending_assignments:
            incident = Incident.objects.select_for_update().get(pk=assignment.incident_id)
            assignment.status = AssignmentStatus.CANCELLED
            assignment.notes = f"{assignment.notes}\nCancelled: responder became unavailable.".strip()
            assignment.save(update_fields=['status', 'notes'])
            if incident.assigned_responder_id != responder.id:
                continue

            IncidentEvent.objects.create(
                incident=incident,
                actor=actor,
                event_type=EventType.AUTO_REASSIGNED,
                from_status=incident.status,
                to_status=incident.status,
                description=(
                    f"Pending assignment to {responder.get_full_name() or responder.username} "
                    "was cancelled because the responder became unavailable; automatic reassignment started."
                )
            )
            cls.dispatch_top_responder(incident, actor=actor)
            reassigned += 1
        return reassigned

    @classmethod
    @transaction.atomic
    def manual_dispatch(cls, incident, responder, actor):
        incident = Incident.objects.select_for_update().get(pk=incident.pk)
        if incident.status not in [
            IncidentStatus.REPORTED, IncidentStatus.TRIAGED, IncidentStatus.UNASSIGNED
        ]:
            raise ValidationError("Manual dispatch is only available for reported, triaged, or unassigned incidents.")
        if Assignment.objects.filter(
            incident=incident,
            status__in=[AssignmentStatus.PENDING, AssignmentStatus.ACCEPTED]
        ).exists():
            raise ValidationError("This incident already has an active responder assignment.")

        excluded_ids = Assignment.objects.filter(incident=incident).values_list('responder_id', flat=True)
        ResponderProfile.objects.select_for_update().filter(user=responder).first()
        matches, match_info = MatchingEngine.find_matches(incident, exclude_user_ids=excluded_ids)
        selected_match = next((match for match in matches if match['responder'].id == responder.id), None)
        if not selected_match:
            raise ValidationError(f"Responder is not currently eligible for this incident. {match_info}")

        assignment = Assignment.objects.create(
            incident=incident,
            responder=responder,
            assigned_by=actor,
            status=AssignmentStatus.PENDING,
            match_score=selected_match['score'],
            match_explanation=f"Manual dispatch by {actor.username}. {selected_match['explanation']}"
        )
        previous_status = incident.status
        incident.status = IncidentStatus.ASSIGNED
        incident.assigned_responder = responder
        incident.unassigned_reason = ''
        incident.save()
        IncidentEvent.objects.create(
            incident=incident,
            actor=actor,
            event_type=EventType.ASSIGNED,
            from_status=previous_status,
            to_status=IncidentStatus.ASSIGNED,
            description=f"Manually assigned to {responder.get_full_name() or responder.username} by administrator."
        )
        return assignment
