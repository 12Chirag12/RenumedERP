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
  var options = document.getElementById('operatorSectionDdOptions');
  var labelEl = document.getElementById('operatorSectionDdLabel');
  var pageRoot = document.querySelector('.cu-page.operator-page');
  var sectionsLoading = false;

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

  function refreshSections() {
    var selectedIds = getSectionCheckboxes().filter(function (cb) {
      return cb.checked;
    }).map(function (cb) {
      return cb.value;
    });

    return fetch(dd.dataset.sectionsUrl, { credentials: 'same-origin' })
      .then(function (response) {
        if (!response.ok) throw new Error('Unable to load sections.');
        return response.json();
      })
      .then(function (data) {
        if (!options || !Array.isArray(data.sections)) {
          throw new Error('Invalid sections response.');
        }
        options.replaceChildren();
        if (!data.sections.length) {
          var empty = document.createElement('div');
          empty.className = 'operator-section-dd__group';
          empty.textContent = 'No sections available';
          options.appendChild(empty);
          return;
        }

        var currentDepartment = null;
        data.sections.forEach(function (section) {
          if (section.department !== currentDepartment) {
            currentDepartment = section.department;
            var heading = document.createElement('div');
            heading.className = 'operator-section-dd__group';
            heading.textContent = currentDepartment;
            options.appendChild(heading);
          }
          var row = document.createElement('label');
          row.className = 'operator-section-dd__row';
          var checkbox = document.createElement('input');
          checkbox.type = 'checkbox';
          checkbox.name = 'sections';
          checkbox.value = section.id;
          checkbox.checked = selectedIds.indexOf(String(section.id)) !== -1;
          checkbox.addEventListener('change', syncSectionDdLabel);
          var name = document.createElement('span');
          name.textContent = section.name;
          row.appendChild(checkbox);
          row.appendChild(name);
          options.appendChild(row);
        });
      });
  }

  function onDocMouseDown(ev) {
    if (!dd || !panel || panel.hidden) return;
    if (!dd.contains(ev.target)) setPanelOpen(false);
  }

  if (toggle && panel) {
    toggle.addEventListener('click', function (e) {
      e.preventDefault();
      if (!panel.hidden) {
        setPanelOpen(false);
        return;
      }
      if (sectionsLoading) return;
      sectionsLoading = true;
      refreshSections()
        .then(function () {
          syncSectionDdLabel();
          setPanelOpen(true);
        })
        .catch(function (error) {
          if (options) {
            options.textContent = '';
            var message = document.createElement('div');
            message.className = 'operator-section-dd__group';
            message.textContent = 'Unable to load sections. Please try again.';
            options.appendChild(message);
          }
          console.error(error);
          setPanelOpen(true);
        })
        .then(function () {
          sectionsLoading = false;
        });
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
