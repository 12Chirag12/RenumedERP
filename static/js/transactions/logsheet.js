/**
 * Log sheet — customer → product → pending batch selection → save; grid by date range.
 * Double-layer products: colour dropdown sets layer slot; half quantities per colour.
 */
(function () {
  'use strict';

  function readJsonScript(id) {
    var el = document.getElementById(id);
    if (!el || !el.textContent) return {};
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return {};
    }
  }

  function esc(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function initPage_log_sheet() {
    var form = document.getElementById('lsForm');
    if (!form) return;

    var urls = readJsonScript('lsAjaxUrls');
    var gridDef = readJsonScript('lsGridDefaults') || {};
    var editPayload = readJsonScript('lsEditPayload');
    var isEdit = !!(editPayload && editPayload.logsheet_id);
    var editBootstrapDone = false;

    var customer = document.getElementById('lsCustomer');
    var product = document.getElementById('lsProduct');
    var pendingBody = document.getElementById('lsPendingBody');
    var gridBody = document.getElementById('lsGridBody');
    var gridErr = document.getElementById('lsGridErr');
    var gridStart = document.getElementById('lsGridStart');
    var gridEnd = document.getElementById('lsGridEnd');
    var batchDtl = document.getElementById('lsBatchDtlId');
    var layerSlotInput = document.getElementById('lsLayerSlot');
    var ordDisp = document.getElementById('lsOrdDisplay');
    var batchNoDisp = document.getElementById('lsBatchNoDisplay');
    var mfgValue = document.getElementById('lsMfgValue');
    var expValue = document.getElementById('lsExpValue');
    var mfgPicker = document.getElementById('lsMfgDatePicker');
    var expPicker = document.getElementById('lsExpDatePicker');
    var sizeLDisp = document.getElementById('lsBatchSizeL');
    var layerDisp = document.getElementById('lsTabletLayer');
    var colourSelect = document.getElementById('lsColour');

    var tabletLayer = '';
    var selectedBatch = null;
    var lastProductMeta = null;

    function monthToPickerValue(value) {
      var match = String(value || '').trim().toUpperCase().match(/^([A-Z]{3})-(\d{4})$/);
      if (!match) return '';
      var months = { JAN: '01', FEB: '02', MAR: '03', APR: '04', MAY: '05', JUN: '06', JUL: '07', AUG: '08', SEP: '09', OCT: '10', NOV: '11', DEC: '12' };
      return months[match[1]] ? match[2] + '-' + months[match[1]] + '-01' : '';
    }

    function pickerValueToMonth(value) {
      var match = String(value || '').match(/^(\d{4})-(\d{2})-\d{2}$/);
      if (!match) return '';
      var months = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
      return months[Number(match[2]) - 1] + '-' + match[1];
    }

    function syncDateValues() {
      if (mfgValue && mfgPicker) mfgValue.value = pickerValueToMonth(mfgPicker.value);
      if (expValue && expPicker) expValue.value = pickerValueToMonth(expPicker.value);
    }

    function loadDateValues(mfg, exp) {
      if (mfgValue) mfgValue.value = mfg || '';
      if (expValue) expValue.value = exp || '';
      if (mfgPicker) mfgPicker.value = monthToPickerValue(mfg);
      if (expPicker) expPicker.value = monthToPickerValue(exp);
    }

    if (gridStart && gridDef.start) gridStart.value = gridDef.start;
    if (gridEnd && gridDef.end) gridEnd.value = gridDef.end;

    if (typeof initSearchableDropdowns === 'function') {
      initSearchableDropdowns(form);
    }

    function clearColourSelect() {
      if (!colourSelect) return;
      colourSelect.innerHTML = '';
      var o = document.createElement('option');
      o.value = '';
      o.textContent = '—';
      colourSelect.appendChild(o);
      colourSelect.value = '';
      colourSelect.disabled = true;
    }

    function clearBatchPick() {
      selectedBatch = null;
      if (batchDtl) batchDtl.value = '';
      if (batchNoDisp) batchNoDisp.value = '';
      loadDateValues('', '');
      if (sizeLDisp) sizeLDisp.value = '';
      if (ordDisp) ordDisp.value = '';
      if (layerSlotInput) layerSlotInput.value = 'S';
      clearColourSelect();
    }

    /** Batch size (Lacs): plain decimal (dot separator), at most 2 decimal places. */
    function formatBatchSizeLDecimal(lac) {
      var x = parseFloat(String(lac).replace(',', '.'));
      if (!isFinite(x)) return lac == null ? '' : String(lac);
      return String(parseFloat(x.toFixed(2)));
    }

    function updateDoubleBatchSizeDisplay() {
      if (!selectedBatch || !sizeLDisp || !layerSlotInput) return;
      var slot = layerSlotInput.value;
      var l;
      if (slot === '1') {
        l = formatBatchSizeLDecimal(selectedBatch.split_qty_l_first);
      } else if (slot === '2') {
        l = formatBatchSizeLDecimal(selectedBatch.split_qty_l_second);
      } else {
        sizeLDisp.value = '';
        return;
      }
      sizeLDisp.value = l;
    }

    function applyColourSelectFromProduct(data) {
      if (!colourSelect) return;
      if (!data || data.error) {
        lastProductMeta = null;
        clearColourSelect();
        return;
      }
      lastProductMeta = data;
      var layer = data.tablet_layer || '';
      if (layer === 'Double') {
        colourSelect.innerHTML = '';
        var o0 = document.createElement('option');
        o0.value = '';
        o0.textContent = '— Select batch —';
        colourSelect.appendChild(o0);
        colourSelect.value = '';
        colourSelect.disabled = true;
        return;
      }
      var label = ((data.first_color || '') + '').trim() || ((data.colour_display || '') + '').trim() || '—';
      colourSelect.innerHTML = '';
      var o = document.createElement('option');
      o.value = 'S';
      o.textContent = label;
      colourSelect.appendChild(o);
      colourSelect.value = 'S';
      colourSelect.disabled = true;
    }

    function setProductOptions(rows) {
      if (!product) return;
      var cur = product.value;
      product.innerHTML = '<option value="">— Select product —</option>';
      (rows || []).forEach(function (r) {
        var o = document.createElement('option');
        o.value = r.prod_id;
        o.textContent = r.prod_name;
        product.appendChild(o);
      });
      if (isEdit && editPayload.product_id && !editBootstrapDone) {
        product.value = String(editPayload.product_id);
      } else if (cur && [].some.call(product.options, function (op) { return op.value === cur; })) {
        product.value = cur;
      }
      if (window.jQuery && product.classList.contains('searchable-dropdown')) {
        try {
          window.jQuery(product).select2('destroy');
        } catch (e1) { /* ignore */ }
      }
      if (typeof initSearchableDropdowns === 'function') initSearchableDropdowns(form);
    }

    function loadCustomerProducts() {
      lastProductMeta = null;
      if (!isEdit || editBootstrapDone) clearBatchPick();
      tabletLayer = '';
      if (layerDisp) layerDisp.value = '';
      if (!customer || !customer.value) {
        setProductOptions([]);
        if (pendingBody) pendingBody.innerHTML = '<tr><td colspan="3" class="ls-muted">Select customer and product…</td></tr>';
        return;
      }
      var u = urls.customerProducts + '?cust_id=' + encodeURIComponent(customer.value);
      if (isEdit && editPayload.product_id) {
        u += '&include_prod_id=' + encodeURIComponent(editPayload.product_id);
      }
      fetch(u, { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var prods = data.products || [];
          setProductOptions(prods);
          if (isEdit && editPayload.product_id && !editBootstrapDone) {
            product.value = String(editPayload.product_id);
            if (window.jQuery && product.classList.contains('searchable-dropdown')) {
              try { window.jQuery(product).val(String(editPayload.product_id)).trigger('change.select2'); } catch (e) {}
            }
            loadProductMetaAndPending();
          } else if (pendingBody) {
            pendingBody.innerHTML = prods.length
              ? '<tr><td colspan="3" class="ls-muted">Select a product…</td></tr>'
              : '<tr><td colspan="3" class="ls-muted">No products with pending batches for this customer.</td></tr>';
          }
        })
        .catch(function () {
          setProductOptions([]);
        });
    }

    function loadProductMetaAndPending() {
      lastProductMeta = null;
      if (!isEdit || editBootstrapDone) clearBatchPick();
      tabletLayer = '';
      if (layerDisp) layerDisp.value = '';
      if (!product || !product.value) {
        if (pendingBody) pendingBody.innerHTML = '<tr><td colspan="3" class="ls-muted">Select customer and product…</td></tr>';
        return;
      }
      var u = urls.productMeta + '?prod_id=' + encodeURIComponent(product.value);
      fetch(u, { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.error) {
            tabletLayer = '';
            if (layerDisp) layerDisp.value = '';
            applyColourSelectFromProduct(null);
            return;
          }
          tabletLayer = data.tablet_layer || '';
          if (layerDisp) layerDisp.value = data.tablet_layer || '';
          applyColourSelectFromProduct(data);
        })
        .catch(function () {
          tabletLayer = '';
          applyColourSelectFromProduct(null);
        });

      if (!customer || !customer.value) {
        if (pendingBody) pendingBody.innerHTML = '<tr><td colspan="3" class="ls-muted">Select customer first…</td></tr>';
        return;
      }
      var u2 = urls.pendingBatches + '?cust_id=' + encodeURIComponent(customer.value)
        + '&prod_id=' + encodeURIComponent(product.value);
      if (isEdit && editPayload.batch_dtl_id) {
        u2 += '&include_dtl_id=' + encodeURIComponent(editPayload.batch_dtl_id);
      }
      fetch(u2, { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.error || !data.batches || !data.batches.length) {
            if (pendingBody) {
              pendingBody.innerHTML = '<tr><td colspan="3" class="ls-muted">No pending batches for this selection.</td></tr>';
            }
            return;
          }
          if (!pendingBody) return;
          pendingBody.innerHTML = '';
          data.batches.forEach(function (b) {
            var tr = document.createElement('tr');
            tr.className = 'ls-pending-row';
            if (isEdit && String(b.dtl_id) === String(editPayload.batch_dtl_id)) {
              tr.classList.add('ls-pending-row--active');
            }
            tr.innerHTML = '<td>' + esc(b.batch_no) + '</td><td>' + esc(b.mfg_dt) + '</td><td>' + esc(b.exp_dt) + '</td>';
            tr.addEventListener('click', function () {
              selectPendingRow(b, tr);
            });
            pendingBody.appendChild(tr);

            if (isEdit && String(b.dtl_id) === String(editPayload.batch_dtl_id) && !editBootstrapDone) {
              selectPendingRow(b, tr);
              if (editPayload.layer_slot && layerSlotInput) {
                layerSlotInput.value = editPayload.layer_slot;
                if (colourSelect) colourSelect.value = editPayload.layer_slot;
                updateDoubleBatchSizeDisplay();
              }
              editBootstrapDone = true;
            }
          });
        })
        .catch(function () {
          if (pendingBody) pendingBody.innerHTML = '<tr><td colspan="3" class="ls-muted">Could not load batches.</td></tr>';
        });
    }

    function selectPendingRow(b, trEl) {
      selectedBatch = b;
      if (batchDtl) batchDtl.value = String(b.dtl_id);
      if (batchNoDisp) batchNoDisp.value = b.batch_no || '';
      loadDateValues(b.mfg_dt || '', b.exp_dt || '');
      var ord = (b.cust_ord_id || '').trim();
      var dt = (b.ord_rec_dt || '').trim();
      if (ordDisp) ordDisp.value = ord && dt ? ord + ' / ' + dt : (ord || dt || '');

      var layer = b.tablet_layer || '';

      if (layer === 'Double' && colourSelect) {
        colourSelect.innerHTML = '';
        var o0 = document.createElement('option');
        o0.value = '';
        o0.textContent = '— Select colour —';
        colourSelect.appendChild(o0);
        var c1 = ((b.first_color || '') + '').trim() || 'First colour';
        var c2 = ((b.second_color || '') + '').trim() || 'Second colour';
        var logged = b.logged_slots || [];
        var o1 = document.createElement('option');
        o1.value = '1';
        o1.textContent = c1;
        if (logged.indexOf('1') >= 0 && (!isEdit || editPayload.layer_slot !== '1')) o1.disabled = true;
        colourSelect.appendChild(o1);
        var o2 = document.createElement('option');
        o2.value = '2';
        o2.textContent = c2;
        if (logged.indexOf('2') >= 0 && (!isEdit || editPayload.layer_slot !== '2')) o2.disabled = true;
        colourSelect.appendChild(o2);
        colourSelect.disabled = false;

        var p1d = logged.indexOf('1') >= 0 && (!isEdit || editPayload.layer_slot !== '1');
        var p2d = logged.indexOf('2') >= 0 && (!isEdit || editPayload.layer_slot !== '2');
        if (layerSlotInput) {
          if (isEdit && editPayload.layer_slot) {
            colourSelect.value = editPayload.layer_slot;
            layerSlotInput.value = editPayload.layer_slot;
          } else if (!p1d && p2d) {
            colourSelect.value = '1';
            layerSlotInput.value = '1';
          } else if (p1d && !p2d) {
            colourSelect.value = '2';
            layerSlotInput.value = '2';
          } else if (!p1d && !p2d) {
            colourSelect.value = '1';
            layerSlotInput.value = '1';
          } else {
            colourSelect.value = '';
            layerSlotInput.value = '';
          }
        }
        updateDoubleBatchSizeDisplay();
      } else {
        if (colourSelect) {
          var lbl = ((b.first_color || '') + '').trim() || '—';
          colourSelect.innerHTML = '';
          var os = document.createElement('option');
          os.value = 'S';
          os.textContent = lbl;
          colourSelect.appendChild(os);
          colourSelect.value = 'S';
          colourSelect.disabled = true;
        }
        if (layerSlotInput) layerSlotInput.value = 'S';
        if (sizeLDisp) sizeLDisp.value = formatBatchSizeLDecimal(b.batch_qty_l);
      }

      if (pendingBody) {
        pendingBody.querySelectorAll('tr.ls-pending-row').forEach(function (tr) {
          tr.classList.remove('ls-pending-row--active');
        });
      }
      if (trEl) trEl.classList.add('ls-pending-row--active');
    }

    function loadGrid() {
      if (!gridStart || !gridEnd || !gridBody || !gridErr) return;
      gridErr.textContent = '';
      var s = gridStart.value;
      var e = gridEnd.value;
      if (!s || !e) {
        gridErr.textContent = 'Choose start and end dates.';
        return;
      }
      var editBase = (window.location.pathname || '').split('?')[0];
      var u = urls.listRows + '?start=' + encodeURIComponent(s) + '&end=' + encodeURIComponent(e);
      fetch(u, { credentials: 'same-origin' })
        .then(function (r) {
          if (!r.ok) return r.json().then(function (j) { throw new Error(j.error || r.statusText); });
          return r.json();
        })
        .then(function (data) {
          gridBody.innerHTML = '';
          if (!data.rows || !data.rows.length) {
            gridBody.innerHTML = '<tr><td colspan="9" class="ls-muted">No log sheets in this range.</td></tr>';
            return;
          }
          data.rows.forEach(function (row) {
            var tr = document.createElement('tr');
            if (isEdit && String(row.logsheet_id) === String(editPayload.logsheet_id)) {
              tr.classList.add('row-editing');
            }
            var editHref = editBase + '?edit_pk=' + encodeURIComponent(row.logsheet_id);
            tr.innerHTML = '<td>' + esc(row.section) + '</td><td>' + esc(row.gran_shift) + '</td><td>'
              + esc(row.product) + '</td><td>'
              + esc(row.batch_summary) + '</td><td>'
              + esc(row.layer_slot) + '</td><td>'
              + esc(row.mfg_exp) + '</td><td>'
              + esc(row.blend_dt) + '</td><td>'
              + esc(row.customer) + '</td>'
              + '<td class="col-actions">'
              + '<a href="' + esc(editHref) + '" class="btn-action btn-edit" title="Edit"><i class="bi bi-pencil"></i></a>'
              + '<button type="button" class="btn-action btn-delete" data-delete-url="' + esc(row.delete_url) + '" data-delete-name="Log sheet #' + esc(row.logsheet_id) + '" onclick="openDeleteModal(this.dataset.deleteUrl, this.dataset.deleteName)"><i class="bi bi-trash"></i></button>'
              + '</td>';
            gridBody.appendChild(tr);
          });
        })
        .catch(function (err) {
          gridBody.innerHTML = '<tr><td colspan="9" class="ls-muted">—</td></tr>';
          gridErr.textContent = err.message || 'Could not load data.';
        });
    }

    form.addEventListener('change', function (ev) {
      if (ev.target === mfgPicker || ev.target === expPicker) syncDateValues();
      if (ev.target.id === 'lsColour') {
        if (layerSlotInput) layerSlotInput.value = colourSelect.value || '';
        updateDoubleBatchSizeDisplay();
      }
    });

    form.addEventListener('submit', function (e) {
      syncDateValues();
      if (selectedBatch && (selectedBatch.tablet_layer || '') === 'Double') {
        var v = layerSlotInput ? layerSlotInput.value : '';
        if (v !== '1' && v !== '2') {
          e.preventDefault();
          alert('Select a colour for this double-layer batch.');
          return false;
        }
      }
    });

    if (customer) customer.addEventListener('change', loadCustomerProducts);
    if (product) product.addEventListener('change', loadProductMetaAndPending);

    var showGrid = document.getElementById('lsShowGrid');
    if (showGrid) showGrid.addEventListener('click', loadGrid);

    // Initial hydration for edit mode
    if (isEdit) {
      if (batchDtl) batchDtl.value = String(editPayload.batch_dtl_id || '');
      if (batchNoDisp) batchNoDisp.value = editPayload.batch_no || '';
      loadDateValues(editPayload.mfg_dt || '', editPayload.exp_dt || '');
      if (ordDisp) ordDisp.value = editPayload.ord_display || '';
      if (layerDisp) layerDisp.value = editPayload.tablet_layer || '';
      if (layerSlotInput) layerSlotInput.value = editPayload.layer_slot || 'S';

      if (editPayload.tablet_layer === 'Double') {
        if (colourSelect) {
          colourSelect.innerHTML = '';
          var o0 = document.createElement('option');
          o0.value = '';
          o0.textContent = '— Select colour —';
          colourSelect.appendChild(o0);
          var c1 = editPayload.first_color || 'First colour';
          var c2 = editPayload.second_color || 'Second colour';
          var o1 = document.createElement('option');
          o1.value = '1';
          o1.textContent = c1;
          colourSelect.appendChild(o1);
          var o2 = document.createElement('option');
          o2.value = '2';
          o2.textContent = c2;
          colourSelect.appendChild(o2);
          colourSelect.disabled = false;
          colourSelect.value = editPayload.layer_slot || '1';
        }
        if (sizeLDisp) {
          var slot = editPayload.layer_slot;
          if (slot === '1') sizeLDisp.value = formatBatchSizeLDecimal(editPayload.split_qty_l_first);
          else if (slot === '2') sizeLDisp.value = formatBatchSizeLDecimal(editPayload.split_qty_l_second);
        }
      } else {
        if (colourSelect) {
          colourSelect.innerHTML = '';
          var os = document.createElement('option');
          os.value = 'S';
          os.textContent = editPayload.first_color || '—';
          colourSelect.appendChild(os);
          colourSelect.value = 'S';
          colourSelect.disabled = true;
        }
        if (sizeLDisp) sizeLDisp.value = formatBatchSizeLDecimal(editPayload.batch_qty_l);
      }

      // Load products and grid immediately
      loadCustomerProducts();
      loadGrid();
    } else {
      if (customer && customer.value) loadCustomerProducts();
      if (product && product.value && customer && customer.value) loadProductMetaAndPending();
    }
  }

  window.initPage_log_sheet = initPage_log_sheet;
})();
