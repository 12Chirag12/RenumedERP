/**
 * static/js/masters/supplier.js
 * Client validation mirrors customer master step-1 rules (no product grid).
 */

function initPage_supplier() {
  var form = document.getElementById('supplierForm');
  if (!form) return;

  function val(id) {
    var el = document.getElementById(id);
    return el ? el.value.trim() : '';
  }

  function setErr(id, msg) {
    var el = document.getElementById('err-' + id);
    if (!el) return;
    el.textContent = msg;
    var inp = document.getElementById(
      {
        supl_name: 'suplNameInput',
        short_name: 'suppShortNameInput',
        address: 'suppAddressInput',
        state: 'suppStateSelect',
        pin_code: 'suppPinCodeInput',
        landline_no: 'suppLandlineInput',
        mobile_no: 'suppMobileInput',
        pan_no: 'suppPanInput',
      }[id]
    );
    if (inp) {
      inp.classList.toggle('input-error', !!msg);
      if (msg) inp.setAttribute('aria-invalid', 'true');
      else inp.removeAttribute('aria-invalid');
    }
  }

  function clearAllErrors() {
    ['supl_name', 'short_name', 'address', 'state', 'pin_code', 'landline_no', 'mobile_no', 'pan_no']
      .forEach(function (id) { setErr(id, ''); });
  }

  function validateSupplier() {
    clearAllErrors();
    var ok = true;

    var suplName = val('suplNameInput');
    var shortName = val('suppShortNameInput');
    var address = val('suppAddressInput');
    var stateEl = document.getElementById('suppStateSelect');
    var pinCode = val('suppPinCodeInput');
    var landline = val('suppLandlineInput');
    var mobile = val('suppMobileInput');
    var pan = val('suppPanInput');

    if (!suplName) { setErr('supl_name', 'Supplier name is required.'); ok = false; }
    // short_name is optional for suppliers; validate only when provided.
    if (shortName && /\s/.test(shortName)) { setErr('short_name', 'No spaces allowed.'); ok = false; }
    if (!address) { setErr('address', 'Address is required.'); ok = false; }
    if (!stateEl || !stateEl.value) { setErr('state', 'Please select a state.'); ok = false; }

    if (!pinCode) { setErr('pin_code', 'Pin code is required.'); ok = false; }
    else if (!/^\d+$/.test(pinCode)) { setErr('pin_code', 'Only digits allowed.'); ok = false; }
    else if (pinCode.length !== 6) { setErr('pin_code', 'Must be exactly 6 digits.'); ok = false; }

    if (landline) {
      if (!/^\d+$/.test(landline)) { setErr('landline_no', 'Only digits allowed.'); ok = false; }
      else if (landline.length !== 10) { setErr('landline_no', 'Must be exactly 10 digits.'); ok = false; }
    }
    if (mobile) {
      if (!/^\d+$/.test(mobile)) { setErr('mobile_no', 'Only digits allowed.'); ok = false; }
      else if (mobile.length !== 10) { setErr('mobile_no', 'Must be exactly 10 digits.'); ok = false; }
    }
    if (pan && pan.length !== 10) {
      setErr('pan_no', 'PAN must be exactly 10 characters.'); ok = false;
    }

    return ok;
  }

  function numericOnly(el) {
    if (!el) return;
    el.addEventListener('input', function () {
      this.value = this.value.replace(/\D/g, '');
    });
    el.addEventListener('keypress', function (e) {
      if (!/\d/.test(e.key)) e.preventDefault();
    });
  }

  numericOnly(document.getElementById('suppPinCodeInput'));
  numericOnly(document.getElementById('suppLandlineInput'));
  numericOnly(document.getElementById('suppMobileInput'));

  var shortNameInput = document.getElementById('suppShortNameInput');
  if (shortNameInput) {
    shortNameInput.addEventListener('input', function () {
      var pos = this.selectionStart;
      this.value = this.value.replace(/\s/g, '').toUpperCase();
      this.setSelectionRange(pos, pos);
    });
  }

  form.addEventListener('submit', function (e) {
    if (!validateSupplier()) e.preventDefault();
  });

  window.resetSupplierForm = function () {
    if (typeof clearMasterFormValidationUI === 'function') clearMasterFormValidationUI(form);
    form.reset();
    var n = document.getElementById('suplNameInput');
    if (n) n.focus();
  };
}

window.initPage_supplier = initPage_supplier;
