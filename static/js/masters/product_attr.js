/**
 * static/js/masters/product_attr.js
 * Exposes window.initPage_product_attr() so base_partial.html can call it after HTMX swap.
 */

function initPage_product_attr() {
  var cards       = document.querySelectorAll('.product-attr-page .attr-card');
  var tableBody   = document.getElementById('attrTableBody');
  var tableTitle  = document.getElementById('tableTitle');
  var tableHead   = document.getElementById('attrTableHead');
  var editPkField = document.getElementById('editPkField');

  if (!document.querySelector('.product-attr-page')) return; // not on this page

  var CONFIG = {
    colour:   { label: 'Colour Name',   icon: 'bi-palette',  single: true  },
    shape:    { label: 'Shape Name',    icon: 'bi-pentagon', single: true  },
    coating:  { label: 'Coating Type',  icon: 'bi-layers',   single: true  },
    category: { label: 'Category Name', icon: 'bi-tag',      isProdCat: true },
    capsule:  { label: 'Capsule Type',  icon: 'bi-capsule',  isCapsule: true },
  };

  var HEADS = {
    colour:   '<th>#</th><th>Colour Name</th><th>Actions</th>',
    shape:    '<th>#</th><th>Shape Name</th><th>Actions</th>',
    coating:  '<th>#</th><th>Coating Type</th><th>Actions</th>',
    category: '<th>#</th><th>ID</th><th>Category Name</th><th>Actions</th>',
    capsule:  '<th>#</th><th>Capsule Name</th><th>Size</th><th>Colour</th><th>Actions</th>',
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
      document.getElementById('attrTypeInput').value = type;
      updateHeader(type);
      switchFields(type);
      loadTable(type);
      history.replaceState(null, '', '?type=' + type);
      resetInputs();
    });
  });

  function updateHeader(type) {
    var cfg = CONFIG[type];
    if (!cfg) return;
    var iconEl    = document.getElementById('headerIcon');
    var titleEl   = document.getElementById('headerTitle');
    var subtitleEl= document.getElementById('headerSubtitle');
    if (iconEl)     iconEl.className = 'bi ' + cfg.icon;
    if (titleEl)    titleEl.textContent = (editPkField && editPkField.value ? 'Edit' : 'New') + ' ' + cfg.label;
    if (subtitleEl) subtitleEl.textContent = 'Enter ' + cfg.label.toLowerCase() + ' details';
  }

  function switchFields(type) {
    var singleRow   = document.getElementById('rowSingle');
    var categoryRow = document.getElementById('rowCategory');
    var capsuleRow  = document.getElementById('rowCapsule');
    var singleLabel = document.getElementById('singleLabel');
    [singleRow, categoryRow, capsuleRow].forEach(function (el) {
      if (el) el.style.display = 'none';
    });
    var cfg = CONFIG[type];
    if (!cfg) return;
    if (cfg.isCapsule)      { if (capsuleRow)  capsuleRow.style.display  = ''; }
    else if (cfg.isProdCat) { if (categoryRow) categoryRow.style.display = ''; }
    else {
      if (singleRow)  singleRow.style.display  = '';
      if (singleLabel) singleLabel.textContent = cfg.label;
    }
  }

  function loadTable(type) {
    if (!tableBody) return;
    if (tableHead) tableHead.innerHTML = HEADS[type] || '';
    if (tableTitle) tableTitle.textContent = 'All Records';
    tableBody.innerHTML = '<tr><td colspan="5" class="empty-row">'
      + '<i class="bi bi-arrow-repeat spin-icon"></i> Loading\u2026</td></tr>';
    fetch('/masters/ajax/product-attr-records/?type=' + type)
      .then(function (r) { return r.json(); })
      .then(function (data) { renderTable(type, data.records); })
      .catch(function () {
        tableBody.innerHTML = '<tr><td colspan="5" class="empty-row">Failed to load records.</td></tr>';
      });
  }

  function renderTable(type, records) {
    if (!tableBody) return;
    if (tableTitle) tableTitle.textContent = 'All Records (' + records.length + ')';
    if (!records.length) {
      tableBody.innerHTML = '<tr><td colspan="5" class="empty-row">No records found. Use the form above to add one.</td></tr>';
      return;
    }
    var editPk = editPkField ? editPkField.value : '';
    tableBody.innerHTML = records.map(function (r, i) {
      var pk         = r.color_id || r.shape_id || r.coating_id || r.prod_cat_id || r.capsule_id;
      var deleteUrl  = '/masters/product-attributes/' + type + '/' + pk + '/delete/';
      var editUrl    = '?type=' + type + '&edit_pk=' + pk;
      var cells = '';
      if (type === 'colour')        cells = '<td><strong>' + esc(r.color_name)   + '</strong></td>';
      else if (type === 'shape')    cells = '<td><strong>' + esc(r.shape_name)   + '</strong></td>';
      else if (type === 'coating')  cells = '<td><strong>' + esc(r.coating_name) + '</strong></td>';
      else if (type === 'category') cells = '<td><span class="attr-badge">' + esc(r.prod_cat_id) + '</span></td><td><strong>' + esc(r.prod_cat_name) + '</strong></td>';
      else if (type === 'capsule')  cells = '<td><strong>' + esc(r.capsule_name) + '</strong></td><td>' + esc(r.capsule_size) + '</td><td>' + esc(r.capsule_color) + '</td>';
      var editingClass = (editPkField && String(editPkField.value) === String(pk)) ? ' class="row-editing"' : '';
      return '<tr' + editingClass + '>'
        + '<td class="col-idx">' + (i + 1) + '</td>'
        + cells
        + '<td class="col-actions">'
        + '<a href="' + editUrl + '"'
        + ' hx-get="' + editUrl + '"'
        + ' hx-target="#mainContent" hx-swap="innerHTML" hx-push-url="true" hx-indicator="#page-loader"'
        + ' class="btn-action btn-edit" title="Edit"><i class="bi bi-pencil"></i></a>'
        + '<button type="button" class="btn-action btn-delete" title="Delete"'
        + ' data-delete-url="' + deleteUrl + '"'
        + ' data-delete-name="' + esc(r.color_name || r.shape_name || r.coating_name || r.prod_cat_name || r.capsule_name || '') + '"'
        + ' onclick="openDeleteModal(this.dataset.deleteUrl, this.dataset.deleteName)">'
        + '<i class="bi bi-trash"></i></button>'
        + '</td></tr>';
    }).join('');
    if (window.htmx) htmx.process(tableBody);
  }

  // Capsule preview
  var capsuleSizeInput  = document.getElementById('capsuleSizeInput');
  var capsuleColorInput = document.getElementById('capsuleColorInput');
  var capsulePreview    = document.getElementById('capsulePreview');

  function updateCapsulePreview() {
    if (!capsulePreview) return;
    var size  = capsuleSizeInput  ? capsuleSizeInput.value.trim()  : '';
    var color = capsuleColorInput ? capsuleColorInput.value.trim() : '';
    if (size || color) {
      capsulePreview.classList.add('show');
      capsulePreview.innerHTML = 'Auto-generated name: <strong>' + esc(size) + (size && color ? ' ' : '') + esc(color) + '</strong>';
    } else {
      capsulePreview.classList.remove('show');
    }
  }

  if (capsuleSizeInput)  capsuleSizeInput.addEventListener('input',  updateCapsulePreview);
  if (capsuleColorInput) capsuleColorInput.addEventListener('input', updateCapsulePreview);
  updateCapsulePreview();

  function resetInputs() {
    ['attrNameInput','prodCatIdInput','prodCatNameInput','capsuleSizeInput','capsuleColorInput'].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.value = '';
    });
    if (capsulePreview) capsulePreview.classList.remove('show');
  }

  window.resetForm = function () {
    var form = document.getElementById('attrForm');
    if (typeof clearMasterFormValidationUI === 'function' && form) clearMasterFormValidationUI(form);
    resetInputs();
    var firstInput = document.querySelector('.cu-section-fields input');
    if (firstInput) firstInput.focus();
  };

  // Load the table for the current type on init
  var attrTypeInput = document.getElementById('attrTypeInput');
  var currentType = (attrTypeInput && attrTypeInput.value) ? attrTypeInput.value : 'colour';
  loadTable(currentType);
}

window.initPage_product_attr = initPage_product_attr;
initPage_product_attr();
