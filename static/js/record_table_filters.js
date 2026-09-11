(function () {
  'use strict';

  var serial = 0;
  var specialBodies = ['baPrevBody', 'lsPendingBody', 'lsGridBody'];

  function normalized(value) {
    return String(value || '').replace(/\s+/g, ' ').trim().toLocaleLowerCase();
  }

  function dateKey(year, month, day) {
    var y = Number(year);
    var m = Number(month);
    var d = Number(day);
    var value = new Date(Date.UTC(y, m - 1, d));
    if (value.getUTCFullYear() !== y || value.getUTCMonth() !== m - 1 || value.getUTCDate() !== d) return null;
    return (y * 10000) + (m * 100) + d;
  }

  function parseDateKey(value) {
    var text = String(value || '').trim();
    var match = text.match(/(?:^|\D)(\d{4})[-\/]([01]?\d)[-\/]([0-3]?\d)(?:\D|$)/);
    if (match) return dateKey(match[1], match[2], match[3]);
    match = text.match(/(?:^|\D)([0-3]?\d)[-\/]([01]?\d)[-\/](\d{4})(?:\D|$)/);
    if (match) return dateKey(match[3], match[2], match[1]);
    match = text.match(/(?:^|\D)(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[-\s](\d{4})(?:\D|$)/i);
    if (match) {
      var months = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
      return dateKey(match[2], months.indexOf(match[1].toUpperCase()) + 1, 1);
    }
    return null;
  }

  function inputDateKey(input) {
    var match = String(input.value || '').match(/^(\d{4})-(\d{2})-(\d{2})$/);
    return match ? dateKey(match[1], match[2], match[3]) : null;
  }

  function isDataRow(row) {
    if (!row || !row.cells || !row.cells.length) return false;
    if (row.cells.length === 1 && row.cells[0].hasAttribute('colspan')) return false;
    return !row.matches('.empty-row, .ls-muted, .dpr-muted, .rm-muted, .ba-muted');
  }

  function tableCandidates(root) {
    var scope = root && root.querySelectorAll ? root : document;
    var tables = Array.prototype.slice.call(
      scope.querySelectorAll('.cu-page[data-page-init] .table-card > .table-scroll-body > table')
    );
    specialBodies.forEach(function (bodyId) {
      var body = scope.querySelector('#' + bodyId);
      var table = body && body.closest('table');
      if (table && tables.indexOf(table) === -1) tables.push(table);
    });
    return tables;
  }

  function toolbarHost(table) {
    var card = table.closest('.table-card');
    if (card) {
      var header = card.querySelector(':scope > .table-card-header');
      if (header) return { node: header, standalone: false };
    }

    var section = table.closest('.txn-section');
    var fields = section && section.querySelector(':scope > .cu-section-fields');
    var tableShell = table.parentElement;
    var host = document.createElement('div');
    host.className = 'record-filter-inline-host';
    if (fields) fields.insertBefore(host, fields.firstChild);
    else if (tableShell && tableShell.parentElement) tableShell.parentElement.insertBefore(host, tableShell);
    else return null;
    return { node: host, standalone: true };
  }

  function columnOptions(table, select) {
    var headers = table.querySelectorAll('thead th');
    var all = document.createElement('option');
    all.value = '-1';
    all.textContent = 'All fields';
    select.appendChild(all);

    Array.prototype.forEach.call(headers, function (header, index) {
      var label = header.textContent.replace(/\s+/g, ' ').trim();
      if (!label || /^(actions?|#)$/i.test(label)) return;
      var option = document.createElement('option');
      option.value = String(index);
      option.textContent = label;
      select.appendChild(option);
    });
  }

  function enhance(table) {
    if (!table || table.dataset.recordFilterReady === 'true') return;
    var tbody = table.tBodies && table.tBodies[0];
    var hostInfo = toolbarHost(table);
    if (!tbody || !hostInfo) return;

    table.dataset.recordFilterReady = 'true';
    serial += 1;
    var inputId = 'recordFilterInput' + serial;
    var toolbar = document.createElement('div');
    toolbar.className = 'record-filter-toolbar' + (hostInfo.standalone ? ' record-filter-toolbar--standalone' : '');
    toolbar.setAttribute('role', 'search');

    var search = document.createElement('div');
    search.className = 'record-filter-search';
    var icon = document.createElement('i');
    icon.className = 'bi bi-search';
    icon.setAttribute('aria-hidden', 'true');
    var input = document.createElement('input');
    input.id = inputId;
    input.type = 'search';
    input.className = 'record-filter-input';
    input.placeholder = hostInfo.standalone ? 'Search…' : 'Search records…';
    input.autocomplete = 'off';
    input.setAttribute('aria-label', 'Search records in this table');
    var clear = document.createElement('button');
    clear.type = 'button';
    clear.className = 'record-filter-clear';
    clear.title = 'Clear search';
    clear.setAttribute('aria-label', 'Clear record search');
    clear.innerHTML = '<i class="bi bi-x-lg" aria-hidden="true"></i>';
    search.appendChild(icon);
    search.appendChild(input);
    search.appendChild(clear);

    var select = document.createElement('select');
    select.className = 'record-filter-column';
    select.setAttribute('aria-label', 'Choose a field to filter');
    columnOptions(table, select);

    var valueSelect = document.createElement('select');
    valueSelect.className = 'record-filter-value';
    valueSelect.setAttribute('aria-label', 'Choose a field value');
    valueSelect.disabled = true;

    var dateRange = document.createElement('div');
    dateRange.className = 'record-filter-date-range';
    dateRange.hidden = true;
    var fromLabel = document.createElement('label');
    fromLabel.textContent = 'From';
    var dateFrom = document.createElement('input');
    dateFrom.type = 'date';
    dateFrom.className = 'record-filter-date';
    dateFrom.setAttribute('aria-label', 'Filter from date');
    fromLabel.appendChild(dateFrom);
    var toLabel = document.createElement('label');
    toLabel.textContent = 'To';
    var dateTo = document.createElement('input');
    dateTo.type = 'date';
    dateTo.className = 'record-filter-date';
    dateTo.setAttribute('aria-label', 'Filter to date');
    toLabel.appendChild(dateTo);
    dateRange.appendChild(fromLabel);
    dateRange.appendChild(toLabel);

    var count = document.createElement('span');
    count.className = 'record-filter-count';
    count.setAttribute('aria-live', 'polite');

    toolbar.appendChild(search);
    toolbar.appendChild(select);
    toolbar.appendChild(valueSelect);
    toolbar.appendChild(dateRange);
    toolbar.appendChild(count);
    hostInfo.node.classList.add('record-filter-host');
    hostInfo.node.appendChild(toolbar);

    function selectedColumnIsDate() {
      var option = select.options[select.selectedIndex];
      var label = normalized(option ? option.textContent : '');
      return Number(select.value) >= 0 && /(^|\s|\/)(date|mfg|exp|expiry|manufacturing)(\s|$|\/)/.test(label);
    }

    function refreshValues(preserveValue) {
      var column = Number(select.value);
      var previous = preserveValue ? valueSelect.value : '';
      valueSelect.replaceChildren();

      var useDateRange = selectedColumnIsDate();
      dateRange.hidden = !useDateRange;
      valueSelect.hidden = useDateRange;

      var all = document.createElement('option');
      all.value = '';
      if (column < 0) {
        all.textContent = 'All values';
        valueSelect.appendChild(all);
        valueSelect.disabled = true;
        return;
      }

      if (useDateRange) {
        valueSelect.disabled = true;
        return;
      }

      var selectedColumn = select.options[select.selectedIndex];
      all.textContent = 'All ' + (selectedColumn ? selectedColumn.textContent.toLocaleLowerCase() : 'values');
      valueSelect.appendChild(all);
      valueSelect.disabled = false;

      var values = [];
      var seen = Object.create(null);
      Array.prototype.filter.call(tbody.rows, isDataRow).forEach(function (row) {
        var label = row.cells[column] ? row.cells[column].textContent.replace(/\s+/g, ' ').trim() : '';
        var key = normalized(label);
        if (!key || seen[key]) return;
        seen[key] = true;
        values.push({ key: key, label: label });
      });
      values.sort(function (a, b) { return a.label.localeCompare(b.label, undefined, { numeric: true }); });
      values.forEach(function (item) {
        var option = document.createElement('option');
        option.value = item.key;
        option.textContent = item.label;
        valueSelect.appendChild(option);
      });
      if (previous && seen[previous]) valueSelect.value = previous;
    }

    function apply() {
      var query = normalized(input.value);
      var column = Number(select.value);
      var selectedValue = normalized(valueSelect.value);
      var fromKey = inputDateKey(dateFrom);
      var toKey = inputDateKey(dateTo);
      var useDateRange = selectedColumnIsDate();
      var rows = Array.prototype.filter.call(tbody.rows, isDataRow);
      var visible = 0;
      rows.forEach(function (row) {
        var fieldText = column >= 0 && row.cells[column] ? normalized(row.cells[column].textContent) : '';
        var haystack = normalized(Array.prototype.map.call(row.cells, function (cell) {
          return cell.matches('.col-actions') ? '' : cell.textContent;
        }).join(' '));
        var matchesSearch = !query || haystack.indexOf(query) !== -1;
        var matchesValue = !selectedValue || fieldText === selectedValue;
        var rowDateKey = useDateRange && (fromKey !== null || toKey !== null) ? parseDateKey(fieldText) : null;
        var matchesFrom = fromKey === null || (rowDateKey !== null && rowDateKey >= fromKey);
        var matchesTo = toKey === null || (rowDateKey !== null && rowDateKey <= toKey);
        var matches = matchesSearch && matchesValue && matchesFrom && matchesTo;
        row.hidden = !matches;
        if (matches) visible += 1;
      });
      var active = Boolean(query || selectedValue || fromKey !== null || toKey !== null);
      count.textContent = active ? (visible + ' of ' + rows.length) : (rows.length + ' records');
      clear.disabled = !active;
      clear.title = active ? 'Clear search and filters' : 'Clear search';
      table.classList.toggle('record-filter-empty', active && visible === 0);
    }

    input.addEventListener('input', apply);
    input.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && input.value) {
        input.value = '';
        apply();
      }
    });
    select.addEventListener('change', function () {
      dateFrom.value = '';
      dateTo.value = '';
      dateFrom.removeAttribute('max');
      dateTo.removeAttribute('min');
      refreshValues(false);
      apply();
    });
    valueSelect.addEventListener('change', apply);
    dateFrom.addEventListener('change', function () {
      dateTo.min = dateFrom.value || '';
      if (dateFrom.value && dateTo.value && dateTo.value < dateFrom.value) dateTo.value = dateFrom.value;
      apply();
    });
    dateTo.addEventListener('change', function () {
      dateFrom.max = dateTo.value || '';
      if (dateFrom.value && dateTo.value && dateFrom.value > dateTo.value) dateFrom.value = dateTo.value;
      apply();
    });
    clear.addEventListener('click', function () {
      input.value = '';
      select.value = '-1';
      dateFrom.value = '';
      dateTo.value = '';
      dateFrom.removeAttribute('max');
      dateTo.removeAttribute('min');
      refreshValues(false);
      apply();
      input.focus();
    });
    new MutationObserver(function () {
      refreshValues(true);
      apply();
    }).observe(tbody, { childList: true });
    refreshValues(false);
    apply();
  }

  function init(root) {
    tableCandidates(root).forEach(enhance);
  }

  window.initRecordTableFilters = init;
  document.addEventListener('DOMContentLoaded', function () { init(document); });
  document.addEventListener('htmx:afterSwap', function (event) {
    init(event.detail && event.detail.target ? event.detail.target : document);
  });
})();
