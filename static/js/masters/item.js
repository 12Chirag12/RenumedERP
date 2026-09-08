/**
 * static/js/masters/item.js
 * Exposes window.initPage_item() so base_partial.html calls it after HTMX swap.
 *
 * Behaviour:
 *   1. Item Type change → AJAX → auto-fill Item Category display + hidden ID.
 *      Reuses the same endpoint as product.js:
 *        /masters/ajax/item-type-category/?item_type_id=N
 *
 *   2. Y/N cascade:
 *      maintain_batch = N → mfg_date locked to N, exp_date locked to N
 *      maintain_batch = Y, mfg_date = N → exp_date locked to N
 *      maintain_batch = Y, mfg_date = Y → exp_date freely selectable
 *
 *   3. resetForm() — clears all fields, resets cascade state.
 */

function initPage_item() {

  var itemTypeSelect   = document.getElementById('itemTypeSelect');
  var catDisplay       = document.getElementById('itemCategoryDisplay');
  var catHidden        = document.getElementById('itemCategoryIdHidden');
  var mfgDateField     = document.getElementById('mfgDateField');
  var expDateField     = document.getElementById('expDateField');

  if (!itemTypeSelect) return; // not on this page

  /* ── 1. Item Type → Category auto-fill (AJAX) ────────────── */
  itemTypeSelect.addEventListener('change', function () {
    var itemTypeId = this.value;
    if (!itemTypeId) { setCategoryDisplay('', ''); return; }

    fetch('/masters/ajax/item-type-category/?item_type_id=' + itemTypeId)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        setCategoryDisplay(
          data.prod_cat_id ? data.prod_cat_name : '',
          data.prod_cat_id || ''
        );
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

  /* ── 2. Y/N cascade logic ──────────────────────────────────── */

  function getCheckedValue(name) {
    var el = document.querySelector('input[name="' + name + '"]:checked');
    return el ? el.value : 'N';
  }

  function forceRadio(name, value) {
    /* Set the radio group to a given value without firing change events. */
    var radios = document.querySelectorAll('input[name="' + name + '"]');
    radios.forEach(function (r) { r.checked = (r.value === value); });
  }

  function setFieldDisabled(fieldEl, disabled) {
    if (!fieldEl) return;
    if (disabled) {
      fieldEl.classList.add('yn-disabled');
    } else {
      fieldEl.classList.remove('yn-disabled');
    }
  }

  function applyCascade() {
    var batch = getCheckedValue('maintain_batch');
    var mfg   = getCheckedValue('mfg_date');

    if (batch === 'N') {
      /* Lock both downstream fields to N */
      forceRadio('mfg_date', 'N');
      forceRadio('exp_date', 'N');
      setFieldDisabled(mfgDateField, true);
      setFieldDisabled(expDateField, true);
    } else {
      /* maintain_batch = Y → unlock mfg_date */
      setFieldDisabled(mfgDateField, false);

      if (mfg === 'N') {
        /* mfg_date = N → lock exp_date to N */
        forceRadio('exp_date', 'N');
        setFieldDisabled(expDateField, true);
      } else {
        /* mfg_date = Y → unlock exp_date */
        setFieldDisabled(expDateField, false);
      }
    }
  }

  /* Attach listeners to all three radio groups */
  ['maintain_batch', 'mfg_date', 'exp_date'].forEach(function (name) {
    document.querySelectorAll('input[name="' + name + '"]').forEach(function (r) {
      r.addEventListener('change', applyCascade);
    });
  });

  /* Apply on init (handles edit pre-fill and fresh defaults) */
  applyCascade();

  /* ── 3. resetForm ───────────────────────────────────────────── */
  window.resetForm = function () {
    var form = document.getElementById('itemForm');
    if (typeof clearMasterFormValidationUI === 'function' && form) clearMasterFormValidationUI(form);
    if (form) form.reset();

    setCategoryDisplay('', '');

    /* Restore defaults: maintain_batch=N, mfg_date=N, exp_date=N */
    forceRadio('maintain_batch', 'N');
    forceRadio('mfg_date', 'N');
    forceRadio('exp_date', 'N');
    applyCascade();

    if (itemTypeSelect) { itemTypeSelect.focus(); }
  };
}

window.initPage_item = initPage_item;
initPage_item();