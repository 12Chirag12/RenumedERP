/**
 * static/js/masters/item_type.js
 * Exposes window.initPage_item_type() so base_partial.html can call it after HTMX swap.
 */

function initPage_item_type() {
  var nameEl = document.getElementById('itemTypeNameInput');
  var catEl  = document.getElementById('itemCategorySelect');

  if (!nameEl) return; // not on this page

  window.resetForm = function () {
    var form = document.getElementById('itemTypeForm');
    if (typeof clearMasterFormValidationUI === 'function' && form) clearMasterFormValidationUI(form);
    if (catEl)  catEl.selectedIndex = 0;
    nameEl.value = '';
    nameEl.focus();
  };
}

window.initPage_item_type = initPage_item_type;
initPage_item_type();
