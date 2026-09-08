/**
 * static/js/masters/machine.js
 * Exposes window.initPage_machine() so base_partial.html can call it after HTMX swap.
 */

function initPage_machine() {
  var sectionDropdown    = document.getElementById('sectionDropdown');
  var deptDisplay        = document.getElementById('deptDisplay');
  var machineNameInput   = document.getElementById('machineNameInput');
  var installedDateInput = document.getElementById('installedDateInput');

  if (!machineNameInput) return; // not on this page

  if (installedDateInput) {
    var today = new Date().toISOString().split('T')[0];
    installedDateInput.setAttribute('max', today);
  }

  if (sectionDropdown && deptDisplay) {
    sectionDropdown.addEventListener('change', function () {
      var sectionId = this.value;
      if (!sectionId) { deptDisplay.value = ''; return; }
      fetch('/masters/ajax/section-dept/?section_id=' + sectionId)
        .then(function (r) { return r.json(); })
        .then(function (data) { deptDisplay.value = data.dept_name || ''; })
        .catch(function () { deptDisplay.value = ''; });
    });
    if (sectionDropdown.value) {
      sectionDropdown.dispatchEvent(new Event('change'));
    }
  }

  window.resetForm = function () {
    var form = document.getElementById('machineForm');
    if (typeof clearMasterFormValidationUI === 'function' && form) clearMasterFormValidationUI(form);
    if (sectionDropdown)  { sectionDropdown.selectedIndex = 0; }
    if (deptDisplay)      { deptDisplay.value = ''; }
    if (machineNameInput) { machineNameInput.value = ''; }
    ['makeInput','modelNoInput','machineNoInput','capacityInput','installedDateInput','remarksInput']
      .forEach(function (id) { var el = document.getElementById(id); if (el) el.value = ''; });
    if (sectionDropdown) sectionDropdown.focus();
  };
}

window.initPage_machine = initPage_machine;
initPage_machine();
