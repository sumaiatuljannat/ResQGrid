"""
Views for ResQGrid Emergency Response Network
Handles authentication, role-based dashboards, incident lifecycles, matching, and shelter management.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.contrib import messages
from django.db import DatabaseError, connection, transaction
from django.db.models import Count, Q, F
from django.core.cache import cache
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.core.exceptions import ValidationError

from core.models import (
    UserProfile, ResponderProfile, UserRole,
    Incident, IncidentStatus, PriorityLevel, EmergencyType,
    Assignment, AssignmentStatus, IncidentEvent, EventType,
    Shelter, ShelterAllocation, ShelterStatus, Resource,
    VerificationStatus, AvailabilityStatus, Resource, ResourceCategory, ResourceStatus
)
from core.forms import (
    CitizenRegistrationForm, ResponderRegistrationForm,
    IncidentReportForm, ShelterAllocationForm, ResourceForm, ShelterForm
)
from core.engines.priority_engine import PriorityEngine
from core.engines.matching_engine import MatchingEngine
from core.engines.workflow_engine import WorkflowEngine


def _is_admin_user(user):
    profile = getattr(user, 'profile', None) if user.is_authenticated else None
    return user.is_authenticated and (user.is_superuser or (profile and profile.role == UserRole.ADMIN))


def _is_resource_manager(user):
    profile = getattr(user, 'profile', None) if user.is_authenticated else None
    return bool(user.is_authenticated and profile and profile.role == UserRole.RESOURCE_MANAGER)


def _is_verified_responder(user):
    if not user.is_authenticated:
        return False
    profile = getattr(user, 'profile', None)
    return bool(
        profile
        and profile.role == UserRole.RESPONDER
        and ResponderProfile.objects.filter(
            user=user,
            verification_status=VerificationStatus.VERIFIED,
        ).exists()
    )


def _demo_account_context():
    demo_password = settings.DEMO_PASSWORD if settings.DEBUG else ''
    return {
        'show_demo_accounts': bool(demo_password),
        'demo_password': demo_password,
    }


# ---------------------------------------------------------
# Public & Authentication Views
# ---------------------------------------------------------

def home_view(request):
    """Public landing page showcasing ResQGrid mission, stats, and portal access."""
    total_incidents = Incident.objects.count()
    active_incidents = Incident.objects.exclude(status__in=[IncidentStatus.RESOLVED, IncidentStatus.CANCELLED]).count()
    resolved_incidents = Incident.objects.filter(status=IncidentStatus.RESOLVED).count()
    total_responders = ResponderProfile.objects.filter(verification_status=VerificationStatus.VERIFIED).count()
    open_shelters = Shelter.objects.filter(status=ShelterStatus.OPEN).count()

    context = {
        'total_incidents': total_incidents,
        'active_incidents': active_incidents,
        'resolved_incidents': resolved_incidents,
        'total_responders': total_responders,
        'open_shelters': open_shelters,
        **_demo_account_context(),
    }
    return render(request, 'core/home.html', context)


def login_view(request):
    """User login view with fast demo account switchers for testing."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        client_ip = request.META.get('REMOTE_ADDR', 'unknown')
        throttle_key = f"login-attempts:{client_ip}:{username.lower()}"
        attempts = cache.get(throttle_key, 0)
        if attempts >= 5:
            messages.error(request, "Too many unsuccessful login attempts. Try again in 15 minutes.")
            return render(request, 'core/login.html', _demo_account_context())
        user = authenticate(request, username=username, password=password)
        if user is not None:
            cache.delete(throttle_key)
            login(request, user)
            messages.success(request, f"Welcome back, {user.get_full_name() or user.username}!")
            next_url = request.POST.get('next') or request.GET.get('next')
            if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)
            return redirect('dashboard')
        else:
            cache.set(throttle_key, attempts + 1, timeout=900)
            messages.error(request, "Invalid username or password.")

    return render(request, 'core/login.html', _demo_account_context())


@require_POST
def logout_view(request):
    """Logout user and redirect to homepage."""
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('home')


def register_citizen_view(request):
    """Registration for Citizens to report emergencies and track assistance."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = CitizenRegistrationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save(commit=False)
                user.set_password(form.cleaned_data['password'])
                user.save()
                UserProfile.objects.create(
                    user=user,
                    role=UserRole.CITIZEN,
                    phone=form.cleaned_data.get('phone', ''),
                    address=form.cleaned_data.get('address', ''),
                    is_verified=True
                )

            login(request, user)
            messages.success(request, "Citizen account registered successfully! You can now report emergency SOS requests.")
            return redirect('citizen_dashboard')
    else:
        form = CitizenRegistrationForm()

    return render(request, 'core/register_citizen.html', {'form': form})


def register_responder_view(request):
    """Registration for Responders, requiring admin verification."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = ResponderRegistrationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save(commit=False)
                user.set_password(form.cleaned_data['password'])
                user.save()
                UserProfile.objects.create(
                    user=user,
                    role=UserRole.RESPONDER,
                    phone=form.cleaned_data.get('phone', ''),
                    organization=form.cleaned_data.get('organization', ''),
                    is_verified=False
                )
                skills_str = ','.join(form.cleaned_data.get('skills_selected', []))
                equipment_str = ','.join(form.cleaned_data.get('equipment_selected', []))
                ResponderProfile.objects.create(
                    user=user,
                    verification_status=VerificationStatus.PENDING,
                    availability=AvailabilityStatus.AVAILABLE,
                    skills=skills_str,
                    equipment=equipment_str,
                    service_area_name=form.cleaned_data.get('service_area_name', 'Dhaka'),
                    latitude=form.cleaned_data.get('latitude', 23.8103),
                    longitude=form.cleaned_data.get('longitude', 90.4125),
                    service_radius_km=form.cleaned_data.get('service_radius_km', 25.0),
                    max_active_capacity=form.cleaned_data.get('max_active_capacity', 2),
                )

            login(request, user)
            messages.info(request, "Responder registered! Your profile is pending Administrator verification before dispatch eligibility.")
            return redirect('responder_dashboard')
    else:
        form = ResponderRegistrationForm()

    return render(request, 'core/register_responder.html', {'form': form})


# ---------------------------------------------------------
# Role Routing & Dashboards
# ---------------------------------------------------------

@login_required
def dashboard_router_view(request):
    """Directs authenticated users to their designated role dashboard."""
    profile = getattr(request.user, 'profile', None)
    if _is_admin_user(request.user):
        return redirect('admin_dashboard')
    elif profile and profile.role == UserRole.RESPONDER:
        return redirect('responder_dashboard')
    elif profile and profile.role == UserRole.RESOURCE_MANAGER:
        return redirect('shelter_list')
    else:
        return redirect('citizen_dashboard')


@login_required
def admin_dashboard_view(request):
    """Admin mission control: analytics, all incidents, responders, and shelters."""
    if not _is_admin_user(request.user):
        return HttpResponseForbidden("Administrator access required.")

    # Metrics
    total_incidents = Incident.objects.count()
    critical_incidents = Incident.objects.filter(priority_level=PriorityLevel.CRITICAL).exclude(status=IncidentStatus.RESOLVED).count()
    unassigned_incidents = Incident.objects.filter(status=IncidentStatus.UNASSIGNED).count()
    active_responders = ResponderProfile.objects.filter(verification_status=VerificationStatus.VERIFIED, availability=AvailabilityStatus.AVAILABLE).count()
    available_shelters = Shelter.objects.filter(status=ShelterStatus.OPEN).count()

    # Priority distribution for charts
    priority_counts = {
        'CRITICAL': Incident.objects.filter(priority_level=PriorityLevel.CRITICAL).count(),
        'HIGH': Incident.objects.filter(priority_level=PriorityLevel.HIGH).count(),
        'MEDIUM': Incident.objects.filter(priority_level=PriorityLevel.MEDIUM).count(),
        'LOW': Incident.objects.filter(priority_level=PriorityLevel.LOW).count(),
    }

    # Status distribution
    status_counts = {
        'REPORTED': Incident.objects.filter(status=IncidentStatus.REPORTED).count(),
        'ASSIGNED': Incident.objects.filter(status=IncidentStatus.ASSIGNED).count(),
        'ACCEPTED': Incident.objects.filter(status=IncidentStatus.ACCEPTED).count(),
        'RESPONDING': Incident.objects.filter(status=IncidentStatus.RESPONDING).count(),
        'RESOLVED': Incident.objects.filter(status=IncidentStatus.RESOLVED).count(),
        'UNASSIGNED': unassigned_incidents,
    }

    # Recent activity stream
    recent_events = IncidentEvent.objects.select_related('incident', 'actor').order_by('-timestamp')[:12]

    # Incidents table with search, filter, and sorting
    incidents_qs = Incident.objects.select_related('assigned_responder', 'reporter').all()

    q_search = request.GET.get('q', '').strip()
    f_status = request.GET.get('status', '').strip()
    f_priority = request.GET.get('priority', '').strip()
    f_type = request.GET.get('type', '').strip()
    sort_by = request.GET.get('sort', '-created_at').strip()

    if q_search:
        incidents_qs = incidents_qs.filter(
            Q(incident_id__icontains=q_search) |
            Q(location_name__icontains=q_search) |
            Q(description__icontains=q_search) |
            Q(contact_name__icontains=q_search)
        )
    if f_status:
        incidents_qs = incidents_qs.filter(status=f_status)
    if f_priority:
        incidents_qs = incidents_qs.filter(priority_level=f_priority)
    if f_type:
        incidents_qs = incidents_qs.filter(emergency_type=f_type)

    if sort_by in ['-created_at', 'created_at', '-priority_score', 'priority_score']:
        incidents_qs = incidents_qs.order_by(sort_by)
    else:
        incidents_qs = incidents_qs.order_by('-created_at')

    # Responders needing verification
    pending_responders = ResponderProfile.objects.select_related('user', 'user__profile').filter(
        verification_status=VerificationStatus.PENDING
    )
    all_responders = ResponderProfile.objects.select_related('user').all()[:15]
    all_shelters = Shelter.objects.all()[:10]

    context = {
        'total_incidents': total_incidents,
        'critical_incidents': critical_incidents,
        'unassigned_incidents': unassigned_incidents,
        'active_responders': active_responders,
        'available_shelters': available_shelters,
        'priority_counts': priority_counts,
        'status_counts': status_counts,
        'recent_events': recent_events,
        'incidents': incidents_qs[:30],
        'pending_responders': pending_responders,
        'all_responders': all_responders,
        'all_shelters': all_shelters,
        'q_search': q_search,
        'f_status': f_status,
        'f_priority': f_priority,
        'f_type': f_type,
        'sort_by': sort_by,
        'emergency_types': EmergencyType.choices,
        'priority_levels': PriorityLevel.choices,
        'incident_statuses': IncidentStatus.choices,
    }
    return render(request, 'core/dashboard_admin.html', context)


@login_required
def citizen_dashboard_view(request):
    """Citizen portal: SOS trigger, reported incidents tracking, shelter finder."""
    profile = getattr(request.user, 'profile', None)
    if not profile or profile.role != UserRole.CITIZEN:
        return HttpResponseForbidden("Citizen access required.")
    my_incidents = Incident.objects.filter(reporter=request.user).order_by('-created_at')
    open_shelters = Shelter.objects.filter(status=ShelterStatus.OPEN).order_by('-total_capacity')[:6]

    context = {
        'my_incidents': my_incidents,
        'open_shelters': open_shelters,
    }
    return render(request, 'core/dashboard_citizen.html', context)


@login_required
def responder_dashboard_view(request):
    """Responder mission terminal: accept/reject, respond, resolve, toggle availability."""
    responder_profile = getattr(request.user, 'responder_profile', None)

    profile = getattr(request.user, 'profile', None)
    if not profile or profile.role != UserRole.RESPONDER or not responder_profile:
        return HttpResponseForbidden("Responder access required.")

    # Pending assignments waiting for acceptance
    pending_assignments = Assignment.objects.select_related('incident').filter(
        responder=request.user,
        status=AssignmentStatus.PENDING
    )

    # Active missions in progress (ACCEPTED or RESPONDING)
    active_assignments = Assignment.objects.select_related('incident').filter(
        responder=request.user,
        status=AssignmentStatus.ACCEPTED,
        incident__status__in=[IncidentStatus.ACCEPTED, IncidentStatus.RESPONDING]
    )

    # Past completed missions
    past_assignments = Assignment.objects.select_related('incident').filter(
        responder=request.user,
        status__in=[AssignmentStatus.COMPLETED, AssignmentStatus.REJECTED]
    ).order_by('-assigned_at')[:10]

    context = {
        'responder_profile': responder_profile,
        'pending_assignments': pending_assignments,
        'active_assignments': active_assignments,
        'past_assignments': past_assignments,
        'availability_choices': AvailabilityStatus.choices,
    }
    return render(request, 'core/dashboard_responder.html', context)


# ---------------------------------------------------------
# Incident Lifecycle & Reporting (Module A, B, C, D)
# ---------------------------------------------------------

@login_required
@login_required
def incident_create_view(request):
    """Create a new emergency SOS report with priority evaluation and auto-dispatch."""
    if request.method == 'POST':
        form = IncidentReportForm(request.POST)
        if form.is_valid():
            # Check for duplicate submission within last 60 seconds by same user at same location
            one_min_ago = timezone.now() - timezone.timedelta(seconds=60)
            loc = form.cleaned_data.get('location_name', '').strip()
            etype = form.cleaned_data.get('emergency_type')
            duplicate = Incident.objects.filter(
                reporter=request.user,
                emergency_type=etype,
                location_name__iexact=loc,
                created_at__gte=one_min_ago
            ).first()

            if duplicate:
                messages.warning(request, f"Duplicate report detected. Existing incident {duplicate.incident_id} is already open.")
                return redirect('incident_detail', incident_id=duplicate.incident_id)

            with transaction.atomic():
                incident = form.save(commit=False)
                incident.reporter = request.user
                incident.status = IncidentStatus.REPORTED
                incident.save()
                IncidentEvent.objects.create(
                    incident=incident,
                    actor=request.user,
                    event_type=EventType.CREATED,
                    from_status='',
                    to_status=IncidentStatus.REPORTED,
                    description=f"Incident reported by {request.user.username}. Emergency type: {incident.get_emergency_type_display()}."
                )
                WorkflowEngine.process_new_incident(incident, actor=request.user, auto_dispatch=True)

            messages.success(request, f"Emergency SOS [{incident.incident_id}] submitted! Triaged as {incident.get_priority_level_display()} (Score: {incident.priority_score}).")
            return redirect('incident_detail', incident_id=incident.incident_id)
    else:
        # Prepopulate reporter name and phone from profile if available
        initial = {}
        profile = getattr(request.user, 'profile', None)
        if profile:
            initial['contact_name'] = request.user.get_full_name() or request.user.username
            initial['contact_phone'] = profile.phone
        form = IncidentReportForm(initial=initial)

    return render(request, 'core/incident_create.html', {'form': form})


@login_required
def incident_detail_view(request, incident_id):
    """Comprehensive incident view with live status, priority breakdown, responder match, and event timeline."""
    incident = get_object_or_404(Incident.objects.select_related('reporter', 'assigned_responder'), incident_id=incident_id)

    # Privacy & Role checks
    is_admin = _is_admin_user(request.user)
    is_assigned = (
        incident.assigned_responder_id == request.user.id
        and _is_verified_responder(request.user)
    )
    is_owner = (incident.reporter == request.user)

    if not (is_admin or is_assigned or is_owner):
        return HttpResponseForbidden("You do not have permission to view this emergency incident.")

    # If Admin, find candidate matches to allow manual dispatch if needed
    recommended_matches = []
    match_diag = ""
    if is_admin and incident.status in [IncidentStatus.REPORTED, IncidentStatus.TRIAGED, IncidentStatus.UNASSIGNED]:
        dispatched_user_ids = list(Assignment.objects.filter(incident=incident).values_list('responder_id', flat=True))
        recommended_matches, match_diag = MatchingEngine.find_matches(incident, exclude_user_ids=dispatched_user_ids)

    # Active assignment
    active_assignment = Assignment.objects.filter(
        incident=incident,
        status__in=[AssignmentStatus.PENDING, AssignmentStatus.ACCEPTED]
    ).first()

    events = incident.events.select_related('actor').order_by('timestamp')
    shelter_allocations = incident.shelter_allocations.select_related('shelter').all()

    from core.forms import IncidentNoteForm
    note_form = IncidentNoteForm()

    context = {
        'incident': incident,
        'events': events,
        'active_assignment': active_assignment,
        'recommended_matches': recommended_matches,
        'match_diag': match_diag,
        'is_admin': is_admin,
        'is_assigned': is_assigned,
        'is_owner': is_owner,
        'can_resolve': (is_admin or is_assigned) and incident.status in [IncidentStatus.ACCEPTED, IncidentStatus.RESPONDING],
        'can_post_note': (is_admin or is_assigned or is_owner) and incident.status not in [IncidentStatus.RESOLVED, IncidentStatus.CANCELLED],
        'can_allocate_shelter_for_incident': (
            is_admin or _is_resource_manager(request.user) or is_assigned
        ),
        'shelter_allocations': shelter_allocations,
        'note_form': note_form,
    }
    return render(request, 'core/incident_detail.html', context)


@login_required
def incident_list_view(request):
    """Filterable, searchable list of all incidents with pagination and metrics."""
    profile = getattr(request.user, 'profile', None)
    if _is_admin_user(request.user):
        incidents = Incident.objects.all()
    elif _is_verified_responder(request.user):
        incidents = Incident.objects.filter(assigned_responder=request.user)
    elif profile and profile.role == UserRole.CITIZEN:
        incidents = Incident.objects.filter(reporter=request.user)
    else:
        incidents = Incident.objects.none()
    incidents = incidents.select_related('reporter', 'assigned_responder')

    q_search = request.GET.get('q', '').strip()
    f_status = request.GET.get('status', '').strip()
    f_priority = request.GET.get('priority', '').strip()
    f_type = request.GET.get('type', '').strip()
    sort_by = request.GET.get('sort', '-created_at').strip()

    if q_search:
        incidents = incidents.filter(
            Q(incident_id__icontains=q_search) |
            Q(location_name__icontains=q_search) |
            Q(description__icontains=q_search) |
            Q(contact_name__icontains=q_search)
        )
    if f_status:
        incidents = incidents.filter(status=f_status)
    if f_priority:
        incidents = incidents.filter(priority_level=f_priority)
    if f_type:
        incidents = incidents.filter(emergency_type=f_type)

    if sort_by in ['-created_at', 'created_at', '-priority_score', 'priority_score']:
        incidents = incidents.order_by(sort_by)
    else:
        incidents = incidents.order_by('-created_at')

    incidents = Paginator(incidents, 20).get_page(request.GET.get('page'))
    context = {
        'incidents': incidents,
        'q_search': q_search,
        'f_status': f_status,
        'f_priority': f_priority,
        'f_type': f_type,
        'sort_by': sort_by,
        'emergency_types': EmergencyType.choices,
        'priority_levels': PriorityLevel.choices,
        'incident_statuses': IncidentStatus.choices,
    }
    return render(request, 'core/incident_list.html', context)


# ---------------------------------------------------------
# Workflow Actions (Module D)
# ---------------------------------------------------------

@login_required
@require_POST
def assignment_accept_view(request, assignment_id):
    """Responder accepts an assigned incident mission."""
    assignment = get_object_or_404(Assignment, id=assignment_id)
    if assignment.responder_id != request.user.id or not _is_verified_responder(request.user):
        return HttpResponseForbidden("Only the assigned verified responder can accept this mission.")
    notes = request.POST.get('notes', '')
    try:
        WorkflowEngine.accept_assignment(assignment, request.user, notes=notes)
        messages.success(request, f"Mission for incident {assignment.incident.incident_id} accepted! Status is now ACCEPTED.")
    except ValidationError as e:
        messages.error(request, str(e.message if hasattr(e, 'message') else e))

    return redirect('responder_dashboard')


@login_required
@require_POST
def assignment_reject_view(request, assignment_id):
    """Responder rejects assignment. Triggers automated failover reassignment loop."""
    assignment = get_object_or_404(Assignment, id=assignment_id)
    if assignment.responder_id != request.user.id or not _is_verified_responder(request.user):
        return HttpResponseForbidden("Only the assigned verified responder can reject this mission.")
    reason = request.POST.get('rejection_reason', 'Responder unable to deploy.')
    try:
        next_assignment, msg = WorkflowEngine.reject_assignment(assignment, request.user, reason=reason)
        messages.info(request, f"Assignment declined. {msg}")
    except ValidationError as e:
        messages.error(request, str(e.message if hasattr(e, 'message') else e))

    return redirect('responder_dashboard')


@login_required
@require_POST
def incident_update_status_view(request, incident_id):
    """Update status to RESPONDING or RESOLVED, or append deployment progress notes."""
    incident = get_object_or_404(Incident, incident_id=incident_id)
    target_status = request.POST.get('status')
    notes = request.POST.get('notes', '').strip()
    is_admin = _is_admin_user(request.user)
    is_assigned = (
        incident.assigned_responder_id == request.user.id
        and _is_verified_responder(request.user)
    )

    try:
        if target_status == IncidentStatus.RESPONDING:
            if not (is_admin or is_assigned):
                return HttpResponseForbidden("Only the assigned verified responder or an administrator can update field deployment progress.")
            if incident.status == IncidentStatus.ACCEPTED:
                actor = request.user if is_assigned else (incident.assigned_responder or request.user)
                WorkflowEngine.update_to_responding(incident, actor, progress_notes=notes)
            elif incident.status == IncidentStatus.RESPONDING:
                # Mid-mission progress note
                IncidentEvent.objects.create(
                    incident=incident,
                    actor=request.user,
                    event_type=EventType.STATUS_UPDATE,
                    from_status=IncidentStatus.RESPONDING,
                    to_status=IncidentStatus.RESPONDING,
                    description=f"Field Progress Update: {notes or 'Active response ongoing on-scene.'}"
                )
            else:
                raise ValidationError("Only an accepted incident can be marked as responding.")
            messages.success(request, f"Incident {incident.incident_id} deployment progress updated.")
        elif target_status == IncidentStatus.RESOLVED:
            if not (is_admin or is_assigned):
                return HttpResponseForbidden("Only the assigned verified responder or an administrator can mark an incident resolved.")
            WorkflowEngine.resolve_incident(incident, request.user, resolution_notes=notes)
            messages.success(request, f"Incident {incident.incident_id} has been marked RESOLVED. Mission completed.")
        elif target_status == IncidentStatus.CANCELLED:
            if not (is_admin or incident.reporter == request.user):
                return HttpResponseForbidden("Only an administrator or the original reporter can cancel an incident.")
            WorkflowEngine.cancel_incident(incident, request.user, reason=notes)
            messages.info(request, f"Incident {incident.incident_id} marked as CANCELLED.")
        else:
            messages.error(request, f"Unsupported transition to {target_status}.")
    except ValidationError as e:
        messages.error(request, str(e.message if hasattr(e, 'message') else e))

    return redirect('incident_detail', incident_id=incident.incident_id)


@login_required
@require_POST
def incident_post_note_view(request, incident_id):
    """Allows authorized actors (citizen reporter, assigned responder, admin) to post real-time updates."""
    incident = get_object_or_404(Incident, incident_id=incident_id)
    is_admin = _is_admin_user(request.user)
    is_assigned = (
        incident.assigned_responder_id == request.user.id
        and _is_verified_responder(request.user)
    )
    is_owner = (incident.reporter == request.user)

    if not (is_admin or is_assigned or is_owner):
        return HttpResponseForbidden("You do not have permission to post updates to this emergency report.")

    if incident.status in [IncidentStatus.RESOLVED, IncidentStatus.CANCELLED]:
        messages.error(request, "Updates cannot be added to a closed incident.")
        return redirect('incident_detail', incident_id=incident.incident_id)
    note_text = request.POST.get('note', '').strip()
    if note_text:
        if is_admin:
            role_label = "Administrator"
        elif is_assigned:
            role_label = "Assigned Responder"
        else:
            role_label = "Citizen (Distressed Reporter)"

        IncidentEvent.objects.create(
            incident=incident,
            actor=request.user,
            event_type=EventType.STATUS_UPDATE,
            from_status=incident.status,
            to_status=incident.status,
            description=f"[{role_label} Update] {note_text}"
        )
        messages.success(request, "Operational update added to live incident audit log.")
    else:
        messages.warning(request, "Note content cannot be empty.")

    return redirect('incident_detail', incident_id=incident.incident_id)


@login_required
@require_POST
def incident_retrigger_triage_view(request, incident_id):
    """Allows administrators to re-evaluate priority score and re-run automated dispatch matching."""
    if not _is_admin_user(request.user):
        return HttpResponseForbidden("Admin access required.")

    incident = get_object_or_404(Incident, incident_id=incident_id)
    if incident.status in [IncidentStatus.RESOLVED, IncidentStatus.CANCELLED]:
        messages.warning(request, f"Cannot re-triage a {incident.get_status_display()} incident.")
        return redirect('incident_detail', incident_id=incident.incident_id)

    WorkflowEngine.process_new_incident(incident, actor=request.user, auto_dispatch=True)
    messages.success(request, f"Re-triaged incident {incident.incident_id}: Priority is {incident.priority_level} ({incident.priority_score} pts). Status: {incident.get_status_display()}.")
    return redirect('incident_detail', incident_id=incident.incident_id)


@login_required
@require_POST
def manual_dispatch_view(request, incident_id):
    """Admin manually dispatches a specific responder to an incident."""
    if not _is_admin_user(request.user):
        return HttpResponseForbidden("Admin access required.")

    incident = get_object_or_404(Incident, incident_id=incident_id)
    responder_id = request.POST.get('responder_id')
    if not responder_id or not responder_id.isdecimal():
        messages.error(request, "Select a valid responder.")
        return redirect('incident_detail', incident_id=incident.incident_id)
    responder_user = get_object_or_404(User, id=int(responder_id))

    try:
        WorkflowEngine.manual_dispatch(incident, responder_user, request.user)
    except ValidationError as error:
        messages.error(request, str(error.message if hasattr(error, 'message') else error))
        return redirect('incident_detail', incident_id=incident.incident_id)

    messages.success(request, f"Dispatched incident {incident.incident_id} to responder {responder_user.username}.")
    return redirect('incident_detail', incident_id=incident.incident_id)


# ---------------------------------------------------------
# Responder Management & Profile
# ---------------------------------------------------------

@login_required
@require_POST
def responder_toggle_availability_view(request):
    """Responder updates their duty availability status."""
    responder_profile = getattr(request.user, 'responder_profile', None)
    profile = getattr(request.user, 'profile', None)
    if not responder_profile or not profile or profile.role != UserRole.RESPONDER:
        return HttpResponseForbidden("Responder access required.")

    new_status = request.POST.get('availability')
    if new_status in [AvailabilityStatus.AVAILABLE, AvailabilityStatus.BUSY, AvailabilityStatus.OFFLINE]:
        with transaction.atomic():
            responder_profile.availability = new_status
            responder_profile.save()
            reassigned_count = 0
            if new_status != AvailabilityStatus.AVAILABLE:
                reassigned_count = WorkflowEngine.reassign_pending_for_unavailable_responder(
                    request.user, actor=request.user
                )
        messages.success(request, f"Availability status updated to: {responder_profile.get_availability_display()}.")
        if new_status != AvailabilityStatus.AVAILABLE and reassigned_count:
            messages.info(request, f"{reassigned_count} pending assignment(s) were automatically reassigned.")
    else:
        messages.error(request, "Choose a valid responder availability status.")

    return redirect('responder_dashboard')


@login_required
@require_POST
def admin_verify_responder_view(request, responder_id):
    """Admin verifies or rejects a responder's credentials."""
    if not _is_admin_user(request.user):
        return HttpResponseForbidden("Admin access required.")

    responder_profile = get_object_or_404(ResponderProfile, id=responder_id)
    action = request.POST.get('action')

    if action == 'VERIFY':
        responder_profile.verification_status = VerificationStatus.VERIFIED
        responder_profile.save()
        messages.success(request, f"Responder {responder_profile.user.username} has been VERIFIED and added to active dispatch roster.")
    elif action == 'REJECT':
        with transaction.atomic():
            responder_profile.verification_status = VerificationStatus.REJECTED
            responder_profile.save()
            WorkflowEngine.reassign_pending_for_unavailable_responder(
                responder_profile.user, actor=request.user
            )
        messages.warning(request, f"Responder {responder_profile.user.username} application was REJECTED.")
    else:
        messages.error(request, "Choose VERIFY or REJECT for this responder.")

    return redirect('admin_dashboard')


# ---------------------------------------------------------
# Map & Geospatial View
# ---------------------------------------------------------

def _map_data_for_user(user):
    """Return database-backed map data within the caller's existing visibility scope."""
    profile = getattr(user, 'profile', None)
    is_admin = _is_admin_user(user)
    is_resource_manager = _is_resource_manager(user)
    is_verified_responder = _is_verified_responder(user)
    if is_admin:
        incidents = Incident.objects.exclude(
            status__in=[IncidentStatus.RESOLVED, IncidentStatus.CANCELLED]
        ).select_related('assigned_responder')
    elif is_verified_responder:
        incidents = Incident.objects.filter(
            assigned_responder=user
        ).exclude(status__in=[IncidentStatus.RESOLVED, IncidentStatus.CANCELLED]).select_related(
            'assigned_responder'
        )
    elif user.is_authenticated and profile and profile.role == UserRole.CITIZEN:
        incidents = Incident.objects.filter(
            reporter=user
        ).exclude(status__in=[IncidentStatus.RESOLVED, IncidentStatus.CANCELLED]).select_related(
            'assigned_responder'
        )
    else:
        incidents = Incident.objects.none()
    shelters = Shelter.objects.all()
    responders = ResponderProfile.objects.none()
    if is_admin or is_verified_responder:
        responders = ResponderProfile.objects.filter(
            verification_status=VerificationStatus.VERIFIED
        ).select_related('user', 'user__profile')

    incidents_list = []
    for inc in incidents:
        incidents_list.append({
            'id': inc.incident_id,
            'type': inc.emergency_type,
            'type_display': inc.get_emergency_type_display(),
            'priority': inc.priority_level,
            'score': inc.priority_score,
            'status': inc.status,
            'status_display': inc.get_status_display(),
            'location': inc.location_name,
            'lat': inc.latitude,
            'lon': inc.longitude,
            'affected': inc.affected_count,
            'injured': inc.injured_count,
            'trapped': inc.trapped_count,
            'threat': inc.immediate_threat_to_life,
            'has_vulnerable': inc.has_vulnerable_people,
            'access_difficulty': inc.get_access_difficulty_display(),
            'description': inc.description,
            'assigned_responder': inc.assigned_responder.get_full_name() or inc.assigned_responder.username if inc.assigned_responder else None,
            'created_at': inc.created_at.strftime('%b %d, %H:%M'),
            'waiting_mins': inc.waiting_time_minutes,
        })

    shelters_list = []
    for s in shelters:
        shelters_list.append({
            'id': s.id,
            'name': s.name,
            'address': s.address,
            'lat': s.latitude,
            'lon': s.longitude,
            'total': s.total_capacity,
            'occupied': s.occupied_capacity,
            'available': s.available_capacity,
            'occupancy_pct': s.occupancy_percentage,
            'status': s.status,
            'status_display': s.get_status_display(),
            'food': s.has_food,
            'water': s.has_water,
            'medical': s.has_medical,
            'contact_person': s.contact_person,
            'contact_phone': s.contact_phone,
        })

    responders_list = []
    for r in responders:
        responder_user_profile = getattr(r.user, 'profile', None)
        can_view_contact = is_admin or r.user_id == user.id
        responders_list.append({
            'id': r.id,
            'name': r.user.get_full_name() or r.user.username,
            'username': r.user.username,
            'phone': responder_user_profile.phone if can_view_contact and responder_user_profile else '',
            'org': responder_user_profile.organization if can_view_contact and responder_user_profile else '',
            'skills': r.get_skills_list(),
            'equipment': r.get_equipment_list(),
            'area': r.service_area_name,
            'lat': r.latitude,
            'lon': r.longitude,
            'radius_km': r.service_radius_km,
            'max_capacity': r.max_active_capacity,
            'active_assignments': r.current_active_assignments,
            'availability': r.availability,
            'availability_display': r.get_availability_display(),
        })

    return {
        'incidents': incidents_list,
        'shelters': shelters_list,
        'responders': responders_list,
    }


def map_view(request):
    """Interactive Leaflet map showing active incidents, emergency shelters, and verified responders."""
    map_data = _map_data_for_user(request.user)
    is_admin = _is_admin_user(request.user)
    is_resource_manager = _is_resource_manager(request.user)
    is_verified_responder = _is_verified_responder(request.user)
    context = {
        'incidents_json': map_data['incidents'],
        'shelters_json': map_data['shelters'],
        'responders_json': map_data['responders'],
        'total_active_incidents': len(map_data['incidents']),
        'total_shelters': len(map_data['shelters']),
        'total_responders': len(map_data['responders']),
        'emergency_types': EmergencyType.choices,
        'priority_levels': PriorityLevel.choices,
        'can_manage_shelters': is_admin or is_resource_manager,
        'can_allocate_from_incident': is_admin or is_resource_manager or is_verified_responder,
    }
    return render(request, 'core/map.html', context)


@require_GET
def map_data_view(request):
    """Return the latest authorized map records for the live grid refresh."""
    return JsonResponse(_map_data_for_user(request.user))


@require_GET
def health_check_view(request):
    """Report readiness only when the configured database accepts a query."""
    try:
        connection.ensure_connection()
    except DatabaseError:
        return JsonResponse({'status': 'unavailable'}, status=503)
    return JsonResponse({'status': 'ok'})


# ---------------------------------------------------------
# Shelter & Resource Management (Module E)
# ---------------------------------------------------------

def shelter_list_view(request):
    """Public and authenticated directory of emergency relief shelters."""
    shelters = Shelter.objects.all()
    q = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()

    if q:
        shelters = shelters.filter(Q(name__icontains=q) | Q(address__icontains=q))
    if status_filter:
        shelters = shelters.filter(status=status_filter)

    shelters = Paginator(shelters, 12).get_page(request.GET.get('page'))
    context = {
        'shelters': shelters,
        'q': q,
        'status_filter': status_filter,
        'shelter_statuses': ShelterStatus.choices,
    }
    return render(request, 'core/shelter_list.html', context)


@login_required
def shelter_create_view(request):
    if not (_is_admin_user(request.user) or _is_resource_manager(request.user)):
        return HttpResponseForbidden("Shelter management access required.")
    if request.method == 'POST':
        form = ShelterForm(request.POST)
        if form.is_valid():
            shelter = form.save()
            messages.success(request, f"Shelter '{shelter.name}' registered successfully.")
            return redirect('shelter_list')
    else:
        form = ShelterForm()
    return render(request, 'core/shelter_form.html', {'form': form, 'action': 'Register'})


@login_required
def shelter_edit_view(request, shelter_id):
    if not (_is_admin_user(request.user) or _is_resource_manager(request.user)):
        return HttpResponseForbidden("Shelter management access required.")
    shelter = get_object_or_404(Shelter, id=shelter_id)
    if request.method == 'POST':
        form = ShelterForm(request.POST, instance=shelter)
        if form.is_valid():
            shelter = form.save()
            messages.success(request, f"Shelter '{shelter.name}' updated successfully.")
            return redirect('shelter_list')
    else:
        form = ShelterForm(instance=shelter)
    return render(request, 'core/shelter_form.html', {'form': form, 'action': 'Update', 'shelter': shelter})


@login_required
def shelter_allocate_view(request):
    """Allocates affected families/individuals to a shelter with concurrency-safe capacity validation."""
    can_manage_shelters = _is_admin_user(request.user) or _is_resource_manager(request.user)
    is_verified_responder = _is_verified_responder(request.user)
    if not (can_manage_shelters or is_verified_responder):
        return HttpResponseForbidden("Shelter allocation is restricted to administrators, resource managers, and assigned responders.")

    allowed_incidents = _shelter_allocation_incidents_for_user(request.user)
    if request.method == 'POST':
        incident_id = request.POST.get('incident', '').strip()
        if incident_id and (
            not incident_id.isdecimal()
            or not allowed_incidents.filter(pk=int(incident_id)).exists()
        ):
            return HttpResponseForbidden("You cannot allocate shelter capacity for this incident.")
        if is_verified_responder and not incident_id:
            return HttpResponseForbidden("Responders must link a shelter allocation to an assigned incident.")

        form = ShelterAllocationForm(request.POST)
        _scope_shelter_allocation_incidents(form, request.user, allowed_incidents)
        if form.is_valid():
            shelter = form.cleaned_data['shelter']
            count = form.cleaned_data['family_count']
            person_name = form.cleaned_data['person_name']
            linked_incident = form.cleaned_data.get('incident')

            try:
                with transaction.atomic():
                    shelter.allocate_people(count)
                    allocation = form.save(commit=False)
                    allocation.allocated_by = request.user
                    allocation.save()
                    if linked_incident:
                        IncidentEvent.objects.create(
                            incident=linked_incident,
                            actor=request.user,
                            event_type=EventType.SHELTER_ALLOCATED,
                            from_status=linked_incident.status,
                            to_status=linked_incident.status,
                            description=f"Evacuee Allocation: {count} person(s) for '{person_name}' safely accommodated at shelter '{shelter.name}'."
                        )

                messages.success(
                    request,
                    f"Successfully allocated {count} person(s) for '{person_name}' to {shelter.name}. "
                    f"Remaining free capacity: {shelter.available_capacity}/{shelter.total_capacity}."
                )
                if linked_incident:
                    return redirect('incident_detail', incident_id=linked_incident.incident_id)
                return redirect('shelter_list')
            except ValidationError as e:
                messages.error(request, str(e.message if hasattr(e, 'message') else e))
    else:
        initial = {}
        shelter_id = request.GET.get('shelter_id')
        incident_id = request.GET.get('incident_id')
        if shelter_id:
            initial['shelter'] = shelter_id
        if incident_id:
            inc = get_object_or_404(Incident, incident_id=incident_id)
            if not allowed_incidents.filter(pk=inc.pk).exists():
                return HttpResponseForbidden("You cannot allocate shelter capacity for this incident.")
            initial['incident'] = inc.id
            initial['person_name'] = inc.victim_name or inc.contact_name
            initial['family_count'] = max(1, inc.affected_count)
            initial['contact_phone'] = inc.contact_phone
        elif is_verified_responder:
            return HttpResponseForbidden("Responders must open shelter allocation from an assigned incident.")
        form = ShelterAllocationForm(initial=initial)
        _scope_shelter_allocation_incidents(form, request.user, allowed_incidents)

    return render(request, 'core/shelter_allocate.html', {'form': form})


def _can_manage_resources(user):
    return _is_admin_user(user) or _is_resource_manager(user)


@login_required
def resource_list_view(request):
    if not _can_manage_resources(request.user):
        return HttpResponseForbidden("Resource management access required.")

    resources = Resource.objects.select_related('shelter').order_by('-updated_at', 'name')
    q = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip()
    status_filter = request.GET.get('status', '').strip()
    if q:
        resources = resources.filter(
            Q(name__icontains=q) | Q(location_name__icontains=q)
        )
    if category:
        resources = resources.filter(category=category)
    if status_filter:
        resources = resources.filter(status=status_filter)
    resources = Paginator(resources, 20).get_page(request.GET.get('page'))
    return render(request, 'core/resource_list.html', {
        'resources': resources,
        'q': q,
        'category': category,
        'status_filter': status_filter,
        'resource_categories': ResourceCategory.choices,
        'resource_statuses': ResourceStatus.choices,
    })


@login_required
def resource_create_view(request):
    if not _can_manage_resources(request.user):
        return HttpResponseForbidden("Resource management access required.")

    if request.method == 'POST':
        form = ResourceForm(request.POST)
        if form.is_valid():
            resource = form.save()
            messages.success(request, f"Resource '{resource.name}' registered successfully.")
            return redirect('resource_list')
    else:
        form = ResourceForm()
    return render(request, 'core/resource_form.html', {'form': form, 'action': 'Register'})


@login_required
def resource_edit_view(request, resource_id):
    if not _can_manage_resources(request.user):
        return HttpResponseForbidden("Resource management access required.")
    resource = get_object_or_404(Resource, id=resource_id)
    if request.method == 'POST':
        form = ResourceForm(request.POST, instance=resource)
        if form.is_valid():
            resource = form.save()
            if resource.quantity == 0:
                resource.status = ResourceStatus.DEPLETED
                resource.save(update_fields=['status', 'updated_at'])
            messages.success(request, f"Resource '{resource.name}' updated successfully.")
            return redirect('resource_list')
    else:
        form = ResourceForm(instance=resource)
    return render(request, 'core/resource_form.html', {'form': form, 'action': 'Update', 'resource': resource})


@login_required
@require_POST
def resource_update_status_view(request, resource_id):
    if not _can_manage_resources(request.user):
        return HttpResponseForbidden("Resource management access required.")
    resource = get_object_or_404(Resource, id=resource_id)
    new_status = request.POST.get('status')
    if new_status not in [choice[0] for choice in ResourceStatus.choices]:
        messages.error(request, "Choose a valid resource status.")
    else:
        resource.status = new_status
        resource.save(update_fields=['status', 'updated_at'])
        messages.success(request, f"Resource '{resource.name}' status updated.")
    return redirect('resource_list')


@login_required
@require_POST
def resource_adjust_quantity_view(request, resource_id):
    if not _can_manage_resources(request.user):
        return HttpResponseForbidden("Resource management access required.")
    resource = get_object_or_404(Resource, id=resource_id)
    try:
        quantity_change = int(request.POST.get('quantity_change', '0'))
    except (TypeError, ValueError):
        messages.error(request, "Enter a valid whole-number quantity.")
        return redirect('resource_list')
    if quantity_change == 0:
        messages.error(request, "Quantity change cannot be zero.")
        return redirect('resource_list')

    with transaction.atomic():
        resource = Resource.objects.select_for_update().get(id=resource.id)
        new_quantity = resource.quantity + quantity_change
        if new_quantity < 0:
            messages.error(request, f"Cannot reduce '{resource.name}' below zero.")
            return redirect('resource_list')
        resource.quantity = new_quantity
        resource.status = (
            ResourceStatus.DEPLETED if new_quantity == 0
            else (ResourceStatus.RESERVED if quantity_change < 0 else ResourceStatus.AVAILABLE)
        )
        resource.save(update_fields=['quantity', 'status', 'updated_at'])
    action = "reserved" if quantity_change < 0 else "added"
    messages.success(request, f"{abs(quantity_change)} unit(s) {action} for '{resource.name}'.")
    return redirect('resource_list')


def _shelter_allocation_incidents_for_user(user):
    active_incidents = Incident.objects.exclude(
        status__in=[IncidentStatus.RESOLVED, IncidentStatus.CANCELLED]
    )
    if _is_admin_user(user) or _is_resource_manager(user):
        return active_incidents
    if _is_verified_responder(user):
        return active_incidents.filter(assigned_responder=user)
    return active_incidents.none()


def _scope_shelter_allocation_incidents(form, user, allowed_incidents):
    form.fields['incident'].queryset = allowed_incidents
    form.fields['shelter'].queryset = Shelter.objects.filter(
        status=ShelterStatus.OPEN,
        occupied_capacity__lt=F('total_capacity'),
    )


# ---------------------------------------------------------
# Dynamic Analytics API (Module 8)
# ---------------------------------------------------------

@require_GET
def api_incident_stats(request):
    """Returns dynamic database-backed statistics for live dashboard charts and telemetry."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required.'}, status=401)
    if not _is_admin_user(request.user):
        return JsonResponse({'error': 'Administrator access required.'}, status=403)

    priority_data = {
        'CRITICAL': Incident.objects.filter(priority_level=PriorityLevel.CRITICAL).count(),
        'HIGH': Incident.objects.filter(priority_level=PriorityLevel.HIGH).count(),
        'MEDIUM': Incident.objects.filter(priority_level=PriorityLevel.MEDIUM).count(),
        'LOW': Incident.objects.filter(priority_level=PriorityLevel.LOW).count(),
    }
    status_data = {
        'REPORTED': Incident.objects.filter(status=IncidentStatus.REPORTED).count(),
        'TRIAGED': Incident.objects.filter(status=IncidentStatus.TRIAGED).count(),
        'ASSIGNED': Incident.objects.filter(status=IncidentStatus.ASSIGNED).count(),
        'ACCEPTED': Incident.objects.filter(status=IncidentStatus.ACCEPTED).count(),
        'RESPONDING': Incident.objects.filter(status=IncidentStatus.RESPONDING).count(),
        'RESOLVED': Incident.objects.filter(status=IncidentStatus.RESOLVED).count(),
        'UNASSIGNED': Incident.objects.filter(status=IncidentStatus.UNASSIGNED).count(),
    }
    total_shelters = Shelter.objects.count()
    open_shelters = Shelter.objects.filter(status=ShelterStatus.OPEN).count()
    shelter_spots_free = sum(s.available_capacity for s in Shelter.objects.all())

    return JsonResponse({
        'priorities': priority_data,
        'statuses': status_data,
        'total_active': Incident.objects.exclude(status__in=[IncidentStatus.RESOLVED, IncidentStatus.CANCELLED]).count(),
        'critical_active': Incident.objects.filter(priority_level=PriorityLevel.CRITICAL).exclude(status__in=[IncidentStatus.RESOLVED, IncidentStatus.CANCELLED]).count(),
        'unassigned_count': Incident.objects.filter(status=IncidentStatus.UNASSIGNED).count(),
        'active_responders': ResponderProfile.objects.filter(verification_status=VerificationStatus.VERIFIED, availability=AvailabilityStatus.AVAILABLE).count(),
        'open_shelters': open_shelters,
        'shelter_spots_free': shelter_spots_free,
        'updated_at': timezone.now().strftime('%H:%M:%S'),
    })


@require_GET
def api_my_incident_status(request):
    """Returns only the caller's reported incidents for dashboard status refresh."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required.'}, status=401)

    incidents = Incident.objects.filter(reporter=request.user).order_by('-created_at')
    return JsonResponse({
        'incidents': [
            {
                'id': incident.incident_id,
                'status': incident.status,
                'status_display': incident.get_status_display(),
                'priority': incident.priority_level,
                'priority_score': incident.priority_score,
                'assigned_responder': (
                    incident.assigned_responder.get_full_name()
                    or incident.assigned_responder.username
                    if incident.assigned_responder
                    else None
                ),
                'updated_at': incident.updated_at.isoformat(),
            }
            for incident in incidents
        ],
        'updated_at': timezone.now().isoformat(),
    })
