/**
 * static/js/masters/prod_stage.js
 * Exposes window.initPage_prod_stage() so base_partial.html can call it after HTMX swap.
 */

function initPage_prod_stage() {
  var el = document.getElementById('stageNameInput');
  if (!el) return; // not on this page

  window.resetForm = function () {
    var form = document.getElementById('prodStageForm');
    if (typeof clearMasterFormValidationUI === 'function' && form) clearMasterFormValidationUI(form);
    el.value = '';
    el.focus();
  };
}

window.initPage_prod_stage = initPage_prod_stage;
initPage_prod_stage();
