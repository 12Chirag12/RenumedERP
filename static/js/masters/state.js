/**
 * static/js/masters/state.js
 * Exposes window.initPage_state() so base_partial.html can call it after HTMX swap.
 */

function initPage_state() {
  var nameInput = document.getElementById('stateNameInput');
  var gstInput  = document.getElementById('gstCodeInput');

  if (!nameInput) return; // not on this page

  window.resetForm = function () {
    var form = document.getElementById('logForm');
    if (typeof clearMasterFormValidationUI === 'function' && form) clearMasterFormValidationUI(form);
    nameInput.value = '';
    gstInput.value  = '';
    nameInput.focus();
  };
}

window.initPage_state = initPage_state;
initPage_state();
