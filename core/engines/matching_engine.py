"""
Module C: Responder Management & Intelligent Matching Engine
Discovers, validates, and ranks emergency responders for incident dispatch.
Strictly enforces capability filters and generates human-readable match explanations.
"""

from django.db.models import Count

from core.models import (
    Assignment, AssignmentStatus, ResponderProfile,
    VerificationStatus, AvailabilityStatus
)


class MatchingEngine:
    """
    Intelligent dispatch matching engine.
    Filters out ineligible responders and ranks verified candidates based on:
    - Skill congruence (mandatory)
    - Equipment availability (mandatory)
    - Verification & availability status (mandatory)
    - Active capacity limits (mandatory)
    - Proximity & travel distance (ranking factor)
    - Current workload headroom (ranking factor)
    """

    @classmethod
    def find_matches(cls, incident, exclude_user_ids=None):
        """
        Finds and ranks all eligible responders for a given incident.
        Returns a list of dicts:
        [
            {
                'responder': User,
                'profile': ResponderProfile,
                'score': float,
                'distance_km': float,
                'explanation': str,
                'is_eligible': True
            },
            ...
        ]
        Also returns a summary message if no matches exist.
        """
        required_skills = incident.get_required_skills()
        required_equipment = incident.get_required_equipment()
        exclude_user_ids = set(exclude_user_ids or [])

        # Query all responder profiles with select_related user
        candidates = ResponderProfile.objects.select_related('user', 'user__profile').all()
        pending_counts = dict(
            Assignment.objects.filter(status=AssignmentStatus.PENDING)
            .values('responder_id')
            .annotate(total=Count('id'))
            .values_list('responder_id', 'total')
        )

        eligible_matches = []
        ineligible_reasons = []

        for profile in candidates:
            user = profile.user
            if user.id in exclude_user_ids:
                ineligible_reasons.append(f"{user.get_full_name() or user.username}: Already previously dispatched or rejected this incident.")
                continue

            # 1. Verification Check (Mandatory)
            if profile.verification_status != VerificationStatus.VERIFIED:
                ineligible_reasons.append(f"{user.get_full_name() or user.username}: Account status is {profile.get_verification_status_display()} (Admin verification required).")
                continue

            # 2. Availability Check (Mandatory)
            if profile.availability != AvailabilityStatus.AVAILABLE:
                ineligible_reasons.append(f"{user.get_full_name() or user.username}: Status is {profile.get_availability_display()}.")
                continue

            # 3. Capacity Check (Mandatory)
            reserved_assignments = pending_counts.get(user.id, 0)
            occupied_capacity = profile.current_active_assignments + reserved_assignments
            if occupied_capacity >= profile.max_active_capacity:
                ineligible_reasons.append(
                    f"{user.get_full_name() or user.username}: Operating at max active or reserved capacity "
                    f"({profile.current_active_assignments} active, {reserved_assignments} pending/"
                    f"{profile.max_active_capacity} slots)."
                )
                continue

            # 4. Required Skills Check (Mandatory)
            missing_skills = [s for s in required_skills if s.upper() not in set(profile.get_skills_list())]
            if missing_skills:
                ineligible_reasons.append(f"{user.get_full_name() or user.username}: Missing mandatory rescue skills: {', '.join(missing_skills)}.")
                continue

            # 5. Required Equipment Check (Mandatory)
            missing_equipment = [e for e in required_equipment if e.upper() not in set(profile.get_equipment_list())]
            if missing_equipment:
                ineligible_reasons.append(f"{user.get_full_name() or user.username}: Missing required emergency equipment: {', '.join(missing_equipment)}.")
                continue

            # Candidate meets ALL mandatory criteria! Compute ranking score.
            distance = profile.distance_to(incident.latitude, incident.longitude)
            if distance > profile.service_radius_km:
                ineligible_reasons.append(
                    f"{user.get_full_name() or user.username}: Incident is {distance} km away, "
                    f"outside the {profile.service_radius_km} km service radius."
                )
                continue

            # Ranking scoring formula (0 - 100):
            # Proximity score (0-50 pts): closer = higher
            # Max radius comparison (e.g. within 30km: 0km = 50pts, 25km = 10pts)
            if distance <= 2.0:
                proximity_score = 50.0
            elif distance <= 10.0:
                proximity_score = 40.0
            elif distance <= 25.0:
                proximity_score = 30.0
            elif distance <= 50.0:
                proximity_score = 20.0
            else:
                proximity_score = 10.0

            # Capacity headroom score (0-30 pts):
            free_slots = profile.max_active_capacity - occupied_capacity
            capacity_score = min(30.0, free_slots * 15.0)

            # Skill & Equipment breadth score (0-20 pts)
            extra_skills = len(profile.get_skills_list()) - len(required_skills)
            extra_equip = len(profile.get_equipment_list()) - len(required_equipment)
            breadth_score = min(20.0, max(0, extra_skills * 3.0) + max(0, extra_equip * 2.0))

            total_match_score = round(proximity_score + capacity_score + breadth_score, 1)

            # Explanation narrative
            explanation = (
                f"Match Score: {total_match_score}/100. "
                f"Verified responder with all required skills ({', '.join(required_skills)}) "
                f"and required gear ({', '.join(required_equipment)}). "
                f"Estimated distance: {distance} km. "
                f"Available capacity: {free_slots} free slot(s) ({profile.current_active_assignments}/{profile.max_active_capacity} busy)."
            )

            eligible_matches.append({
                'responder': user,
                'profile': profile,
                'score': total_match_score,
                'distance_km': distance,
                'explanation': explanation,
                'is_eligible': True,
            })

        # Sort eligible matches by highest score, then closest distance
        eligible_matches.sort(key=lambda m: (-m['score'], m['distance_km']))

        if not eligible_matches:
            # Generate actionable unassigned diagnostic explanation
            summary_reasons = "; ".join(ineligible_reasons[:4]) if ineligible_reasons else "No responders registered in the system."
            no_match_explanation = (
                f"Automatic matching found zero eligible responders for {incident.incident_id}. "
                f"Required skills: [{', '.join(required_skills)}]. Required equipment: [{', '.join(required_equipment)}]. "
                f"Eligibility failures: {summary_reasons}."
            )
            return [], no_match_explanation

        return eligible_matches, f"Found {len(eligible_matches)} eligible responder(s) ranked by distance and workload capacity."
