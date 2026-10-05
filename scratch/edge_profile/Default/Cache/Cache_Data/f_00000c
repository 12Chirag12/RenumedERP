/**
 * static/js/masters/customer.js
 * Exposes window.initPage_customer()
 *
 * Two-step wizard — single <form>, shared state (same pattern as BOM):
 *   Step 1: Customer details   → [Clear] [Save Customer] [Add Products]
 *   Step 2: Product grid       → [← Back] (save only from step 1)
 *
 * State is NEVER reset on navigation. Inputs keep their DOM values.
 * Products live in the grid rows; serialised to JSON only on submit.
 *
 * Validation:
 *   Step 1 (enforced before advancing to Step 2):
 *     - cust_name   : required
 *     - short_name  : required, no spaces, max 10 chars
 *     - address     : required
 *     - state       : required
 *     - pin_code    : required, numeric, exactly 6 digits
 *     - landline_no : numeric, exactly 10 digits (if filled)
 *     - mobile_no   : numeric, exactly 10 digits (if filled)
 *     - pan_no      : exactly 10 chars (if filled)
 *   Step 2 (enforced on submit):
 *     - each row: product selected, batch abbr = exactly 3 characters
 *     - adv_license=Y → license_details required
 *     - no duplicate products
 */

function initPage_customer() {

  /* ── DOM refs ────────────────────────────────────────────── */
  var form           = document.getElementById('customerForm');
  var step1          = document.getElementById('step1');
  var step2          = document.getElementById('step2');
  var prodGridBody   = document.getElementById('prodGridBody');
  var prodGridEmpty  = document.getElementById('prodGridEmpty');
  var prodGridError  = document.getElementById('prodGridError');
  var prodGridErrMsg = document.getElementById('prodGridErrorMsg');
  var prodJsonHidden = document.getElementById('productsJsonHidden');
  var shortNameInput = document.getElementById('shortNameInput');
  var dot1           = document.getElementById('dot1');
  var dot2           = document.getElementById('dot2');
  var headerIcon     = document.getElementById('headerIcon');
  var headerTitle    = document.getElementById('headerTitle');
  var headerSub      = document.getElementById('headerSub');
  var btnSaveCustomer = document.getElementById('btnSaveCustomer');

  if (!form) return;

  /* ── Load page data injected by Django ───────────────────── */
  var allProducts  = [];
  var existingRows = [];
  var isEdit       = false;
  var pageData     = {};
  try {
    var dataEl = document.getElementById('custPageData');
    if (dataEl) {
      pageData       = JSON.parse(dataEl.textContent);
      allProducts    = pageData.allProducts  || [];
      existingRows   = pageData.existingProds || [];
      isEdit         = !!pageData.isEdit;
    }
  } catch (e) { /* silent */ }

  /* ── Current step tracker ────────────────────────────────── */
  var currentStep = 1;

  /* ── Header content per step ─────────────────────────────── */
  var HEADERS = {
    1: {
      icon:  isEdit ? 'bi-pencil-fill' : 'bi-person-plus',
      title: isEdit ? 'Edit Customer'  : 'New Customer',
      sub:   'Save from this step after adding products (use Add Products, then Back to save).'
    },
    2: {
      icon:  'bi-grid-3x3-gap',
      title: 'Product Details',
      sub:   'Add products ordered by this customer'
    }
  };

  function setHeader(step) {
    var h = HEADERS[step];
    if (headerIcon)  { headerIcon.className  = 'bi ' + h.icon; }
    if (headerTitle) { headerTitle.textContent = h.title; }
    if (headerSub)   { headerSub.textContent   = h.sub;   }
    if (dot1) { dot1.className = 'step-dot' + (step === 1 ? ' active' : ' done'); }
    if (dot2) { dot2.className = 'step-dot' + (step === 2 ? ' active' : '');      }
  }

  setHeader(1); // initialise

  /* ════════════════════════════════════════════════════════
     STEP NAVIGATION
  ════════════════════════════════════════════════════════ */

  /* Same idea as BOM: Save stays disabled until the grid has something to persist.
     Stricter than row count alone: at least one row must have a product selected. */
  function hasAtLeastOneProductSelected() {
    if (!prodGridBody) return false;
    var rows = prodGridBody.querySelectorAll('tr.prod-grid-row');
    for (var i = 0; i < rows.length; i++) {
      var sel = rows[i].querySelector('.prod-select');
      if (sel && sel.value && parseInt(sel.value, 10) > 0) return true;
    }
    return false;
  }

  function updateSaveState() {
    if (!btnSaveCustomer) return;
    var ok = hasAtLeastOneProductSelected();
    btnSaveCustomer.disabled = !ok;
    btnSaveCustomer.setAttribute('aria-disabled', ok ? 'false' : 'true');
  }

  window.goToProducts = function () {
    setErr('products_json', '');
    if (!validateStep1()) return;
    step1.style.display = 'none';
    step2.style.display = 'flex';
    step2.style.flexDirection = 'column';
    currentStep = 2;
    setHeader(2);
  };

  window.goBack = function () {
    clearGridError();
    step2.style.display = 'none';
    step1.style.display = 'flex';
    step1.style.flexDirection = 'column';
    currentStep = 1;
    setHeader(1);
    updateSaveState();
  };

  /* ════════════════════════════════════════════════════════
     STEP 1 VALIDATION
  ════════════════════════════════════════════════════════ */

  function setErr(id, msg) {
    var el = document.getElementById('err-' + id);
    if (!el) return;
    el.textContent = msg;
    /* highlight the input */
    var inp = document.getElementById(
      {cust_name:'custNameInput', short_name:'shortNameInput',
       address:'addressInput', state:'stateSelect',
       pin_code:'pinCodeInput', landline_no:'landlineInput',
       mobile_no:'mobileInput', pan_no:'panInput'}[id]
    );
    if (inp) {
      inp.classList.toggle('input-error', !!msg);
      if (msg) inp.setAttribute('aria-invalid', 'true');
      else inp.removeAttribute('aria-invalid');
    }
  }

  function clearAllErrors() {
    ['cust_name','short_name','address','state',
     'pin_code','landline_no','mobile_no','pan_no','products_json'].forEach(function (id) {
      setErr(id, '');
    });
  }

  function validateStep1() {
    clearAllErrors();
    var ok = true;

    var custName  = val('custNameInput');
    var shortName = val('shortNameInput');
    var address   = val('addressInput');
    var stateEl   = document.getElementById('stateSelect');
    var pinCode   = val('pinCodeInput');
    var landline  = val('landlineInput');
    var mobile    = val('mobileInput');
    var pan       = val('panInput');

    if (!custName)  { setErr('cust_name',  'Customer name is required.'); ok = false; }
    if (!shortName) { setErr('short_name', 'Short name is required.'); ok = false; }
    else if (/\s/.test(shortName)) { setErr('short_name', 'No spaces allowed.'); ok = false; }
    if (!address)   { setErr('address',    'Address is required.'); ok = false; }
    if (!stateEl || !stateEl.value) { setErr('state', 'Please select a state.'); ok = false; }

    /* Pin code: required, numeric, exactly 6 digits */
    if (!pinCode) {
      setErr('pin_code', 'Pin code is required.');
      ok = false;
    } else if (!/^\d+$/.test(pinCode)) {
      setErr('pin_code', 'Only digits allowed.');
      ok = false;
    } else if (pinCode.length !== 6) {
      setErr('pin_code', 'Must be exactly 6 digits.');
      ok = false;
    }

    /* Landline: numeric, exactly 10 digits if filled */
    if (landline) {
      if (!/^\d+$/.test(landline))    { setErr('landline_no', 'Only digits allowed.'); ok = false; }
      else if (landline.length !== 10){ setErr('landline_no', 'Must be exactly 10 digits.'); ok = false; }
    }

    /* Mobile: numeric, exactly 10 digits if filled */
    if (mobile) {
      if (!/^\d+$/.test(mobile))    { setErr('mobile_no', 'Only digits allowed.'); ok = false; }
      else if (mobile.length !== 10){ setErr('mobile_no', 'Must be exactly 10 digits.'); ok = false; }
    }

    /* PAN: exactly 10 chars if filled */
    if (pan && pan.length !== 10) {
      setErr('pan_no', 'PAN must be exactly 10 characters.'); ok = false;
    }

    return ok;
  }

  function val(id) {
    var el = document.getElementById(id);
    return el ? el.value.trim() : '';
  }

  /* ════════════════════════════════════════════════════════
     INPUT ENFORCERS (numeric-only, uppercase)
  ════════════════════════════════════════════════════════ */

  function numericOnly(el) {
    if (!el) return;
    el.addEventListener('input', function () {
      this.value = this.value.replace(/\D/g, '');
    });
    el.addEventListener('keypress', function (e) {
      if (!/\d/.test(e.key)) e.preventDefault();
    });
  }

  numericOnly(document.getElementById('pinCodeInput'));
  numericOnly(document.getElementById('landlineInput'));
  numericOnly(document.getElementById('mobileInput'));

  /* Short name: uppercase, no spaces */
  if (shortNameInput) {
    shortNameInput.addEventListener('input', function () {
      var pos = this.selectionStart;
      this.value = this.value.replace(/\s/g, '').toUpperCase();
      this.setSelectionRange(pos, pos);
    });
  }

  /* ════════════════════════════════════════════════════════
     PRODUCT GRID
  ════════════════════════════════════════════════════════ */

  function buildProductOptions(selectedId) {
    var html = '<option value="">— Select Product —</option>';
    allProducts.forEach(function (p) {
      html += '<option value="' + p.prod_id + '"'
            + (p.prod_id === selectedId ? ' selected' : '')
            + '>' + escHtml(p.prod_name) + '</option>';
    });
    return html;
  }

  function escHtml(s) {
    return String(s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;')
      .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  window.addProductRow = function (rowData) {
    rowData = rowData || {};
    var advLic   = rowData.adv_license     || 'N';
    var licDet   = rowData.license_details || '';
    var batch    = rowData.batch_abbr      || '';
    var prodId   = rowData.prod_id         || '';
    var licDis   = (advLic === 'N') ? 'disabled' : '';

    var tr = document.createElement('tr');
    tr.className = 'prod-grid-row';
    tr.innerHTML =
      '<td>' +
        '<select class="grid-select prod-select searchable-dropdown">' + buildProductOptions(Number(prodId)) + '</select>' +
      '</td>' +
      '<td>' +
        '<button type="button" class="lic-toggle active-' + advLic.toLowerCase() + '" ' +
               'data-val="' + advLic + '" onclick="toggleAdvLic(this)">' + advLic + '</button>' +
      '</td>' +
      '<td>' +
        '<input type="text" class="grid-input lic-details" placeholder="License number / details" ' +
               'value="' + escHtml(licDet) + '" ' + (licDis ? 'disabled' : '') + ' />' +
      '</td>' +
      '<td>' +
        '<input type="text" class="grid-input batch-abbr" placeholder="ABC" maxlength="3" ' +
               'value="' + escHtml(batch) + '" />' +
      '</td>' +
      '<td style="text-align:center;">' +
        '<button type="button" class="btn-del-row" onclick="removeProductRow(this)" title="Remove row">' +
          '<i class="bi bi-x"></i>' +
        '</button>' +
      '</td>';

    prodGridBody.appendChild(tr);
    if (typeof initSearchableDropdowns === 'function') initSearchableDropdowns(tr);
    updateGridEmpty();
    var prodSel = tr.querySelector('.prod-select');
    if (prodSel) {
      prodSel.addEventListener('change', updateSaveState);
    }
    updateSaveState();
  };

  window.toggleAdvLic = function (btn) {
    var next = (btn.dataset.val === 'N') ? 'Y' : 'N';
    btn.dataset.val  = next;
    btn.textContent  = next;
    btn.className    = 'lic-toggle active-' + next.toLowerCase();
    var licDet = btn.closest('tr').querySelector('.lic-details');
    if (licDet) {
      if (next === 'Y') { licDet.removeAttribute('disabled'); licDet.focus(); }
      else              { licDet.setAttribute('disabled', 'disabled'); licDet.value = ''; }
    }
  };

  window.removeProductRow = function (btn) {
    var row = btn.closest('tr');
    if (row) {
      var sel = row.querySelector('select.searchable-dropdown');
      if (sel && typeof destroySearchableDropdownsIn === 'function') destroySearchableDropdownsIn(sel);
      row.remove();
    }
    updateGridEmpty();
    updateSaveState();
  };

  function updateGridEmpty() {
    var has = prodGridBody.querySelectorAll('tr.prod-grid-row').length > 0;
    if (prodGridEmpty) prodGridEmpty.style.display = has ? 'none' : 'flex';
  }

  function showGridError(msg) {
    if (prodGridError)  prodGridError.style.display  = 'flex';
    if (prodGridErrMsg) prodGridErrMsg.textContent    = msg;
  }

  function clearGridError() {
    if (prodGridError)  prodGridError.style.display  = 'none';
    if (prodGridErrMsg) prodGridErrMsg.textContent    = '';
  }

  /* ════════════════════════════════════════════════════════
     GRID SERIALISATION + STEP 2 VALIDATION
  ════════════════════════════════════════════════════════ */

  function serializeGrid() {
    clearGridError();
    var rows    = prodGridBody.querySelectorAll('tr.prod-grid-row');
    var result  = [];
    var seenIds = {};
    var valid   = true;

    /* clear previous cell errors */
    document.querySelectorAll('.cell-err-msg').forEach(function (e) { e.remove(); });
    document.querySelectorAll('.cell-error').forEach(function (e) { e.classList.remove('cell-error'); });

    for (var i = 0; i < rows.length; i++) {
      var n       = i + 1;
      var prodSel = rows[i].querySelector('.prod-select');
      var licBtn  = rows[i].querySelector('.lic-toggle');
      var licDet  = rows[i].querySelector('.lic-details');
      var batchEl = rows[i].querySelector('.batch-abbr');

      var prodId  = prodSel  ? parseInt(prodSel.value, 10)             : 0;
      var advLic  = licBtn   ? licBtn.dataset.val                       : 'N';
      var licText = licDet   ? licDet.value.trim()                     : '';
      var batch   = batchEl  ? batchEl.value.trim().toUpperCase()      : '';

      if (!prodId) {
        addCellErr(prodSel, 'Select a product'); valid = false;
      } else if (seenIds[prodId]) {
        var name = prodSel.options[prodSel.selectedIndex].text;
        showGridError('Row ' + n + ': "' + name + '" is already added.');
        addCellErr(prodSel, 'Duplicate'); valid = false;
      }
      seenIds[prodId] = true;

      if (advLic === 'Y' && !licText) {
        addCellErr(licDet, 'Required when Adv-Lic is Y'); valid = false;
      }

      if (!batch || batch.length !== 3) {
        addCellErr(batchEl, 'Exactly 3 characters required'); valid = false;
      }

      // Always collect rows; return null at end if any error found.
      result.push({
        prod_id: prodId, adv_license: advLic,
        license_details: licText, batch_abbr: batch,
      });
    }

    if (!valid) return null;
    return result;
  }

  function addCellErr(el, msg) {
    if (!el) return;
    el.classList.add('cell-error');
    var span = document.createElement('span');
    span.className = 'cell-err-msg';
    span.textContent = msg;
    el.parentNode.appendChild(span);
  }

  /* ════════════════════════════════════════════════════════
     FORM SUBMIT — combine step 1 + step 2 data
  ════════════════════════════════════════════════════════ */

  function prepareProductsJsonForSubmit() {
    setErr('products_json', '');
    /* Re-run step 1 validation on submit (belt + braces) */
    if (!validateStep1()) {
      if (currentStep === 2) goBack();
      return false;
    }

    var gridData = serializeGrid();
    if (gridData === null) {
      goToProducts();
      return false;
    }

    if (gridData.length === 0) {
      setErr('products_json', 'Please add at least one product before saving (use Add Products).');
      return false;
    }

    if (prodJsonHidden) {
      prodJsonHidden.value = JSON.stringify(gridData);
    }
    return true;
  }

  // Normal full-page form submit
  form.addEventListener('submit', function (e) {
    if (!prepareProductsJsonForSubmit()) {
      e.preventDefault();
    }
  });

  function isThisFormHtmxRequest(e) {
    // htmx events reliably expose the issuing element as e.detail.elt
    var elt = e && e.detail && e.detail.elt;
    if (!elt) return false;
    if (elt === form) return true;
    // Often the issuing element is the submit button, not the form.
    if (typeof elt.closest === 'function') {
      return elt.closest('form') === form;
    }
    return false;
  }

  // HTMX boosted submit: ensure hidden field updated BEFORE HTMX serializes the form.
  document.body.addEventListener('htmx:configRequest', function (e) {
    if (!isThisFormHtmxRequest(e)) return;
    if (!prepareProductsJsonForSubmit()) {
      e.preventDefault(); // cancel HTMX request
    }
  });

  // Extra safety: some HTMX flows may bypass configRequest ordering.
  document.body.addEventListener('htmx:beforeRequest', function (e) {
    if (!isThisFormHtmxRequest(e)) return;
    if (!prepareProductsJsonForSubmit()) {
      e.preventDefault(); // cancel HTMX request
    }
  });

  /* ════════════════════════════════════════════════════════
     RESET FORM
  ════════════════════════════════════════════════════════ */

  window.resetForm = function () {
    if (typeof clearMasterFormValidationUI === 'function') clearMasterFormValidationUI(form);
    form.reset();
    if (prodGridBody) {
      if (typeof destroySearchableDropdownsIn === 'function') destroySearchableDropdownsIn(prodGridBody);
      prodGridBody.innerHTML = '';
    }
    updateGridEmpty();
    clearGridError();
    if (prodJsonHidden) prodJsonHidden.value = '[]';
    /* Always go back to step 1 */
    if (currentStep === 2) goBack();
    updateSaveState();
    var custNameInput = document.getElementById('custNameInput');
    if (custNameInput) custNameInput.focus();
  };

  /* ════════════════════════════════════════════════════════
     INIT — populate grid on edit, set initial step
  ════════════════════════════════════════════════════════ */

  if (existingRows && existingRows.length > 0) {
    existingRows.forEach(function (r) { addProductRow(r); });
  }
  if (prodGridBody && typeof initSearchableDropdowns === 'function') {
    initSearchableDropdowns(prodGridBody);
  }
  updateGridEmpty();
  updateSaveState();

  // Keep hidden field in sync on initial render too.
  // This avoids submitting a broken/old value when the user doesn't touch the grid.
  if (prodJsonHidden) {
    try {
      prodJsonHidden.value = JSON.stringify(existingRows || []);
    } catch (e) {
      prodJsonHidden.value = '[]';
    }
  }

  /* ── FIX 3: Auto-advance to step 2 when only product errors exist ──
     The server computes start_step = 2 when form.errors has product-grid
     errors but no step-1 field errors.  We jump directly (bypassing
     goToProducts → validateStep1) because the server already verified
     that step 1 is clean. */
  var startStep = Number(pageData.startStep) || 1;
  if (startStep === 2) {
    step1.style.display = 'none';
    step2.style.display = 'flex';
    step2.style.flexDirection = 'column';
    currentStep = 2;
    setHeader(2);
  }

  updateSaveState();
}

// Do NOT call initPage_customer() here.
// base.js DOMContentLoaded calls it on full page loads;
// base_partial.html inline script calls it on every HTMX swap.
// Calling it here as well causes double-init → duplicate grid rows
// → second submit listener sees duplicates → blocks Update.
window.initPage_customer = initPage_customer;

/**
 * Global safety net:
 * Some flows can submit the customer form before initPage_customer() runs
 * (or if it errors mid-way). This hook ensures products_json is always
 * derived from the current grid DOM right before request submission.
 *
 * It is intentionally lightweight and independent of the page init state.
 */
(function registerCustomerProductsSubmitHook() {
  if (window.__custProductsSubmitHookRegistered) return;
  window.__custProductsSubmitHookRegistered = true;

  function serializeGridFromDom(form) {
    var body = form.querySelector('#prodGridBody');
    if (!body) return null;
    var rows = body.querySelectorAll('tr.prod-grid-row');
    var result = [];

    for (var i = 0; i < rows.length; i++) {
      var prodSel = rows[i].querySelector('.prod-select');
      var licBtn  = rows[i].querySelector('.lic-toggle');
      var licDet  = rows[i].querySelector('.lic-details');
      var batchEl = rows[i].querySelector('.batch-abbr');

      var prodId  = prodSel ? parseInt(prodSel.value, 10) : 0;
      var advLic  = licBtn ? (licBtn.dataset.val || 'N') : 'N';
      var licText = licDet ? licDet.value.trim() : '';
      var batch   = batchEl ? batchEl.value.trim().toUpperCase() : '';

      // Only include rows that have at least a selected product;
      // validation is handled by the main page init, but this prevents
      // submitting a completely empty payload when rows exist.
      if (!prodId) continue;

      result.push({
        prod_id: prodId,
        adv_license: advLic,
        license_details: licText,
        batch_abbr: batch,
      });
    }
    return result;
  }

  function ensureHiddenUpdated(form) {
    var hidden = form.querySelector('#productsJsonHidden');
    if (!hidden) return;
    var data = serializeGridFromDom(form);
    if (data === null) return;
    hidden.value = JSON.stringify(data);
  }

  // Capture phase so it runs before any libraries serialize the form.
  document.addEventListener('submit', function (ev) {
    var f = ev.target;
    if (!f || f.id !== 'customerForm') return;
    ensureHiddenUpdated(f);
  }, true);

  // HTMX: update before request building. Works when elt is button or form.
  // Use document (not document.body) because this file is loaded in <head>.
  document.addEventListener('htmx:configRequest', function (e) {
    var elt = e && e.detail && e.detail.elt;
    if (!elt || typeof elt.closest !== 'function') return;
    var f = elt.closest('form');
    if (!f || f.id !== 'customerForm') return;
    ensureHiddenUpdated(f);
  });
})();