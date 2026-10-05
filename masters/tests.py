import json
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from masters.models import MstCust, MstCustProd, MstProd, MstState, MstItemType, MstProdCat, MstUom
from masters.forms import CustomerForm
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
