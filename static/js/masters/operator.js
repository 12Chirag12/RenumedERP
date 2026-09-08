/**
 * static/js/masters/operator.js
 * Exposes window.initPage_operator() for HTMX swaps via base_partial.html.
 * Sections: single dropdown button + checkbox panel (sync label to selection).
 */

function initPage_operator() {
  var nameInput = document.getElementById('operatorNameInput');
  if (!nameInput) return;

  var dd = document.getElementById('operatorSectionDd');
  var toggle = document.getElementById('operatorSectionDdToggle');
  var panel = document.getElementById('operatorSectionDdPanel');
  var labelEl = document.getElementById('operatorSectionDdLabel');
  var pageRoot = document.querySelector('.cu-page.operator-page');

  function getSectionCheckboxes() {
    if (!dd) return [];
    return Array.prototype.slice.call(dd.querySelectorAll('input[type="checkbox"][name="sections"]'));
  }

  function selectedSectionLabels() {
    var out = [];
    getSectionCheckboxes().forEach(function (cb) {
      if (!cb.checked) return;
      var row = cb.closest('.operator-section-dd__row');
      var span = row ? row.querySelector('span') : null;
      out.push(span && span.textContent ? span.textContent.trim() : cb.value);
    });
    return out;
  }

  function syncSectionDdLabel() {
    if (!labelEl) return;
    var labels = selectedSectionLabels();
    if (!labels.length) {
      labelEl.textContent = '— Select sections —';
      return;
    }
    if (labels.length <= 2) {
      labelEl.textContent = labels.join(', ');
      return;
    }
    labelEl.textContent = labels.slice(0, 2).join(', ') + ' +' + (labels.length - 2) + ' more';
  }

  function setPanelOpen(open) {
    if (!panel || !toggle) return;
    panel.hidden = !open;
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (pageRoot) {
      if (open) pageRoot.classList.add('operator-form--dd-open');
      else pageRoot.classList.remove('operator-form--dd-open');
    }
  }

  function onDocMouseDown(ev) {
    if (!dd || !panel || panel.hidden) return;
    if (!dd.contains(ev.target)) setPanelOpen(false);
  }

  if (toggle && panel) {
    toggle.addEventListener('click', function (e) {
      e.preventDefault();
      setPanelOpen(panel.hidden);
    });
    getSectionCheckboxes().forEach(function (cb) {
      cb.addEventListener('change', syncSectionDdLabel);
    });
    if (window.__operatorSectionDdMdown) {
      document.removeEventListener('mousedown', window.__operatorSectionDdMdown);
    }
    window.__operatorSectionDdMdown = onDocMouseDown;
    document.addEventListener('mousedown', window.__operatorSectionDdMdown);
    syncSectionDdLabel();
  }

  window.resetForm = function () {
    var form = document.getElementById('operatorForm');
    if (typeof clearMasterFormValidationUI === 'function' && form) clearMasterFormValidationUI(form);
    if (nameInput) nameInput.value = '';
    var des = document.getElementById('operatorDesignationInput');
    if (des) des.value = '';
    getSectionCheckboxes().forEach(function (cb) {
      cb.checked = false;
    });
    syncSectionDdLabel();
    setPanelOpen(false);
    if (nameInput) nameInput.focus();
  };
}

window.initPage_operator = initPage_operator;
initPage_operator();
