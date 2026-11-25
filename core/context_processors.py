"""
Global context processors for ResQGrid templates
"""
from django.conf import settings


def resqgrid_globals(request):
    is_admin = False
    is_responder = False
    is_citizen = False
    is_resource_manager = False
    profile = None
    responder_profile = None

    if request.user.is_authenticated:
        profile = getattr(request.user, 'profile', None)
        if profile:
            if profile.role == 'ADMIN' or request.user.is_superuser:
                is_admin = True
            elif profile.role == 'RESPONDER':
                is_responder = True
                responder_profile = getattr(request.user, 'responder_profile', None)
            elif profile.role == 'CITIZEN':
                is_citizen = True
            elif profile.role == 'RESOURCE_MANAGER':
                is_resource_manager = True
        elif request.user.is_superuser:
            is_admin = True

    return {
        'PROJECT_NAME': 'ResQGrid',
        'PROJECT_FULL_NAME': 'Intelligent Emergency Response & Humanitarian Coordination Network',
        'PROJECT_TAGLINE': 'Connecting Help. Saving Lives.',
        'PROJECT_TRACK': 'World Problem Solver',
        'EMERGENCY_DISCLAIMER': 'This is an emergency coordination prototype, NOT a replacement for official emergency services (e.g. Bangladesh 999). In life-threatening emergencies, also dial official emergency hotlines.',
        'user_profile': profile,
        'user_responder_profile': responder_profile,
        'is_admin_user': is_admin,
        'is_responder_user': is_responder,
        'is_citizen_user': is_citizen,
        'is_resource_manager_user': is_resource_manager,
        'CARTO_API_KEY': settings.CARTO_API_KEY,
    }
