"""
Access Control UI — single place to edit group permissions (role / department).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .access import (
    _apply_group_permissions,
    get_department_groups,
    get_role_groups,
    user_can_manage_access,
)
from .access_registry import (
    ACCESS_SECTIONS,
    BUNDLE_DEFINITIONS,
    GROUP_TYPE_DEPARTMENT,
    GROUP_TYPE_ROLE,
    iter_grantable_codenames,
)
def _require_access_manager(view_func):
    def _wrapped(request, *args, **kwargs):
        if not user_can_manage_access(request.user):
            messages.error(request, 'Access denied.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped


@login_required
@_require_access_manager
def access_control_view(request):
    group_type = request.GET.get('type', GROUP_TYPE_ROLE)
    if group_type not in (GROUP_TYPE_ROLE, GROUP_TYPE_DEPARTMENT):
        group_type = GROUP_TYPE_ROLE

    if group_type == GROUP_TYPE_ROLE:
        groups = list(get_role_groups())
    else:
        groups = list(get_department_groups())

    selected_id = request.GET.get('group')
    selected_group = None
    selected_codenames = set()
    if groups:
        if selected_id:
            selected_group = get_object_or_404(Group, pk=selected_id)
        else:
            selected_group = groups[0]
        selected_codenames = _group_module_codenames(selected_group)

    context = {
        'group_type': group_type,
        'groups': groups,
        'selected_group': selected_group,
        'selected_codenames': selected_codenames,
        'sections': ACCESS_SECTIONS,
        'bundles': BUNDLE_DEFINITIONS,
        'page_init': 'access_control',
    }
    return render(request, 'users/access_control.html', context)


@login_required
@require_POST
@_require_access_manager
def access_control_save_view(request):
    group_type = request.POST.get('group_type', GROUP_TYPE_ROLE)
    group_id = request.POST.get('group_id')
    group = get_object_or_404(Group, pk=group_id)

    meta = getattr(group, 'access_meta', None)
    if not meta or meta.group_type != group_type:
        messages.error(request, 'Invalid group type.')
        return redirect('access_control')

    selected = request.POST.getlist('permissions')
    valid = set(iter_grantable_codenames())
    codenames = [c for c in selected if c in valid]
    _apply_group_permissions(group, codenames)
    messages.success(request, f'Permissions updated for "{group.name}".')
    return redirect(
        f'{reverse("access_control")}?type={group_type}&group={group.pk}'
    )


def _group_module_codenames(group: Group) -> set[str]:
    from .access import django_codename_to_module

    out = set()
    for perm in group.permissions.all():
        module = django_codename_to_module(perm.codename)
        if module:
            out.add(module)
    return out
