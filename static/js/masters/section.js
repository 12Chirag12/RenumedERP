/**
 * static/js/masters/section.js
 * Exposes window.initPage_section() so base_partial.html can call it after HTMX swap.
 */

function initPage_section() {
  var deptDropdown = document.getElementById('deptDropdown');
  var sectionInput = document.getElementById('sectionNameInput');

  if (!deptDropdown) return; // not on this page

  window.resetForm = function () {
    var form = document.getElementById('sectionForm');
    if (typeof clearMasterFormValidationUI === 'function' && form) clearMasterFormValidationUI(form);
    deptDropdown.selectedIndex = 0;
    sectionInput.value = '';
    sectionInput.focus();
  };
}

window.initPage_section = initPage_section;
initPage_section();
