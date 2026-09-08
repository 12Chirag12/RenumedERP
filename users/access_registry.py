"""
Single source of truth for ERP module permissions.

Change group access in the Access Control UI (DB). Add new screens here once,
then run: python manage.py sync_access_permissions

Role-based groups: seeded from ROLE_GROUP_PRESETS.
Department-based groups: DEPARTMENT_GROUP_NAMES with empty presets for now.
"""

from __future__ import annotations

GROUP_TYPE_ROLE = 'role'
GROUP_TYPE_DEPARTMENT = 'department'

BUNDLE_ACCESS_FULL = 'access.full'
BUNDLE_TRANSACTIONS_FULL = 'transactions.full'
BUNDLE_REPORTS_FULL = 'reports.full'

BUNDLE_CODENAMES = frozenset({
    BUNDLE_ACCESS_FULL,
    BUNDLE_TRANSACTIONS_FULL,
    BUNDLE_REPORTS_FULL,
})


def _m(codename, label, url_name, url_names=None, *, app_namespace=None, show_in_menu=True):
    return {
        'codename': codename,
        'label': label,
        'url_name': url_name,
        'url_names': list(url_names or []),
        'app_namespace': app_namespace,
        'show_in_menu': show_in_menu,
    }


ACCESS_SECTIONS = (
    {
        'key': 'masters',
        'label': 'Masters',
        'modules': [
            _m('masters.section', 'Section', 'section',
               ['section_delete', 'section_dept_ajax']),
            _m('masters.machine', 'Machines', 'machine', ['machine_delete']),
            _m('masters.operator', 'Operators', 'operator', ['operator_delete']),
            _m('masters.product_attr', 'Product Attributes', 'product_attr',
               ['product_attr_delete', 'product_attr_records_ajax']),
            _m('masters.uom', 'Unit Of Measurement (UOM)', 'uom', ['uom_delete']),
            _m('masters.prod_stage', 'Production Stage', 'prod_stage', ['prod_stage_delete']),
            _m('masters.logistics', 'Logistics', 'logistics',
               ['logistics_delete', 'logistics_records_ajax']),
            _m('masters.item_type', 'Item Types', 'item_type', ['item_type_delete']),
            _m('masters.pkg_style', 'Packing Style', 'pkg_style', ['pkg_style_delete']),
            _m('masters.expenses', 'Expenses', 'expenses', ['expenses_delete']),
            _m('masters.item', 'Items', 'item',
               ['item_delete', 'item_type_category_ajax']),
            _m('masters.product', 'Products', 'product', ['product_delete']),
            _m('masters.customer', 'Customer', 'customer',
               ['customer_delete', 'customer_products_ajax']),
            _m('masters.supplier', 'Supplier', 'supplier', ['supplier_delete']),
            _m('masters.bom', 'BOM', 'bom',
               ['bom_delete', 'bom_records_ajax', 'item_uom_ajax', 'product_type_ajax']),
        ],
    },
    {
        'key': 'transactions',
        'label': 'Transactions',
        'app_namespace': 'transactions',
        'modules': [
            _m('transactions.inward', 'Inward (GRN)', 'inward',
               ['inward_delete', 'inward_items_ajax', 'inward_item_meta_ajax',
                'inward_next_numbers_ajax', 'suggest_grn_api'],
               app_namespace='transactions'),
            _m('transactions.sales_order', 'Sales order', 'sales_order',
               ['sales_order_delete', 'sales_order_product_meta_ajax',
                'sales_order_customer_products_ajax'],
               app_namespace='transactions'),
            _m('transactions.sales_invoice', 'Sales invoice', 'sales_invoice',
               ['sales_invoice_delete', 'sales_invoice_next_numbers_ajax',
                'sales_invoice_orders_ajax', 'sales_invoice_fg_batches_ajax',
                'sales_invoice_order_detail_ajax', 'sales_invoice_order_products_ajax'],
               app_namespace='transactions'),
            _m('transactions.batch_allocation', 'Batch allocation', 'batch_allocation',
               ['batch_allocation_orders_ajax', 'batch_allocation_order_detail_ajax',
                'batch_allocation_products_ajax', 'batch_allocation_previous_batches_ajax'],
               app_namespace='transactions'),
            _m('transactions.log_sheet', 'Log sheet', 'log_sheet',
               ['logsheet_customer_products_ajax', 'logsheet_pending_batches_ajax',
                'logsheet_product_meta_ajax', 'logsheet_list_ajax'],
               app_namespace='transactions'),
            _m('transactions.rm_dispensing', 'Dispensing (RM)', 'rm_dispensing',
               ['rm_dispensing_customer_products_ajax', 'rm_dispensing_batches_ajax',
                'rm_dispensing_specs_ajax', 'rm_dispensing_bom_items_ajax',
                'rm_dispensing_list_ajax'],
               app_namespace='transactions'),
            # Permission only until PM dispensing screen is built (no URL yet).
            _m('transactions.pm_dispensing', 'Dispensing (PM)', None,
               app_namespace='transactions', show_in_menu=False),
            _m('transactions.dpr', 'Daily production report (DPR)', 'dpr',
               ['dpr_machines_ajax', 'dpr_operators_ajax', 'dpr_customer_products_ajax',
                'dpr_logsheets_ajax', 'dpr_specs_ajax', 'dpr_section_status_ajax', 'dpr_list_ajax'],
               app_namespace='transactions'),
            _m('transactions.pkg_cont', 'Daily packing (contractors)', 'pkg_cont',
               ['pkg_cont_delete', 'pkg_cont_products_ajax', 'pkg_cont_styles_ajax',
                'pkg_cont_list_ajax'],
               app_namespace='transactions'),
        ],
    },
    {
        'key': 'reports',
        'label': 'Reports',
        'modules': [
            _m('reports.master', 'Master Reports', 'master_reports',
               ['master_report_config', 'master_report_options', 'master_report_data',
                'master_report_export_excel']),
            _m('reports.transaction', 'Transaction Reports', 'transaction_reports',
               ['transaction_report_config', 'transaction_report_options',
                'transaction_report_data', 'transaction_report_export_excel']),
        ],
    },
    {
        'key': 'inventory',
        'label': 'Inventory',
        'app_namespace': 'inventory',
        'modules': [
            _m('inventory.stock', 'Inventory', 'inventory_stock',
               ['inventory_stock_lifecycle_ajax', 'customer_monthly_redirect'],
               app_namespace='inventory'),
            _m('inventory.stock_adjustment', 'Stock adjustment', 'stock_adjustment',
               ['stock_adj_masters_ajax', 'stock_adj_sku_meta_ajax',
                'stock_adj_inv_defaults_ajax'],
               app_namespace='inventory'),
        ],
    },
    {
        'key': 'utilities',
        'label': 'Utilities',
        'modules': [
            _m('utilities.user_management', 'User Management', 'user_list',
               ['create_user', 'change_user_password']),
            _m('utilities.change_password', 'Change Password', 'change_password'),
            _m('utilities.fy', 'Financial Years', 'admin_fy_management',
               ['admin_fy_toggle_status']),
            _m('utilities.backup', 'Database backup', 'admin_database_backup',
               ['admin_database_backup_run', 'admin_database_backup_settings',
                'admin_database_backup_delete', 'admin_database_backup_download']),
            _m('utilities.access_control', 'Access Control', 'access_control',
               ['access_control_save']),
        ],
    },
)

BUNDLE_DEFINITIONS = (
    {'codename': BUNDLE_ACCESS_FULL, 'label': 'Full access (all modules)'},
    {'codename': BUNDLE_TRANSACTIONS_FULL, 'label': 'All transactions'},
    {'codename': BUNDLE_REPORTS_FULL, 'label': 'All reports'},
)

ROLE_GROUP_NAMES = (
    'Directors',
    'Plant Manager',
    'IT Manager',
    'IT Executive',
    'Accounts',
)

_ALL_UTILITIES = [
    m['codename']
    for sec in ACCESS_SECTIONS
    if sec['key'] == 'utilities'
    for m in sec['modules']
]

ROLE_GROUP_PRESETS: dict[str, list[str]] = {
    'Directors': [BUNDLE_ACCESS_FULL, *_ALL_UTILITIES],
    'Plant Manager': [BUNDLE_ACCESS_FULL],
    'IT Manager': [BUNDLE_ACCESS_FULL, *_ALL_UTILITIES],
    'IT Executive': [BUNDLE_TRANSACTIONS_FULL, BUNDLE_REPORTS_FULL],
    'Accounts': [BUNDLE_TRANSACTIONS_FULL, BUNDLE_REPORTS_FULL],
}

DEPARTMENT_GROUP_NAMES = (
    'Stores',
    'Production',
    'Packing',
)

DEPARTMENT_GROUP_PRESETS: dict[str, list[str]] = {
    name: [] for name in DEPARTMENT_GROUP_NAMES
}


def _url_keys_for_module(module: dict, section: dict) -> list[str]:
    if not module.get('url_name'):
        return []
    ns = module.get('app_namespace') or section.get('app_namespace')
    names = [module['url_name']] + list(module.get('url_names') or [])
    keys = []
    for name in names:
        if ns:
            keys.append(f'{ns}:{name}')
        keys.append(name)
    return keys


def build_url_permission_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for section in ACCESS_SECTIONS:
        for module in section['modules']:
            codename = module['codename']
            for key in _url_keys_for_module(module, section):
                mapping.setdefault(key, codename)
    return mapping


URL_PERMISSION_MAP = build_url_permission_map()

EXEMPT_URL_NAMES = frozenset({
    'home',
    'login',
    'logout',
    'dashboard',
    'change_password',
})


def iter_grantable_codenames():
    for bundle in BUNDLE_DEFINITIONS:
        yield bundle['codename']
    for section in ACCESS_SECTIONS:
        for module in section['modules']:
            yield module['codename']


def all_modules_flat():
    for section in ACCESS_SECTIONS:
        for module in section['modules']:
            yield section, module
