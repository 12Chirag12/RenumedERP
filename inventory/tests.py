from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from .transaction_posting import (
    _inward_item_inventory_postings,
    post_inward_to_inventory,
    reverse_inward_from_inventory,
)


class _Lines:
    def __init__(self, *lines):
        self._lines = lines

    def select_related(self, *_fields):
        return list(self._lines)


class InwardInventoryPostingTests(SimpleTestCase):
    def _objects(self, *, quantity='20', sample_qty='0'):
        item = SimpleNamespace(
            pk=34,
            item_category_id='RM',
            sample_qty=Decimal(sample_qty),
        )
        line = SimpleNamespace(
            item=item,
            item_id=item.pk,
            quantity=Decimal(quantity),
        )
        inward = SimpleNamespace(
            pk=9,
            customer_id=8,
            inward_dt=date(2026, 9, 12),
            lines=_Lines(line),
        )
        return line, inward

    def test_item_quantity_posts_once_without_batch(self):
        line, inward = self._objects(quantity='20', sample_qty='0')

        self.assertEqual(
            list(_inward_item_inventory_postings(line, inward)),
            [(None, Decimal('20.000'))],
        )

    def test_sample_quantity_is_deducted_from_item_total(self):
        line, inward = self._objects(quantity='20', sample_qty='0.250')

        self.assertEqual(
            list(_inward_item_inventory_postings(line, inward)),
            [(None, Decimal('19.750'))],
        )

    @patch('inventory.transaction_posting.reverse_inward_ledger')
    @patch('inventory.transaction_posting.post_inward_ledger')
    @patch('inventory.transaction_posting.inventory_apply_batch_delta')
    def test_post_and_reverse_use_the_same_unbatched_bucket(self, apply_delta, mock_post, mock_rev):
        _line, inward = self._objects(quantity='20', sample_qty='0')

        post_inward_to_inventory(inward)
        reverse_inward_from_inventory(inward)

        self.assertEqual(apply_delta.call_count, 2)
        posted, reversed_call = apply_delta.call_args_list
        self.assertEqual(posted.kwargs['batch_no'], '')
        self.assertIsNone(posted.kwargs['mfg_date'])
        self.assertIsNone(posted.kwargs['exp_date'])
        self.assertEqual(posted.kwargs['qty_delta'], Decimal('20.000'))
        self.assertEqual(reversed_call.kwargs['batch_no'], '')
        self.assertEqual(reversed_call.kwargs['qty_delta'], Decimal('-20.000'))

    def test_conversion_factor_multiplies_inward_quantity(self):
        # 1 kg inward with conversion factor 1000 -> 1000 grams in inventory
        item = SimpleNamespace(
            pk=35,
            item_category_id='RM',
            sample_qty=Decimal('0'),
            conversion_factor=Decimal('1000.0000'),
        )
        line = SimpleNamespace(
            item=item,
            item_id=item.pk,
            quantity=Decimal('1.000'),
        )
        inward = SimpleNamespace(
            pk=10,
            customer_id=8,
            inward_dt=date(2026, 9, 12),
            lines=_Lines(line),
        )
        self.assertEqual(
            list(_inward_item_inventory_postings(line, inward)),
            [(None, Decimal('1000.000'))],
        )

    def test_conversion_factor_with_sample_qty(self):
        # 2 kg inward with 0.1 kg sample -> 1.9 kg net * 1000 = 1900 grams
        item = SimpleNamespace(
            pk=36,
            item_category_id='RM',
            sample_qty=Decimal('0.100'),
            conversion_factor=Decimal('1000.0000'),
        )
        line = SimpleNamespace(
            item=item,
            item_id=item.pk,
            quantity=Decimal('2.000'),
        )
        inward = SimpleNamespace(
            pk=11,
            customer_id=8,
            inward_dt=date(2026, 9, 12),
            lines=_Lines(line),
        )
        self.assertEqual(
            list(_inward_item_inventory_postings(line, inward)),
            [(None, Decimal('1900.000'))],
        )
