import json
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.http import QueryDict
from django.urls import reverse
from masters.models import (
    MstCust, MstCustProd, MstProd, MstState, MstItemType, MstProdCat, MstUom,
    MstDepartment, MstSection,
)
from masters.forms import CustomerForm, OperatorForm
from masters.views import customer_view

User = get_user_model()

class CustomerMasterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.state = MstState.objects.create(state_name='Maharashtra', gst_code='27')
        cls.uom = MstUom.objects.create(uom_name='Tablet', short_name='TAB')
        cls.cat = MstProdCat.objects.create(prod_cat_id='TB', prod_cat_name='Tablet')
        cls.item_type = MstItemType.objects.create(item_type_name='Finished Good', item_category=cls.cat)
        cls.prod1 = MstProd.objects.create(
            prod_name='Test Product 1', generic_name='Gen 1', prod_type=cls.item_type,
            prod_category=cls.cat, uom=cls.uom, tablet_layer='Single'
        )
        cls.prod2 = MstProd.objects.create(
            prod_name='Test Product 2', generic_name='Gen 2', prod_type=cls.item_type,
            prod_category=cls.cat, uom=cls.uom, tablet_layer='Single'
        )
        cls.user = User.objects.create_superuser('testadmin', 'test@example.com', 'pass123')

    def test_customer_form_get_initial_deduplicates(self):
        cust = MstCust.objects.create(
            cust_name='Acme Corp', short_name='ACME', address='123 Road', state=self.state, pin_code='400001'
        )
        # Create product row
        MstCustProd.objects.create(customer=cust, product=self.prod1, adv_license='N', batch_abbr='ACM')

        form = CustomerForm(instance=cust)
        initial = form.get_initial()
        rows = json.loads(initial['products_json'])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['prod_id'], self.prod1.prod_id)

    def test_clean_products_json_rejects_duplicates(self):
        form = CustomerForm(data={
            'cust_name': 'Beta Corp',
            'short_name': 'BETA',
            'address': '456 Street',
            'state': self.state.pk,
            'pin_code': '400002',
            'products_json': json.dumps([
                {'prod_id': self.prod1.prod_id, 'adv_license': 'N', 'license_details': '', 'batch_abbr': 'BET'},
                {'prod_id': self.prod1.prod_id, 'adv_license': 'N', 'license_details': '', 'batch_abbr': 'BET'},
            ])
        })
        self.assertFalse(form.is_valid())
        self.assertTrue('products_json' in form.errors)
        self.assertIn('listed more than once', form.errors['products_json'][0])

    def test_customer_view_post_sanitizes_duplicates(self):
        rf = RequestFactory()
        data = {
            'cust_name': 'Gamma Corp',
            'short_name': 'GAMMA',
            'address': '789 Ave',
            'state': self.state.pk,
            'pin_code': '400003',
            'products_json': json.dumps([
                {'prod_id': self.prod1.prod_id, 'adv_license': 'N', 'license_details': '', 'batch_abbr': 'GAM'},
                {'prod_id': self.prod1.prod_id, 'adv_license': 'N', 'license_details': '', 'batch_abbr': 'GAM'},
            ])
        }
        req = rf.post('/masters/customer/', data)
        req.user = self.user
        resp = customer_view(req)
        # Verify that response rendered without crashing
        self.assertEqual(resp.status_code, 200)


class OperatorFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department = MstDepartment.objects.create(dept_name='Production')
        cls.section = MstSection.objects.create(
            section_name='Granulation-I', department=cls.department,
        )
        cls.other_section = MstSection.objects.create(
            section_name='Packing', department=cls.department,
        )
        cls.admin_section = MstSection.objects.create(
            section_name='aDmIn', department=cls.department,
        )

    def operator_data(self, name, section_id):
        data = QueryDict('', mutable=True)
        data.update({'opt_name': name, 'designation': 'Operator'})
        data.setlist('sections', [str(section_id)])
        return data

    def test_section_choices_exclude_admin_case_insensitively(self):
        form = OperatorForm()

        self.assertEqual(
            [section.section_name for section in form.operator_section_list],
            ['Granulation-I', 'Packing'],
        )

    def test_new_sections_appear_in_a_fresh_form(self):
        MstSection.objects.create(
            section_name='Tablet Inspection', department=self.department,
        )

        form = OperatorForm()

        self.assertIn(
            'Tablet Inspection',
            [section.section_name for section in form.operator_section_list],
        )

    def test_sections_endpoint_returns_latest_sections_without_admin(self):
        user = User.objects.create_user(username='operator-test', password='pass12345')
        self.client.force_login(user)
        url = reverse('operator_sections_ajax')

        initial = self.client.get(url)
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(
            [section['name'] for section in initial.json()['sections']],
            ['Granulation-I', 'Packing'],
        )

        MstSection.objects.create(
            section_name='Tablet Inspection', department=self.department,
        )
        refreshed = self.client.get(url)
        self.assertEqual(
            [section['name'] for section in refreshed.json()['sections']],
            ['Granulation-I', 'Packing', 'Tablet Inspection'],
        )
        self.assertNotIn(
            'aDmIn',
            [section['name'] for section in refreshed.json()['sections']],
        )

    def test_save_and_edit_operator_section(self):
        form = OperatorForm(data=self.operator_data('John', self.section.pk))
        self.assertTrue(form.is_valid(), form.errors)
        operator = form.save()
        self.assertEqual(
            list(operator.section_links.values_list('section_id', flat=True)),
            [self.section.pk],
        )

        edit_form = OperatorForm(instance=operator)
        self.assertEqual(edit_form.get_initial()['sections'], [str(self.section.pk)])
        edit_form = OperatorForm(
            data=self.operator_data('John', self.other_section.pk),
            instance=operator,
        )
        self.assertTrue(edit_form.is_valid(), edit_form.errors)
        edit_form.save()
        self.assertEqual(
            list(operator.section_links.values_list('section_id', flat=True)),
            [self.other_section.pk],
        )

    def test_admin_section_id_is_rejected_on_submission(self):
        form = OperatorForm(
            data=self.operator_data('John', self.admin_section.pk),
        )

        self.assertFalse(form.is_valid())
        self.assertIn('Invalid section selection.', form.non_field_errors())

    def test_empty_valid_section_list_is_handled(self):
        MstSection.objects.filter(
            pk__in=[self.section.pk, self.other_section.pk],
        ).delete()
        form = OperatorForm()

        self.assertEqual(form.operator_section_list, [])
        no_selection = QueryDict('', mutable=True)
        no_selection.update({'opt_name': 'John', 'designation': 'Operator'})
        submitted_form = OperatorForm(
            data=no_selection,
        )
        self.assertFalse(submitted_form.is_valid())
        self.assertIn('Select at least one section.', submitted_form.non_field_errors())
