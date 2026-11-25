"""
Custom template filters for ResQGrid UI badges, formatting, and role views
"""

from django import template

register = template.Library()


@register.filter
def priority_badge_class(level):
    mapping = {
        'CRITICAL': 'badge-priority-critical',
        'HIGH': 'badge-priority-high',
        'MEDIUM': 'badge-priority-medium',
        'LOW': 'badge-priority-low',
    }
    return mapping.get(level, 'badge-priority-unknown')


@register.filter
def status_badge_class(status):
    mapping = {
        'REPORTED': 'bg-light text-dark border',
        'TRIAGED': 'bg-info text-dark',
        'ASSIGNED': 'bg-primary text-white',
        'ACCEPTED': 'bg-warning text-dark',
        'RESPONDING': 'bg-primary text-white text-uppercase',
        'RESOLVED': 'bg-success text-white',
        'CANCELLED': 'bg-dark text-white',
        'UNASSIGNED': 'bg-danger text-white',
    }
    return mapping.get(status, 'bg-secondary text-white')


@register.filter
def shelter_status_badge(status):
    mapping = {
        'OPEN': 'bg-success text-white',
        'FULL': 'bg-danger text-white',
        'CLOSED': 'bg-secondary text-white',
    }
    return mapping.get(status, 'bg-secondary text-white')


@register.filter
def comma_split(val):
    if not val:
        return []
    return [x.strip() for x in str(val).split(',') if x.strip()]


@register.filter
def readable_tag(tag):
    return str(tag).replace('_', ' ').title()
