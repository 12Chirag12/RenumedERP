from .access import build_sidebar_menu, user_can_manage_access


def erp_access(request):
    if not request.user.is_authenticated:
        return {
            'erp_menu': {'sections': []},
            'user_can_manage_access': False,
        }
    return {
        'erp_menu': build_sidebar_menu(request.user),
        'user_can_manage_access': user_can_manage_access(request.user),
    }
