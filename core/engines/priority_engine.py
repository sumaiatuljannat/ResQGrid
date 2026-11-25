"""
Module B: Intelligent Emergency Priority Engine (A02 Intelligent Decisions & Optimization)
Rule-based, transparent, and explainable emergency triage scoring.

Disclaimer: Rule-based prioritization for humanitarian resource allocation.
Does NOT make medical diagnoses or replace professional emergency services judgment.
"""

from core.models import IncidentStatus, PriorityLevel, AccessDifficulty


class PriorityEngine:
    """
    Calculates transparent triage priority score (0-100+) and generates
    human-readable, audit-ready explanations for dispatch prioritization.
    """

    @classmethod
    def evaluate(cls, incident, waiting_minutes=None):
        """
        Evaluates an Incident model instance and returns:
        (score: float, level: str, explanation: str)
        """
        score = 0.0
        factors = []

        # 1. Immediate threat to life (+35)
        if incident.immediate_threat_to_life:
            score += 35.0
            factors.append("+35 pts: Active immediate threat to human life reported.")
        else:
            factors.append("+0 pts: No active life-threatening danger confirmed.")

        # 2. Trapped individuals (+20 base + 5 per additional, max +35)
        if incident.trapped_count > 0:
            trapped_pts = min(35.0, 20.0 + max(0, incident.trapped_count - 1) * 5.0)
            score += trapped_pts
            factors.append(f"+{trapped_pts:.0f} pts: {incident.trapped_count} individual(s) physically trapped.")

        # 3. Injured individuals (+15 base + 3 per additional, max +25)
        if incident.injured_count > 0:
            injured_pts = min(25.0, 15.0 + max(0, incident.injured_count - 1) * 3.0)
            score += injured_pts
            factors.append(f"+{injured_pts:.0f} pts: {incident.injured_count} person(s) injured requiring urgent medical stabilization.")

        # 4. Vulnerable individuals (children, elderly, pregnant, disabled) (+15)
        if incident.has_vulnerable_people:
            score += 15.0
            v_desc = f" ({incident.vulnerable_details})" if incident.vulnerable_details else ""
            factors.append(f"+15 pts: High-vulnerability individuals present{v_desc}.")

        # 5. Affected population scale (+5 to +20)
        pop = incident.affected_count
        if pop > 50:
            pop_pts = 20.0
            pop_label = "Severe mass casualty / large population displacement (>50 people)"
        elif pop >= 20:
            pop_pts = 15.0
            pop_label = "Medium-scale community emergency (20-50 people)"
        elif pop >= 6:
            pop_pts = 10.0
            pop_label = "Multiple households affected (6-19 people)"
        elif pop >= 2:
            pop_pts = 5.0
            pop_label = "Small group affected (2-5 people)"
        else:
            pop_pts = 2.0
            pop_label = "Single person affected"
        score += pop_pts
        factors.append(f"+{pop_pts:.0f} pts: Population impact: {pop_label} ({pop} affected).")

        # 6. Access difficulty (+0 to +15)
        access_pts = {
            AccessDifficulty.EASY: (0.0, "Paved/easy road access"),
            AccessDifficulty.MODERATE: (5.0, "Moderate terrain / partial waterlogging"),
            AccessDifficulty.DIFFICULT: (10.0, "Difficult access (deep water/debris)"),
            AccessDifficulty.INACCESSIBLE: (15.0, "Severely cut off / boat or aerial access required"),
        }
        pts, label = access_pts.get(incident.access_difficulty, (0.0, "Standard access"))
        if pts > 0:
            score += pts
            factors.append(f"+{pts:.0f} pts: Terrain & access impediment: {label}.")

        # 7. Dynamic waiting time penalty (+2 pts per 15 min waiting unassigned, max +20)
        accumulates_waiting_priority = incident.status in [
            IncidentStatus.REPORTED,
            IncidentStatus.TRIAGED,
            IncidentStatus.UNASSIGNED,
        ]
        wait_mins = (
            waiting_minutes
            if waiting_minutes is not None
            else incident.waiting_time_minutes
        )
        if not accumulates_waiting_priority:
            wait_mins = 0
        if wait_mins >= 15:
            intervals = wait_mins // 15
            wait_pts = min(20.0, intervals * 2.0)
            score += wait_pts
            factors.append(f"+{wait_pts:.0f} pts: Unassigned delay penalty ({wait_mins} min waiting).")

        # Determine Priority Level
        if score >= 80.0:
            level = PriorityLevel.CRITICAL
        elif score >= 55.0:
            level = PriorityLevel.HIGH
        elif score >= 30.0:
            level = PriorityLevel.MEDIUM
        else:
            level = PriorityLevel.LOW

        # Generate transparent explanation narrative
        explanation_lines = [
            f"Triage Score: {score:.1f}/100+ -> Priority Tier: {level}",
            "Rule-Based Factor Evaluation Breakdown:",
        ]
        for f in factors:
            explanation_lines.append(f"  • {f}")
        explanation_lines.append(
            "Notice: Calculated deterministically by ResQGrid Rule-Based Priority Engine. "
            "Aids humanitarian resource prioritization and does not constitute a medical diagnosis."
        )

        return round(score, 1), level, "\n".join(explanation_lines)
