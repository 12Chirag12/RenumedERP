/**
 * static/js/masters/logistics.js
 * Exposes window.initPage_logistics() so base_partial.html can call it after HTMX swap.
 */

function initPage_logistics() {
  var cards      = document.querySelectorAll('.logistics-selector .attr-card');
  var tableBody  = document.getElementById('logTableBody');
  var tableHead  = document.getElementById('logTableHead');
  var tableTitle = document.getElementById('tableTitle');
  var ltypeInput = document.getElementById('ltypeInput');

  if (!ltypeInput) return; // not on this page

  var HEADS = {
    transporter: '<th>#</th><th>Transporter Name</th><th>Actions</th>',
    state:       '<th>#</th><th>State Name</th><th>GST Code</th><th>Actions</th>',
  };

  function esc(str) {
    return String(str || '')
      .replace(/&/g,'&amp;').replace(/</g,'&lt;')
      .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  cards.forEach(function (card) {
    card.addEventListener('click', function () {
      var type = this.dataset.type;
      if (this.classList.contains('active')) return;
      cards.forEach(function (c) { c.classList.remove('active'); });
      this.classList.add('active');
      ltypeInput.value = type;
      switchFields(type);
      loadTable(type);
      history.replaceState(null, '', '?type=' + type);
      resetInputs();
    });
  });

  function switchFields(type) {
    var rowT = document.getElementById('rowTransporter');
    var rowS = document.getElementById('rowState');
    if (rowT) rowT.style.display = (type === 'transporter') ? '' : 'none';
    if (rowS) rowS.style.display = (type === 'state')       ? '' : 'none';
    updateHeader(type);
  }

  function updateHeader(type) {
    var icon     = document.getElementById('headerIcon');
    var title    = document.getElementById('headerTitle');
    var subtitle = document.getElementById('headerSubtitle');
    var editing  = document.getElementById('editPkField') && document.getElementById('editPkField').value;
    if (type === 'transporter') {
      if (icon)     icon.className = 'bi bi-truck';
      if (title)    title.textContent = (editing ? 'Edit' : 'New') + ' Transporter';
      if (subtitle) subtitle.textContent = 'Enter transporter name';
    } else {
      if (icon)     icon.className = 'bi bi-geo-alt-fill';
      if (title)    title.textContent = (editing ? 'Edit' : 'New') + ' State';
      if (subtitle) subtitle.textContent = 'Enter state name and GST code';
    }
  }

  function loadTable(type) {
    if (!tableBody) return;
    if (tableHead) tableHead.innerHTML = HEADS[type] || '';
    tableBody.innerHTML = '<tr><td colspan="4" class="empty-row">'
      + '<i class="bi bi-arrow-repeat spin-icon"></i> Loading\u2026</td></tr>';
    fetch('/masters/ajax/logistics-records/?type=' + type)
      .then(function (r) { return r.json(); })
      .then(function (data) { renderTable(type, data.records); })
      .catch(function () {
        tableBody.innerHTML = '<tr><td colspan="4" class="empty-row">Failed to load records.</td></tr>';
      });
  }

  function renderTable(type, records) {
    if (tableTitle) tableTitle.textContent = 'All Records (' + records.length + ')';
    if (!records.length) {
      tableBody.innerHTML = '<tr><td colspan="4" class="empty-row">No records found.</td></tr>';
      return;
    }
    var editPk = document.getElementById('editPkField') ? document.getElementById('editPkField').value : '';
    tableBody.innerHTML = records.map(function (r, i) {
      var pk  = r.transport_id || r.state_id;
      var del = '/masters/logistics/' + type + '/' + pk + '/delete/';
      var lbl = type === 'transporter' ? r.transport_name : r.state_name;
      var cls = String(editPk) === String(pk) ? ' class="row-editing"' : '';
      var cells = type === 'transporter'
        ? '<td><strong>' + esc(lbl) + '</strong></td>'
        : '<td><strong>' + esc(r.state_name) + '</strong></td>'
          + '<td><span class="gst-badge">' + esc(r.gst_code) + '</span></td>';
      return '<tr' + cls + '>'
        + '<td class="col-idx">' + (i + 1) + '</td>'
        + cells
        + '<td class="col-actions">'
        + '<a href="?type=' + type + '&edit_pk=' + pk + '"'
        + ' hx-get="?type=' + type + '&edit_pk=' + pk + '"'
        + ' hx-target="#mainContent" hx-swap="innerHTML" hx-push-url="true" hx-indicator="#page-loader"'
        + ' class="btn-action btn-edit" title="Edit"><i class="bi bi-pencil"></i></a>'
        + '<button type="button" class="btn-action btn-delete"'
        + ' data-delete-url="' + del + '" data-delete-name="' + esc(lbl) + '"'
        + ' onclick="openDeleteModal(this.dataset.deleteUrl,this.dataset.deleteName)">'
        + '<i class="bi bi-trash"></i></button>'
        + '</td></tr>';
    }).join('');
    if (window.htmx) htmx.process(tableBody);
  }

  function resetInputs() {
    ['transporterNameInput', 'stateNameInput', 'gstCodeInput'].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.value = '';
    });
  }

  window.resetForm = function () {
    var form = document.getElementById('logForm');
    if (typeof clearMasterFormValidationUI === 'function' && form) clearMasterFormValidationUI(form);
    resetInputs();
  };

  // Load the table for the current type on init
  var currentType = ltypeInput.value || 'transporter';
  loadTable(currentType);
}

window.initPage_logistics = initPage_logistics;
initPage_logistics();