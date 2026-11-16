/**
 * static/js/masters/product.js
 * Exposes window.initPage_product() so base_partial.html calls it after HTMX swap.
 *
 * Behaviour:
 *   1. Product Type change → AJAX → auto-fill Product Category display + hidden ID.
 *   2. Tablet Layer radio  → enable / disable First & Second Colour field wrappers.
 *   3. Image file input    → REPLACE preview (not accumulate) on every new selection.
 *   4. window.resetForm()  → resets all fields and UI state.
 */

function initPage_product() {

  var prodTypeSelect    = document.getElementById('prodTypeSelect');
  var catDisplay        = document.getElementById('prodCategoryDisplay');
  var catHidden         = document.getElementById('prodCategoryIdHidden');
  var layerRadios       = document.querySelectorAll('input[name="tablet_layer"]');
  var firstColorField   = document.getElementById('firstColorField');
  var secondColorField  = document.getElementById('secondColorField');
  var firstColorSelect  = document.getElementById('firstColorSelect');
  var secondColorSelect = document.getElementById('secondColorSelect');
  var imageInput        = document.getElementById('productImageInput');
  var imgPreview        = document.getElementById('imgPreview');
  var imgPlaceholder    = document.getElementById('imgPlaceholder');
  var uploadHint        = document.getElementById('uploadHint');

  if (!prodTypeSelect) return; // not on this page

  /* ── 1. Product Type → Category auto-fill (AJAX) ─────────── */
  prodTypeSelect.addEventListener('change', function () {
    var itemTypeId = this.value;
    if (!itemTypeId) { setCategoryDisplay('', ''); return; }

    fetch('/masters/ajax/item-type-category/?item_type_id=' + itemTypeId)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        setCategoryDisplay(data.prod_cat_id ? data.prod_cat_name : '', data.prod_cat_id || '');
      })
      .catch(function () { setCategoryDisplay('', ''); });
  });

  function setCategoryDisplay(name, id) {
    if (catDisplay) {
      catDisplay.value = name;
      catDisplay.classList.toggle('populated', !!name);
    }
    if (catHidden) { catHidden.value = id; }
  }

  /* ── 2. Tablet Layer → enable / disable colour fields ───────── */
  function applyLayerState(value) {
    var isDouble = (value === 'Double');
    toggleColorField(firstColorField,  firstColorSelect,  isDouble);
    toggleColorField(secondColorField, secondColorSelect, isDouble);
  }

  function toggleColorField(fieldEl, selectEl, enabled) {
    if (!fieldEl || !selectEl) return;
    if (enabled) {
      fieldEl.classList.remove('color-disabled');
      selectEl.removeAttribute('disabled');
    } else {
      fieldEl.classList.add('color-disabled');
      selectEl.setAttribute('disabled', 'disabled');
      selectEl.value = '';
    }
  }

  layerRadios.forEach(function (radio) {
    radio.addEventListener('change', function () { applyLayerState(this.value); });
  });

  // Apply on init (handles edit pre-fill and default 'Single')
  var checkedRadio = document.querySelector('input[name="tablet_layer"]:checked');
  applyLayerState(checkedRadio ? checkedRadio.value : 'Single');

  /* ── 3. Image file → REPLACE preview ───────────────────────── *
   *  One file only: choosing a new file replaces the previous.   *
   *  Canceling the file dialog does not fire "change", so the     *
   *  prior selection and preview stay. (Same behaviour as Inward.)*
   *  Oversized files clear the input and keep the previous UI.   *
   * ─────────────────────────────────────────────────────────── */
  if (imageInput) {
    imageInput.addEventListener('change', function () {
      var file = this.files && this.files[0];

      if (!file) { return; }

      // 5 MB guard — reject and reset input so old preview stays
      if (file.size > 5 * 1024 * 1024) {
        alert('Image must be 5 MB or smaller.');
        // Reset the input so its file list is empty again
        this.value = '';
        return;
      }

      var reader = new FileReader();
      reader.onload = function (e) {
        // Replace: hide placeholder, update img src, show img
        if (imgPlaceholder) { imgPlaceholder.style.display = 'none'; }
        if (imgPreview) {
          imgPreview.src = e.target.result;   // overwrites any previous src
          imgPreview.style.display = 'block';
        }
        if (uploadHint) { uploadHint.textContent = file.name; }
      };
      reader.readAsDataURL(file);
    });
  }

  /* ── 4. UOM conversion preview and auto-conversion ─────────── */
  function getShortName(selectEl) {
    if (!selectEl || selectEl.selectedIndex < 0) return '';
    var opt = selectEl.options[selectEl.selectedIndex];
    if (!opt || !opt.value) return '';
    var txt = opt.text.trim();
    var m = txt.match(/\(([^)]+)\)/);
    return m ? m[1].trim() : txt;
  }

  function getStandardConversion(fromUom, toUom) {
    var f = (fromUom || '').toUpperCase();
    var t = (toUom || '').toUpperCase();
    if (!f || !t) return null;
    if (f === t) return '1.0000';

    if ((f === 'KGS' || f === 'KG' || f.indexOf('KILO') !== -1) && (t === 'GMS' || t === 'GM' || t.indexOf('GRAM') !== -1)) return '1000.0000';
    if ((f === 'GMS' || f === 'GM' || f.indexOf('GRAM') !== -1) && (t === 'MGS' || t === 'MG' || t.indexOf('MILLI') !== -1)) return '1000.0000';
    if ((f === 'KGS' || f === 'KG') && (t === 'MGS' || t === 'MG')) return '1000000.0000';
    if ((f === 'TON' || f === 'TONS') && (t === 'KGS' || t === 'KG')) return '1000.0000';
    if ((f === 'LTR' || f === 'LIT') && (t === 'ML' || t.indexOf('MILLI') !== -1)) return '1000.0000';
    if ((f === 'MTR' || f.indexOf('METER') !== -1) && (t === 'CMS' || t.indexOf('CENTI') !== -1)) return '100.0000';
    if ((f === 'MTR' || f.indexOf('METER') !== -1) && (t === 'MM' || t.indexOf('MILLI') !== -1)) return '1000.0000';

    return null;
  }

  var purchSelect = document.getElementById('uomSelect');
  var issueSelect = document.getElementById('productIssueUomSelect');
  var factorInput = document.getElementById('productConversionFactorInput');
  var previewEl   = document.getElementById('productUomConversionPreview');

  function updatePreview() {
    if (!previewEl || !factorInput) return;
    var pName = getShortName(purchSelect) || 'Purchase UOM';
    var iName = getShortName(issueSelect) || getShortName(purchSelect) || 'Issued UOM';
    var factor = factorInput.value ? parseFloat(factorInput.value) : 1;
    if (isNaN(factor) || factor <= 0) factor = 1;
    previewEl.textContent = '1 ' + pName + ' = ' + factor + ' ' + iName;
  }

  function onUomChange(isPurchChange) {
    if (!purchSelect || !issueSelect || !factorInput) return;
    var pVal = purchSelect.value;
    var iVal = issueSelect.value;

    if (isPurchChange && pVal && !iVal) {
      issueSelect.value = pVal;
    }

    var pName = getShortName(purchSelect);
    var iName = getShortName(issueSelect);
    var stdFactor = getStandardConversion(pName, iName);
    if (stdFactor !== null) {
      factorInput.value = stdFactor;
    } else if (pVal && iVal && pVal === iVal) {
      factorInput.value = '1.0000';
    } else if (!factorInput.value) {
      factorInput.value = '1.0000';
    }
    updatePreview();
  }

  if (purchSelect) { purchSelect.addEventListener('change', function () { onUomChange(true); }); }
  if (issueSelect) { issueSelect.addEventListener('change', function () { onUomChange(false); }); }
  if (factorInput) { factorInput.addEventListener('input', updatePreview); }
  updatePreview();

  /* ── 5. resetForm ───────────────────────────────────────────── */
  window.resetForm = function () {
    var form = document.getElementById('productForm');
    if (typeof clearMasterFormValidationUI === 'function' && form) clearMasterFormValidationUI(form);
    if (form) form.reset();

    setCategoryDisplay('', '');

    // Reset image preview to blank state
    if (imgPreview)     { imgPreview.src = ''; imgPreview.style.display = 'none'; }
    if (imgPlaceholder) { imgPlaceholder.style.display = 'flex'; }
    if (uploadHint)     { uploadHint.textContent = 'JPG, PNG — max 5 MB'; }

    // Re-apply default layer state
    applyLayerState('Single');
    if (factorInput) factorInput.value = '1.0000';
    updatePreview();

    if (prodTypeSelect) { prodTypeSelect.focus(); }
  };
}

window.initPage_product = initPage_product;
initPage_product();