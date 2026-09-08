/**
 * static/js/masters/uom.js
 * Exposes window.initPage_uom() so base_partial.html can call it after HTMX swap.
 */

function initPage_uom() {
  var nameInput = document.getElementById('uomNameInput');
  var abbrInput = document.getElementById('shortNameInput');

  if (!nameInput) return; // not on this page

  function syncAbbrState() {
    var hasName = nameInput.value.trim().length > 0;
    abbrInput.disabled = !hasName;
    if (!hasName) { abbrInput.value = ''; abbrInput.style.background = ''; }
  }

  nameInput.addEventListener('input', syncAbbrState);
  syncAbbrState();

  abbrInput.addEventListener('input', function () {
    if (this.value.length > 3) this.value = this.value.slice(0, 3);
  });

  window.resetForm = function () {
    var form = document.getElementById('uomForm');
    if (typeof clearMasterFormValidationUI === 'function' && form) clearMasterFormValidationUI(form);
    nameInput.value = '';
    abbrInput.value = '';
    abbrInput.disabled = true;
    nameInput.focus();
  };
}

window.initPage_uom = initPage_uom;
initPage_uom();
