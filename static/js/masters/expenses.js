/**
 * static/js/masters/expenses.js
 * Exposes window.initPage_expenses() so base_partial.html calls it after HTMX swap.
 */

function initPage_expenses() {
  var nameEl = document.getElementById('expNameInput');
  var expGroupEl  = document.getElementById('expGroupSelect');
 

  if (!nameEl) return; // not on this page

  window.resetForm = function () {
    var form = document.getElementById('expensesForm');
    if (typeof clearMasterFormValidationUI === 'function' && form) clearMasterFormValidationUI(form);
    nameEl.value = '';
    if (expGroupEl) expGroupEl.selectedIndex = 0;
    nameEl.focus();
  };
}

window.initPage_expenses = initPage_expenses;
initPage_expenses();