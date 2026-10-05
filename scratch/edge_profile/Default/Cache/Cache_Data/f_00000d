function initPage_bom() {
  var form = document.getElementById('bomForm');
  if (!form) return;

  var data = {};
  try { data = JSON.parse(document.getElementById('bomPageData').textContent || '{}'); } catch (e) { data = {}; }

  var state = {
    bomType: data.bomType || 'rm',
    currentStep: 1,
    itemRows: Array.isArray(data.existingItems) ? data.existingItems : [],
    isLocked: !!data.isLocked,
    rmProductTypeLabel: '',
  };

  var step1 = document.getElementById('step1');
  var step2 = document.getElementById('step2');
  var dot1 = document.getElementById('dot1');
  var dot2 = document.getElementById('dot2');
  var gridBody = document.getElementById('bomGridBody');
  var gridEmpty = document.getElementById('bomGridEmpty');
  var itemsHidden = document.getElementById('bomItemsJsonHidden');
  var bomTypeHidden = document.getElementById('bomTypeHidden');
  var specPreview = document.getElementById('specNamePreview');
  var btnSaveBom = document.getElementById('btnSaveBom');

  function escHtml(s) { return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function byId(id) { return document.getElementById(id); }

  function setStep(step) {
    state.currentStep = step;
    step1.style.display = step === 1 ? 'flex' : 'none';
    step2.style.display = step === 2 ? 'flex' : 'none';
    dot1.className = 'step-dot' + (step === 1 ? ' active' : ' done');
    dot2.className = 'step-dot' + (step === 2 ? ' active' : '');
  }

  function setErr(name, msg) {
    var errEl = document.getElementById('err-' + name);
    if (errEl) errEl.textContent = msg || '';
  }

  function clearStep1Errors() {
    ['customer', 'product', 'machine',  'pkg_style', 'items_json', 'batch_size', 'batch_nos'].forEach(function (k) { setErr(k, ''); });
    ['bomRmCustomerSelect', 'bomPmCustomerSelect', 'bomRmProductSelect', 'bomPmProductSelect', 'bomRmMachineSelect', 'bomPmPkgStyleSelect', 'bomBatchSizeInput']
      .forEach(function (id) {
        var el = byId(id);
        if (el) {
          el.classList.remove('input-error');
          el.removeAttribute('aria-invalid');
        }
      });
  }

  function syncBatchNosFromSize() {
    var inp = byId('bomBatchSizeInput');
    var out = byId('bomBatchNosInput');
    if (!inp || !out || state.isLocked) return;
    var raw = String(inp.value || '').trim().replace(',', '.');
    var v = parseFloat(raw, 10);
    if (raw === '' || isNaN(v) || v < 0) {
      out.value = '';
      return;
    }
    out.value = String(Math.round(v * 100000));
  }

  function getSelectedText(el) {
    if (!el || !el.value || !el.selectedOptions || !el.selectedOptions.length) return '';
    return (el.selectedOptions[0].textContent || '').trim();
  }

  function fetchProductType() {
    var productSel = byId(state.bomType === 'rm' ? 'bomRmProductSelect' : 'bomPmProductSelect');
    if (!productSel || !productSel.value) return Promise.resolve('');
    return fetch('/masters/ajax/product-type/?prod_id=' + encodeURIComponent(productSel.value))
      .then(function (r) { return r.json(); })
      .then(function (d) { return (d.product_type || ''); })
      .catch(function () { return ''; });
  }

  function applyRmProductTypeRules(prodType) {
    var t = String(prodType || '').toLowerCase();
    var isTablet = t === 'tablet';
    var isCapsule = t === 'capsule';
    var machine = byId('bomRmMachineSelect');
    var no_of_lots = byId('bomRmNoOfLotsInput')
    var shape = byId('bomRmShapeSelect');
    var color = byId('bomRmColorSelect');
    var coating = byId('bomRmCoatingSelect');
    var capsule = byId('bomRmCapsuleSelect');
    var avgWt = byId('bomRmAvgWtInput');
    if (shape) shape.disabled = isCapsule || state.isLocked;
    if (color) color.disabled = isCapsule || state.isLocked;
    if (coating) coating.disabled = isCapsule || state.isLocked;
    if (capsule) capsule.disabled = isTablet || state.isLocked;
    if (avgWt) avgWt.disabled = state.isLocked;
  }

  function buildSpecName() {
    var customerSel = byId(state.bomType === 'rm' ? 'bomRmCustomerSelect' : 'bomPmCustomerSelect');
    var customerName = getSelectedText(customerSel);
    var customerShort = '';
    if (customerName) {
      var c = (data.customers || []).find(function (x) { return String(x.cust_id) === String(customerSel.value); });
      customerShort = c ? c.short_name : customerName;
    }
    if (state.bomType === 'pm') {
      var pkgStyle = getSelectedText(byId('bomPmPkgStyleSelect'));
      specPreview.value = [customerShort, pkgStyle].filter(Boolean).join(' / ');
      return;
    }
    var itemType = state.rmProductTypeLabel || '';
    var machine = getSelectedText(byId('bomRmMachineSelect'))
    var shape = getSelectedText(byId('bomRmShapeSelect'));
    var color = getSelectedText(byId('bomRmColorSelect'));
    var coating = getSelectedText(byId('bomRmCoatingSelect'));
    var avgWt = (byId('bomRmAvgWtInput') && byId('bomRmAvgWtInput').value) ? byId('bomRmAvgWtInput').value.trim() : '';
    var avgWtPart = avgWt ? (avgWt + 'mg') : '';
    specPreview.value = [customerShort, itemType, machine, shape, color, coating, avgWtPart].filter(Boolean).join(' / ');
  }

  function setSelectOptions(selectEl, options, placeholder) {
    if (!selectEl) return;
    var keep = String(selectEl.value || '');
    var html = '<option value="">' + (placeholder || '— Select —') + '</option>';
    (options || []).forEach(function (o) {
      html += '<option value="' + escHtml(o.value) + '">' + escHtml(o.label) + '</option>';
    });
    if (typeof destroySearchableDropdownsIn === 'function') destroySearchableDropdownsIn(selectEl.parentElement || selectEl);
    selectEl.innerHTML = html;
    // Restore selection if still present
    if (keep) {
      var found = false;
      selectEl.querySelectorAll('option').forEach(function (o) {
        if (String(o.value) === keep) found = true;
      });
      if (found) selectEl.value = keep;
    }
    if (typeof initSearchableDropdowns === 'function') initSearchableDropdowns(selectEl.parentElement || selectEl);
    try { selectEl.dispatchEvent(new Event('change', { bubbles: true })); } catch (e) {}
  }

  function fetchCustomerProducts(custId) {
    if (!custId) return Promise.resolve([]);
    return fetch('/masters/ajax/customer-products/?cust_id=' + encodeURIComponent(custId))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var rows = (d && d.rows) ? d.rows : [];
        return rows.map(function (x) {
          return { value: x.prod_id, label: x.prod_name };
        });
      })
      .catch(function () { return []; });
  }

  function refreshProductDropdown() {
    var custSel = byId(state.bomType === 'rm' ? 'bomRmCustomerSelect' : 'bomPmCustomerSelect');
    var prodSel = byId(state.bomType === 'rm' ? 'bomRmProductSelect' : 'bomPmProductSelect');
    var custId = custSel && custSel.value ? custSel.value : '';
    if (!prodSel) return Promise.resolve();
    if (!custId) {
      setSelectOptions(prodSel, [], '— Select Product —');
      state.rmProductTypeLabel = '';
      buildSpecName();
      return Promise.resolve();
    }
    return fetchCustomerProducts(custId).then(function (opts) {
      setSelectOptions(prodSel, opts, '— Select Product —');
      // ensure product-type cache updates after options refresh
      return fetchProductType().then(function (t) {
        state.rmProductTypeLabel = t || '';
        applyRmProductTypeRules(t);
        buildSpecName();
      });
    });
  }

  function renderGrid() {
    if (typeof destroySearchableDropdownsIn === 'function') destroySearchableDropdownsIn(gridBody);
    gridBody.innerHTML = '';
    state.itemRows.forEach(function (row) { addBomItemRow(row); });
    gridEmpty.style.display = state.itemRows.length ? 'none' : 'block';
    updateSaveState();
  }

  function stageOptions(selected) {
    var opts = '<option value="">— Select Stage —</option>';
    (data.stages || []).forEach(function (s) {
      opts += '<option value="' + s.stage_id + '"' + (String(s.stage_id) === String(selected) ? ' selected' : '') + '>' + escHtml(s.stage_name) + '</option>';
    });
    return opts;
  }
  function itemOptions(selected) {
    var opts = '<option value="">— Select Item —</option>';
    (data.items || []).forEach(function (i) {
      opts += '<option value="' + i.item_id + '"' + (String(i.item_id) === String(selected) ? ' selected' : '') + '>' + escHtml(i.item_name) + '</option>';
    });
    return opts;
  }

  function machineOptions(selected) {
    var opts = '<option value="">— Select Machine —</option>';
    (data.machines || []).forEach(function (m) {
      opts += '<option value="' + m.machine_id + '"' + (String(m.machine_id) === String(selected) ? ' selected' : '') + '>' + escHtml(m.machine_name) + '</option>';
    });
    return opts;
  }

  function rmMachineLotsCells(row) {
    if (state.bomType == 'rm') return '';
    return (
      '<td><select class="grid-select machine-select searchable-dropdown">' + machineOptions(row.machine_id) + '</select></td>' +
      '<td><input type="number" min="1" step="1" class="grid-input lots-input qty-col" value="' + escHtml(row.no_of_lots != null ? row.no_of_lots : '') + '"></td>'
    );
  }

  window.addBomItemRow = function (row) {
    row = row || {};
    var tr = document.createElement('tr');
    tr.className = 'prod-grid-row';
    tr.innerHTML =
      '<td><select class="grid-select stage-select searchable-dropdown">' + stageOptions(row.stage_id) + '</select></td>' +
      '<td><select class="grid-select item-select searchable-dropdown">' + itemOptions(row.item_id) + '</select></td>' +
      '<td><input type="number" min="0.001" step="0.001" class="grid-input qty-input qty-col" value="' + escHtml(row.qty || '') + '"></td>' +
      '<td><input type="text" class="grid-input uom-input" readonly value="' + escHtml(row.uom_name || '') + '"></td>' +
      '<td><button type="button" class="btn-del-row"><i class="bi bi-x"></i></button></td>';
    gridBody.appendChild(tr);
    if (typeof initSearchableDropdowns === 'function') initSearchableDropdowns(tr);
    tr.querySelector('.btn-del-row').addEventListener('click', function () {
      if (typeof destroySearchableDropdownsIn === 'function') destroySearchableDropdownsIn(tr);
      tr.remove();
      gridEmpty.style.display = gridBody.querySelectorAll('tr').length ? 'none' : 'block';
      updateSaveState();
    });
    tr.querySelector('.item-select').addEventListener('change', function () {
      var itemId = this.value;
      var uomEl = tr.querySelector('.uom-input');
      uomEl.value = '';
      if (!itemId) return;
      fetch('/masters/ajax/item-uom/?item_id=' + encodeURIComponent(itemId))
        .then(function (r) { return r.json(); })
        .then(function (d) {
          uomEl.value = d.uom_name || '';
          uomEl.title = d.error || '';
          updateSaveState();
        })
        .catch(function () {});
    });
    if (state.isLocked) {
      tr.querySelectorAll('select,input,button').forEach(function (el) { el.disabled = true; });
    }
    gridEmpty.style.display = 'none';
    updateSaveState();
  };

  function validateHeader() {
    clearStep1Errors();
    var valid = true;
    var customer = byId(state.bomType === 'rm' ? 'bomRmCustomerSelect' : 'bomPmCustomerSelect');
    var product = byId(state.bomType === 'rm' ? 'bomRmProductSelect' : 'bomPmProductSelect');
    if (!customer || !customer.value) {
      setErr('customer', 'Customer is required.');
      if (customer) {
        customer.classList.add('input-error');
        customer.setAttribute('aria-invalid', 'true');
      }
      valid = false;
    }
    if (!product || !product.value) {
      setErr('product', 'Product is required.');
      if (product) {
        product.classList.add('input-error');
        product.setAttribute('aria-invalid', 'true');
      }
      valid = false;
    }
    if (state.bomType === 'pm') {
      var pkg = byId('bomPmPkgStyleSelect');
      if (!pkg || !pkg.value) {
        setErr('pkg_style', 'Packing style is required.');
        if (pkg) {
          pkg.classList.add('input-error');
          pkg.setAttribute('aria-invalid', 'true');
        }
        valid = false;
      }
    }
    var batchSize = byId('bomBatchSizeInput');
    var bsRaw = batchSize ? String(batchSize.value || '').trim().replace(',', '.') : '';
    var bsNum = parseFloat(bsRaw, 10);
    if (!batchSize || bsRaw === '' || isNaN(bsNum) || bsNum < 0.01) {
      setErr('batch_size', 'Batch size (lakh) is required (min 0.01).');
      if (batchSize) {
        batchSize.classList.add('input-error');
        batchSize.setAttribute('aria-invalid', 'true');
      }
      valid = false;
    } else {
      syncBatchNosFromSize();
    }
    return valid;
  }

  function serializeGrid() {
    var rows = gridBody.querySelectorAll('tr');
    var out = [];
    var seen = {};
    for (var i = 0; i < rows.length; i++) {
      var stage = rows[i].querySelector('.stage-select').value;
      var item = rows[i].querySelector('.item-select').value;
      var qty = rows[i].querySelector('.qty-input').value;
      var uom = rows[i].querySelector('.uom-input').value;
      if (!stage || !item || !qty || Number(qty) <= 0) {
        return { rows: null, error: 'Each row needs Stage, Item, and Qty (> 0).' };
      }
      if (state.bomType === 'vm') {
        if (machine && (!lots || Number(lots) <= 0 || !Number.isInteger(Number(lots)))) {
          return { rows: null, error: 'Each row with a machine needs No. of Lots (whole number > 0).' };
        }
        if (lots && !machine) {
          return { rows: null, error: 'Select a machine when No. of Lots is entered.' };
        }
      }
      var key = stage + '::' + item;
      if (seen[key]) {
        return { rows: null, error: 'Duplicate Stage + Item is not allowed.' };
      }
      seen[key] = true;
      var payload = { stage_id: Number(stage), item_id: Number(item), qty: qty, uom_name: uom };
      if (state.bomType === 'vm') {
        if (machine) payload.machine_id = Number(machine);
        if (lots) payload.no_of_lots = Number(lots);
      }
      out.push(payload);
    }
    return { rows: out, error: '' };
  }

  function hasAtLeastOneItemRow() {
    return gridBody.querySelectorAll('tr.prod-grid-row').length > 0;
  }

  function updateSaveState() {
    if (!btnSaveBom || state.isLocked) return;
    btnSaveBom.disabled = !hasAtLeastOneItemRow();
  }

  function prepareItemsForSubmit(showError) {
    clearStep1Errors();
    if (!validateHeader()) return false;
    var res = serializeGrid();
    var serialized = res && res.rows ? res.rows : null;
    if (!serialized || !serialized.length) {
      if (showError) {
        // If the grid is the problem, always take the user to Step 2
        // (same UX as transaction wizards).
        setStep(2);
        setErr('items_json', (res && res.error) ? res.error : 'At least one item row is required before saving.');
      }
      return false;
    }
    itemsHidden.value = JSON.stringify(serialized);
    bomTypeHidden.value = state.bomType;
    return true;
  }

  window.goToBomItems = function () {
    if (!validateHeader()) return;
    setStep(2);
  };
  window.goBackToBomHeader = function () { setStep(1); };
  window.resetBomForm = function () {
    if (typeof clearMasterFormValidationUI === 'function') clearMasterFormValidationUI(form);
    form.reset();
    gridBody.innerHTML = '';
    gridEmpty.style.display = 'block';
    setStep(1);
    buildSpecName();
    syncBatchNosFromSize();
    updateSaveState();
  };

  form.addEventListener('submit', function (e) {
    if (!prepareItemsForSubmit(true)) e.preventDefault();
  });

  function isThisFormHtmxRequest(e) {
    var elt = e && e.detail && e.detail.elt;
    if (!elt) return false;
    if (elt === form) return true;
    return typeof elt.closest === 'function' && elt.closest('form') === form;
  }

  document.body.addEventListener('htmx:configRequest', function (e) {
    if (!isThisFormHtmxRequest(e)) return;
    if (!prepareItemsForSubmit(true)) e.preventDefault();
  });

  document.body.addEventListener('htmx:beforeRequest', function (e) {
    if (!isThisFormHtmxRequest(e)) return;
    if (!prepareItemsForSubmit(true)) e.preventDefault();
  });

  form.querySelectorAll('select,input').forEach(function (el) {
    if (el.id === 'bomBatchSizeInput') return;
    el.addEventListener('change', buildSpecName);
    el.addEventListener('input', buildSpecName);
  });

  var batchSizeInp = byId('bomBatchSizeInput');
  if (batchSizeInp) {
    batchSizeInp.addEventListener('input', function () {
      syncBatchNosFromSize();
      buildSpecName();
    });
    batchSizeInp.addEventListener('change', syncBatchNosFromSize);
  }

  var productSel = byId('bomRmProductSelect');
  if (productSel) {
    productSel.addEventListener('change', function () {
      fetchProductType().then(function (t) {
        state.rmProductTypeLabel = t || '';
        applyRmProductTypeRules(t);
        buildSpecName();
      });
    });
  }

  var custRm = byId('bomRmCustomerSelect');
  if (custRm) {
    custRm.addEventListener('change', function () {
      refreshProductDropdown();
    });
  }
  var custPm = byId('bomPmCustomerSelect');
  if (custPm) {
    custPm.addEventListener('change', function () {
      refreshProductDropdown();
    });
  }

  if (state.isLocked) {
    form.querySelectorAll('input,select,textarea,button').forEach(function (el) {
      if (el.type !== 'hidden') el.disabled = true;
    });
  }

  renderGrid();
  refreshProductDropdown().then(function () {
    return fetchProductType();
  }).then(function (t) {
    state.rmProductTypeLabel = t || '';
    applyRmProductTypeRules(t);
    buildSpecName();
  });
  buildSpecName();
  syncBatchNosFromSize();
  updateSaveState();
  if (Number(data.startStep || 1) === 2) setStep(2);
}

window.initPage_bom = initPage_bom;

/* Customer-form style safety net: always sync hidden grid JSON before submit. */
(function registerBomItemsSubmitHook() {
  if (window.__bomItemsSubmitHookRegistered) return;
  window.__bomItemsSubmitHookRegistered = true;

  function serializeGridFromDom(form) {
    var body = form.querySelector('#bomGridBody');
    if (!body) return null;
    var rows = body.querySelectorAll('tr.prod-grid-row');
    var out = [];
    for (var i = 0; i < rows.length; i++) {
      var stageEl = rows[i].querySelector('.stage-select');
      var itemEl = rows[i].querySelector('.item-select');
      var qtyEl = rows[i].querySelector('.qty-input');
      var uomEl = rows[i].querySelector('.uom-input');
      var stageId = stageEl ? parseInt(stageEl.value, 10) : 0;
      var itemId = itemEl ? parseInt(itemEl.value, 10) : 0;
      var qty = qtyEl ? qtyEl.value : '';
      if (!stageId || !itemId) continue;
      var rowPayload = {
        stage_id: stageId,
        item_id: itemId,
        qty: qty,
        uom_name: (uomEl && uomEl.value) ? uomEl.value : '',
      };
      out.push(rowPayload);
    }
    return out;
  }

  function ensureHiddenUpdated(form) {
    var hidden = form.querySelector('#bomItemsJsonHidden');
    if (!hidden) return;
    var rows = serializeGridFromDom(form);
    if (rows === null) return;
    hidden.value = JSON.stringify(rows);
  }

  document.addEventListener('submit', function (ev) {
    var f = ev.target;
    if (!f || f.id !== 'bomForm') return;
    ensureHiddenUpdated(f);
  }, true);

  // Use document (not document.body) because this file is loaded in <head>.
  document.addEventListener('htmx:configRequest', function (e) {
    var elt = e && e.detail && e.detail.elt;
    if (!elt || typeof elt.closest !== 'function') return;
    var f = elt.closest('form');
    if (!f || f.id !== 'bomForm') return;
    ensureHiddenUpdated(f);
  });
})();
