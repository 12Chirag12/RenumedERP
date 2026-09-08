"""
Permission helpers: checks, menu building, DB sync.
"""

from __future__ import annotations

from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType

from .access_registry import (
    ACCESS_SECTIONS,
    BUNDLE_ACCESS_FULL,
    BUNDLE_CODENAMES,
    BUNDLE_DEFINITIONS,
    BUNDLE_REPORTS_FULL,
    BUNDLE_TRANSACTIONS_FULL,
    DEPARTMENT_GROUP_NAMES,
    DEPARTMENT_GROUP_PRESETS,
    GROUP_TYPE_DEPARTMENT,
    GROUP_TYPE_ROLE,
    ROLE_GROUP_NAMES,
    ROLE_GROUP_PRESETS,
    iter_grantable_codenames,
)
from .models import AccessGroupMeta, AccessModule


def module_to_django_codename(module_codename: str) -> str:
    """ERP codename → Django permission codename on AccessModule."""
    if module_codename == BUNDLE_ACCESS_FULL:
        return 'access_full'
    if module_codename == BUNDLE_TRANSACTIONS_FULL:
        return 'access_transactions_full'
    if module_codename == BUNDLE_REPORTS_FULL:
        return 'access_reports_full'
    return 'access_' + module_codename.replace('.', '_')


def django_codename_to_module(codename: str) -> str | None:
    if not codename.startswith('access_'):
        return None
    body = codename[len('access_'):]
    if body == 'full':
        return BUNDLE_ACCESS_FULL
    if body == 'transactions_full':
        return BUNDLE_TRANSACTIONS_FULL
    if body == 'reports_full':
        return BUNDLE_REPORTS_FULL
    parts = body.split('_', 1)
    if len(parts) == 2:
        return f'{parts[0]}.{parts[1]}'
    return None


def _content_type() -> ContentType:
    return ContentType.objects.get_for_model(AccessModule)


def get_or_create_permission(module_codename: str, label: str) -> Permission:
    django_codename = module_to_django_codename(module_codename)
    perm, _ = Permission.objects.get_or_create(
        codename=django_codename,
        content_type=_content_type(),
        defaults={'name': label[:255]},
    )
    if perm.name != label[:255]:
        perm.name = label[:255]
        perm.save(update_fields=['name'])
    return perm


def sync_permissions() -> int:
    """Create/update all Permission rows from the registry."""
    AccessModule.objects.get_or_create(pk='erp', defaults={})
    count = 0
    for bundle in BUNDLE_DEFINITIONS:
        get_or_create_permission(bundle['codename'], bundle['label'])
        count += 1
    for section in ACCESS_SECTIONS:
        for module in section['modules']:
            get_or_create_permission(module['codename'], module['label'])
            count += 1
    return count


def _preset_for_group(name: str, group_type: str) -> list[str]:
    if group_type == GROUP_TYPE_ROLE:
        return list(ROLE_GROUP_PRESETS.get(name, []))
    return list(DEPARTMENT_GROUP_PRESETS.get(name, []))


def sync_groups(*, apply_presets: bool = False) -> int:
    """Ensure role/department groups exist with AccessGroupMeta."""
    count = 0
    for name in ROLE_GROUP_NAMES:
        group, _ = Group.objects.get_or_create(name=name)
        AccessGroupMeta.objects.get_or_create(
            group=group,
            defaults={'group_type': GROUP_TYPE_ROLE},
        )
        if apply_presets:
            _apply_group_permissions(group, _preset_for_group(name, GROUP_TYPE_ROLE))
        count += 1
    for name in DEPARTMENT_GROUP_NAMES:
        group, _ = Group.objects.get_or_create(name=name)
        AccessGroupMeta.objects.get_or_create(
            group=group,
            defaults={'group_type': GROUP_TYPE_DEPARTMENT},
        )
        if apply_presets:
            _apply_group_permissions(group, _preset_for_group(name, GROUP_TYPE_DEPARTMENT))
        count += 1
    return count


def _apply_group_permissions(group: Group, module_codenames: list[str]) -> None:
    ct = _content_type()
    perms = []
    for codename in module_codenames:
        django_codename = module_to_django_codename(codename)
        try:
            perms.append(
                Permission.objects.get(codename=django_codename, content_type=ct)
            )
        except Permission.DoesNotExist:
            label = codename
            for section in ACCESS_SECTIONS:
                for mod in section['modules']:
                    if mod['codename'] == codename:
                        label = mod['label']
                        break
            perms.append(get_or_create_permission(codename, label))
    group.permissions.set(perms)


def permissions_for_codenames(module_codenames: list[str]) -> list[Permission]:
    ct = _content_type()
    django_names = [module_to_django_codename(c) for c in module_codenames]
    return list(Permission.objects.filter(content_type=ct, codename__in=django_names))


def user_module_codenames(user: User) -> set[str]:
    """Module/bundle codenames granted to user via groups."""
    if not user.is_authenticated:
        return set()
    ct = _content_type()
    codenames = set()
    for perm in user.get_all_permissions():
        if not perm.startswith('users.'):
            continue
        django_codename = perm.split('.', 1)[1]
        try:
            p = Permission.objects.get(codename=django_codename, content_type=ct)
        except Permission.DoesNotExist:
            continue
        module = django_codename_to_module(p.codename)
        if module:
            codenames.add(module)
    return codenames


def user_has_access(user: User, module_codename: str) -> bool:
    if not user.is_authenticated:
        return False
    granted = user_module_codenames(user)
    if BUNDLE_ACCESS_FULL in granted:
        return True
    if module_codename in granted:
        return True
    if module_codename.startswith('transactions.') and BUNDLE_TRANSACTIONS_FULL in granted:
        return True
    if module_codename.startswith('reports.') and BUNDLE_REPORTS_FULL in granted:
        return True
    if module_codename in BUNDLE_CODENAMES:
        return module_codename in granted
    return False


def user_can_manage_access(user: User) -> bool:
    return user_has_access(user, 'utilities.access_control')


def get_role_groups():
    return Group.objects.filter(
        access_meta__group_type=GROUP_TYPE_ROLE,
    ).order_by('name')


def get_department_groups():
    return Group.objects.filter(
        access_meta__group_type=GROUP_TYPE_DEPARTMENT,
    ).order_by('name')


def build_sidebar_menu(user: User) -> dict:
    """Sections with visible modules for sidebar rendering."""
    granted = user_module_codenames(user)
    has_full = BUNDLE_ACCESS_FULL in granted
    has_tx_full = BUNDLE_TRANSACTIONS_FULL in granted or has_full
    has_rep_full = BUNDLE_REPORTS_FULL in granted or has_full

    def visible(codename: str) -> bool:
        if has_full:
            return True
        if codename in granted:
            return True
        if codename.startswith('transactions.') and has_tx_full:
            return True
        if codename.startswith('reports.') and has_rep_full:
            return True
        return False

    sections = []
    for section in ACCESS_SECTIONS:
        items = []
        for module in section['modules']:
            codename = module['codename']
            if codename == 'utilities.change_password':
                show = user.is_authenticated
            else:
                show = visible(codename)
            if show and module.get('show_in_menu', True) and module.get('url_name'):
                ns = module.get('app_namespace') or section.get('app_namespace')
                url_name = module['url_name']
                menu_url_name = f'{ns}:{url_name}' if ns else url_name
                items.append({
                    'label': module['label'],
                    'url_name': url_name,
                    'menu_url_name': menu_url_name,
                })
        if items:
            sections.append({
                'key': section['key'],
                'label': section.get('label', section['key'].title()),
                'items': items,
            })
    return {'sections': sections}
