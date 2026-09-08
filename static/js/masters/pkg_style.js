/**
 * static/js/masters/pkg_style.js
 * Exposes window.initPage_pkg_style() so base_partial.html calls it after HTMX swap.
 */

function initPage_pkg_style() {
  var nameEl      = document.getElementById('pkgStyleNameInput');
  var valueEl     = document.getElementById('pkgStyleValueInput');
  var itemTypeEl  = document.getElementById('pkgItemTypeSelect');

  if (!nameEl) return; // not on this page

  function filterPkgStyleName(s) {
    return String(s || '').replace(/[^0-9xX]/g, '').toUpperCase();
  }

  function applyNameFilter() {
    var p = nameEl.selectionStart;
    var v = filterPkgStyleName(nameEl.value);
    if (nameEl.value !== v) {
      nameEl.value = v;
      if (p !== null) {
        var c = Math.min(p, v.length);
        nameEl.setSelectionRange(c, c);
      }
    }
  }

  /* Block disallowed keys before they appear (digits and X only). */
  nameEl.addEventListener('keydown', function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === 'Dead' || e.isComposing) return;
    if (e.key.length !== 1) return; // Tab, Backspace, arrows, etc.
    if (/[0-9xX]/.test(e.key)) return;
    e.preventDefault();
  });

  nameEl.addEventListener('beforeinput', function (e) {
    if (e.inputType === 'insertCompositionText' || e.isComposing) return;
    if (e.inputType && e.inputType.indexOf('insert') === 0 && e.data && e.data.length && !/^[0-9xX]*$/.test(e.data)) {
      e.preventDefault();
    }
  });

  nameEl.addEventListener('paste', function (e) {
    e.preventDefault();
    var raw = (e.clipboardData || window.clipboardData).getData('text') || '';
    var ins = filterPkgStyleName(raw);
    if (!ins) return;
    var start = nameEl.selectionStart;
    var end = nameEl.selectionEnd;
    var v = nameEl.value;
    nameEl.value = v.slice(0, start) + ins + v.slice(end);
    applyNameFilter();
    var pos = start + ins.length;
    nameEl.setSelectionRange(pos, pos);
  });

  /* Fallback: any remaining bad chars (drag-drop, autofill, etc.) */
  nameEl.addEventListener('input', applyNameFilter);

  window.resetForm = function () {
    var form = document.getElementById('pkgStyleForm');
    if (typeof clearMasterFormValidationUI === 'function' && form) clearMasterFormValidationUI(form);
    nameEl.value  = '';
    if (valueEl)    valueEl.value = '';
    if (itemTypeEl) itemTypeEl.selectedIndex = 0;
    nameEl.focus();
  };
}

window.initPage_pkg_style = initPage_pkg_style;
initPage_pkg_style();