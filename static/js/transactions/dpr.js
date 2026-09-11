/**
 * Daily production report (DPR) — section → machines, customer (SO products),
 * single batch dropdown (log sheet row), specs, status panel, grid,
 * machine-not-working toggles.
 */
(function () {
  'use strict';

  function readJsonScript(id) {
    var el = document.getElementById(id);
    if (!el || !el.textContent) return null;
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return null;
    }
  }

  function esc(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function parseTimeToMin(el) {
    if (!el || !el.value) return null;
    var p = el.value.split(':');
    if (p.length < 2) return null;
    var h = parseInt(p[0], 10);
    var m = parseInt(p[1], 10);
    if (!isFinite(h) || !isFinite(m)) return null;
    return h * 60 + m;
  }

  function updateTotalTimeDisplay(startEl, endEl, outEl) {
    if (!outEl) return;
    var s = parseTimeToMin(startEl);
    var e = parseTimeToMin(endEl);
    if (s == null || e == null) {
      outEl.value = '';
      return;
    }
    var e2 = e <= s ? e + 24 * 60 : e;
    var mins = e2 - s;
    var h = Math.floor(mins / 60);
    var mm = mins % 60;
    outEl.value = (h < 10 ? '0' + h : h) + ':' + (mm < 10 ? '0' + mm : mm) + ' Hrs.';
  }

  window.initPage_dpr = function initPage_dpr() {
    var form = document.getElementById('dprForm');
    if (!form) return;

    var urls = readJsonScript('dprAjaxUrls') || {};
    var gridDef = readJsonScript('dprGridDefaults') || {};
    var editPayload = readJsonScript('dprEditPayload') || {};

    var section = document.getElementById('dprSection');
    var machine = document.getElementById('dprMachine');
    var operators = document.getElementById('dprOperators');
    var operatorCount = document.getElementById('dprOperatorCount');
    var operatorToggle = document.getElementById('dprOperatorToggle');
    var operatorSelection = document.getElementById('dprOperatorSelection');
    var machineWorking = document.getElementById('dprMachineWorking');
    var customer = document.getElementById('dprCustomer');
    var product = document.getElementById('dprProduct');
    var batchSelect = document.getElementById('dprBatchSelect');
    var batchDtl = document.getElementById('dprBatchDtlId');
    var logSheetId = document.getElementById('dprLogSheetId');
    var specSelect = document.getElementById('dprSpecSelect');
    var specId = document.getElementById('dprSpecId');
    var ordDisp = document.getElementById('dprOrdDisplay');
    var mfgDisp = document.getElementById('dprMfgDisplay');
    var expDisp = document.getElementById('dprExpDisplay');
    var batchSizeDisp = document.getElementById('dprBatchSizeDisplay');
    var layerDisp = document.getElementById('dprTabletLayer');
    var colourDisp = document.getElementById('dprLayerColour');
    var statusBody = document.getElementById('dprStatusBody');
    var gridBody = document.getElementById('dprGridBody');
    var gridErr = document.getElementById('dprGridErr');
    var gridStart = document.getElementById('dprGridStart');
    var gridEnd = document.getElementById('dprGridEnd');
    var startTime = document.getElementById('dprStartTime');
    var endTime = document.getElementById('dprEndTime');
    var totalTime = document.getElementById('dprTotalTime');

    var batchSingleWrap = document.getElementById('dprBatchSingleWrap');
    var batchMultiWrap = document.getElementById('dprBatchMultiWrap');
    var batchDetailStrip = document.getElementById('dprBatchDetailStrip'); /* display:contents; children are grid cells */
    var layerStrip = document.getElementById('dprLayerDetailStrip');
    var ordWrap = document.getElementById('dprOrdFieldWrap');
    var batchDisplay = document.getElementById('dprBatchDisplay');
    var batchAddSelect = document.getElementById('dprBatchAddSelect');
    var logSheetIdsJson = document.getElementById('dprLogSheetIdsJson');
    var multiSectionIds = readJsonScript('dprMultiSectionIds') || [];

    var multiLogCatalog = [];
    var multiSelected = [];
    /** Last JSON rows from dpr_operators_ajax; used to rebuild operators for the selected section. */
    var lastOperatorRows = [];

    var workingFieldIds = [
      'dprCustomer', 'dprProduct', 'dprBatchSelect', 'dprBatchAddSelect', 'dprSpecSelect',
      'dprBatchRem', 'dprLotNo', 'dprQtyKg', 'dprQtyNos', 'dprSectionQty', 'dprBatchSizeLakh',
      'dprOperatorToggle', 'dprOperators', 'dprHelpers',
    ];

    if (gridStart && gridDef.start) gridStart.value = gridDef.start;
    if (gridEnd && gridDef.end) gridEnd.value = gridDef.end;

    if (typeof initSearchableDropdowns === 'function') {
      initSearchableDropdowns(form);
    }

    function clearBatchDisplays() {
      if (ordDisp) ordDisp.value = '';
      if (mfgDisp) mfgDisp.value = '';
      if (expDisp) expDisp.value = '';
      if (batchSizeDisp) batchSizeDisp.value = '';
      if (layerDisp) layerDisp.value = '';
      if (colourDisp) colourDisp.value = '';
      if (batchDtl) batchDtl.value = '';
      if (logSheetId) logSheetId.value = '';
      if (logSheetIdsJson) logSheetIdsJson.value = '[]';
      multiSelected = [];
      multiLogCatalog = [];
      if (batchDisplay) batchDisplay.value = '';
      if (batchAddSelect) {
        batchAddSelect.innerHTML = '<option value="">Choose batch / colour slot to add…</option>';
      }
      if (statusBody) {
        statusBody.innerHTML =
          '<tr><td colspan="2" class="dpr-muted">Select a batch to load totals…</td></tr>';
      }
    }

    function isMultiSection() {
      if (!section || !section.value) return false;
      var sid = parseInt(section.value, 10);
      if (!isFinite(sid)) return false;
      return multiSectionIds.indexOf(sid) !== -1;
    }

    function toggleBatchLanes() {
      var m = isMultiSection();
      var metaRow = document.querySelector('.dpr-row-batch-meta');
      if (metaRow) metaRow.classList.toggle('dpr-row-batch-meta--multi', !!m);
      if (batchSingleWrap) batchSingleWrap.style.display = m ? 'none' : '';
      if (batchMultiWrap) batchMultiWrap.style.display = m ? '' : 'none';
      if (batchDetailStrip) {
        Array.prototype.forEach.call(batchDetailStrip.children, function (cell) {
          cell.style.display = m ? 'none' : '';
        });
      }
      if (layerStrip) layerStrip.style.display = m ? 'none' : '';
      if (ordWrap) ordWrap.style.display = m ? 'none' : '';
      var sqTxt = document.getElementById('dprSectionQtyLabelText');
      if (sqTxt) {
        sqTxt.textContent = 'Section qty (optional)';
      }
    }

    function formatLogsheetOptionLabel(ls) {
      if (!ls) return '';
      var bn = ls.batch_no || '—';
      var slot = (ls.slot_label || '').trim();
      return slot && slot !== 'Single' ? bn + ' — ' + slot : bn;
    }

    function selectedIdsSet() {
      var s = {};
      multiSelected.forEach(function (x) {
        s[x.id] = true;
      });
      return s;
    }

    function rebuildAddBatchDropdown() {
      if (!batchAddSelect) return;
      var sel = selectedIdsSet();
      var keep = batchAddSelect.value;
      batchAddSelect.innerHTML = '';
      var ph = document.createElement('option');
      ph.value = '';
      ph.textContent = 'Choose batch / colour slot to add…';
      batchAddSelect.appendChild(ph);
      multiLogCatalog.forEach(function (ls) {
        var lid = parseInt(ls.logsheet_id, 10);
        if (!isFinite(lid) || sel[lid]) return;
        var o = document.createElement('option');
        o.value = String(lid);
        o.textContent = formatLogsheetOptionLabel(ls);
        batchAddSelect.appendChild(o);
      });
      if (keep && [].some.call(batchAddSelect.options, function (opt) { return opt.value === keep; })) {
        batchAddSelect.value = keep;
      } else {
        batchAddSelect.value = '';
      }
    }

    function syncLogSheetIdsHidden() {
      if (!isMultiSection() || !logSheetIdsJson) return;
      logSheetIdsJson.value = JSON.stringify(multiSelected.map(function (x) {
        return x.id;
      }));
    }

    function updateMultiBatchUi() {
      if (batchDisplay) {
        batchDisplay.value = multiSelected.length
          ? multiSelected.map(function (x) {
            return x.name;
          }).join(' / ')
          : '';
      }
      syncLogSheetIdsHidden();
      rebuildAddBatchDropdown();
    }

    function applyMultiCatalogFromLogSheets(rows, preserveSelection) {
      multiLogCatalog = rows || [];
      if (!preserveSelection) {
        multiSelected = [];
        if (batchDisplay) batchDisplay.value = '';
        if (logSheetIdsJson) logSheetIdsJson.value = '[]';
      } else {
        var byLid = {};
        multiLogCatalog.forEach(function (ls) {
          var lid = parseInt(ls.logsheet_id, 10);
          if (isFinite(lid)) byLid[lid] = formatLogsheetOptionLabel(ls);
        });
        multiSelected = multiSelected
          .map(function (x) {
            var nm = byLid[x.id];
            return nm ? { id: x.id, name: nm } : null;
          })
          .filter(Boolean);
      }
      updateMultiBatchUi();
    }

    function setFieldsDisabled(ids, dis) {
      ids.forEach(function (id) {
        var el = document.getElementById(id);
        if (!el) return;
        el.disabled = !!dis;
        if (el.id === 'dprOperators') {
          [].forEach.call(el.querySelectorAll('input[name="operators"]'), function (input) {
            input.disabled = !!dis;
          });
        }
        if (el.tagName === 'SELECT' && dis) {
          try {
            if (window.jQuery && jQuery(el).data('select2')) {
              jQuery(el).prop('disabled', true);
            }
          } catch (e) { /* ignore */ }
        } else if (el.tagName === 'SELECT' && !dis) {
          try {
            if (window.jQuery && jQuery(el).data('select2')) {
              jQuery(el).prop('disabled', false);
            }
          } catch (e2) { /* ignore */ }
        }
      });
    }

    function applyMachineWorkingUi() {
      var w = machineWorking && machineWorking.value === 'working';
      setFieldsDisabled(workingFieldIds, !w);
      if (batchSelect) batchSelect.disabled = !w;
      if (batchAddSelect) batchAddSelect.disabled = !w;
      if (batchDisplay) batchDisplay.disabled = !w;
      var bsl = document.getElementById('dprBatchSizeLakh');
      if (bsl) bsl.disabled = !w;
      if (specSelect) specSelect.disabled = !w;
    }

    function rebuildMachineOptions(rows, keepValue) {
      if (!machine) return;
      var v = keepValue != null ? String(keepValue) : machine.value;
      machine.innerHTML = '<option value="">— Select machine —</option>';
      (rows || []).forEach(function (r) {
        var o = document.createElement('option');
        o.value = String(r.machine_id);
        o.textContent = r.machine_name;
        machine.appendChild(o);
      });
      if (v && [].some.call(machine.options, function (o) { return o.value === v; })) {
        machine.value = v;
      } else {
        machine.value = '';
      }
      if (typeof initSearchableDropdowns === 'function') {
        initSearchableDropdowns(form);
      }
    }

    function rebuildOperatorOptions(rows, keepValues, clearSelections) {
      rows = rows || [];
      var selected = clearSelections ? [] : (keepValues || []).map(function (x) { return String(x); });
      if (!selected.length && operators) {
        selected = [].map.call(operators.querySelectorAll('input[name="operators"]:checked'), function (input) {
          return String(input.value);
        });
      }
      if (!operators) return;
      operators.innerHTML = '';
      if (!rows.length) {
        var empty = document.createElement('div');
        empty.className = 'dpr-operator-empty';
        empty.textContent = section && section.value ? 'No operators are assigned to this section.' : 'Select a section to load operators.';
        operators.appendChild(empty);
      }
      rows.forEach(function (r) {
        var label = document.createElement('label');
        label.className = 'dpr-operator-checkbox';
        var input = document.createElement('input');
        input.type = 'checkbox';
        input.name = 'operators';
        input.value = String(r.opt_id);
        input.checked = selected.indexOf(input.value) !== -1;
        var text = document.createElement('span');
        text.textContent = r.label || r.opt_name;
        label.appendChild(input);
        label.appendChild(text);
        operators.appendChild(label);
      });
      if (machineWorking && machineWorking.value !== 'working') {
        [].forEach.call(operators.querySelectorAll('input[name="operators"]'), function (input) {
          input.disabled = true;
        });
      }
      updateOperatorCount();
    }

    function updateOperatorCount() {
      if (!operatorCount || !operators) return;
      var count = operators.querySelectorAll('input[name="operators"]:checked').length;
      operatorCount.textContent = count + ' selected';
      if (operatorSelection) {
        operatorSelection.textContent = count ? count + ' operator' + (count === 1 ? '' : 's') + ' selected' : 'Choose operators';
      }
    }

    function closeOperatorMenu() {
      if (!operatorToggle || !operatorToggle.parentElement) return;
      operatorToggle.parentElement.classList.remove('is-open');
      operatorToggle.setAttribute('aria-expanded', 'false');
    }

    if (operatorToggle) {
      operatorToggle.addEventListener('click', function () {
        if (operatorToggle.disabled) return;
        var dropdown = operatorToggle.parentElement;
        var open = dropdown.classList.toggle('is-open');
        operatorToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
      document.addEventListener('click', function (event) {
        if (!operatorToggle.parentElement.contains(event.target)) closeOperatorMenu();
      });
    }

    function syncOperatorDropdownsFromCache() {
      if (lastOperatorRows.length) {
        rebuildOperatorOptions(lastOperatorRows, null, false);
      }
    }

    function loadOperators(keepValues, clearSelections) {
      if (!urls.operators || !section || !section.value) {
        lastOperatorRows = [];
        rebuildOperatorOptions([], [], true);
        return Promise.resolve();
      }
      return fetch(urls.operators + '?section_id=' + encodeURIComponent(section.value))
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.error) {
            lastOperatorRows = [];
            rebuildOperatorOptions([], [], !!clearSelections);
            return;
          }
          lastOperatorRows = data.operators || [];
          rebuildOperatorOptions(lastOperatorRows, keepValues, !!clearSelections);
        })
        .catch(function () {
          lastOperatorRows = [];
          rebuildOperatorOptions([], [], true);
        });
    }

    function loadMachines(keepValue) {
      if (!urls.machines || !section || !section.value) {
        rebuildMachineOptions([], null);
        return Promise.resolve();
      }
      return fetch(urls.machines + '?section_id=' + encodeURIComponent(section.value))
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.error) {
            rebuildMachineOptions([], null);
            return;
          }
          rebuildMachineOptions(data.machines || [], keepValue);
        })
        .catch(function () {
          rebuildMachineOptions([], null);
        });
    }

    function loadCustomerProducts() {
      if (!urls.customerProducts || !customer || !customer.value) {
        if (product) {
          product.innerHTML = '<option value="">— Select product —</option>';
          product.value = '';
        }
        return Promise.resolve();
      }
      return fetch(urls.customerProducts + '?cust_id=' + encodeURIComponent(customer.value))
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!product) return;
          product.innerHTML = '<option value="">— Select product —</option>';
          (data.products || []).forEach(function (p) {
            var o = document.createElement('option');
            o.value = String(p.prod_id);
            o.textContent = p.prod_name;
            product.appendChild(o);
          });
          product.value = '';
          if (typeof initSearchableDropdowns === 'function') {
            initSearchableDropdowns(form);
          }
        });
    }

    function loadBatches(preserveMultiSelection) {
      if (!urls.logsheets) return Promise.resolve();
      if (!customer || !customer.value || !product || !product.value) {
        if (batchSelect) batchSelect.innerHTML = '<option value="">— Select batch —</option>';
        clearBatchDisplays();
        return Promise.resolve();
      }
      return fetch(
        urls.logsheets +
          '?cust_id=' +
          encodeURIComponent(customer.value) +
          '&prod_id=' +
          encodeURIComponent(product.value)
      )
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var rows = data.logsheets || [];
          if (isMultiSection()) {
            applyMultiCatalogFromLogSheets(rows, !!preserveMultiSelection);
            if (batchSelect) {
              batchSelect.innerHTML = '<option value="">— Select batch —</option>';
              batchSelect.value = '';
            }
          } else {
            if (!batchSelect) return;
            batchSelect.innerHTML = '<option value="">— Select batch —</option>';
            rows.forEach(function (ls) {
              var o = document.createElement('option');
              o.value = String(ls.logsheet_id) + '|' + String(ls.batch_dtl_id);
              var bn = ls.batch_no || '—';
              var slot = (ls.slot_label || '').trim();
              o.textContent = slot && slot !== 'Single' ? bn + ' — ' + slot : bn;
              o.dataset.row = JSON.stringify(ls);
              batchSelect.appendChild(o);
            });
            batchSelect.value = '';
            clearBatchDisplays();
          }
          if (typeof initSearchableDropdowns === 'function') {
            initSearchableDropdowns(form);
          }
        });
    }

    function loadSpecs() {
      if (!specSelect || !urls.specs) return Promise.resolve();
      if (!customer || !customer.value || !product || !product.value) {
        specSelect.innerHTML = '<option value="">— Select specification —</option>';
        if (specId) specId.value = '';
        return Promise.resolve();
      }
      return fetch(
        urls.specs +
          '?cust_id=' +
          encodeURIComponent(customer.value) +
          '&prod_id=' +
          encodeURIComponent(product.value)
      )
        .then(function (r) { return r.json(); })
        .then(function (data) {
          specSelect.innerHTML = '<option value="">— Select specification —</option>';
          (data.specs || []).forEach(function (s) {
            var o = document.createElement('option');
            o.value = String(s.spec_id);
            o.textContent = s.spec_name || ('Spec ' + s.spec_id);
            specSelect.appendChild(o);
          });
          specSelect.value = '';
          if (specId) specId.value = '';
          if (typeof initSearchableDropdowns === 'function') {
            initSearchableDropdowns(form);
          }
        });
    }

    function formatBatchSize(ls) {
      if (!ls) return '';
      if (ls.batch_size_display) return String(ls.batch_size_display);
      var lRaw = ls.batch_qty_l;
      var nRaw = ls.batch_qty_n;
      var l = '';
      var n = '';
      if (lRaw != null && lRaw !== '') {
        var lx = parseFloat(String(lRaw).replace(',', '.'));
        l = isFinite(lx) ? lx.toFixed(3) + ' L' : String(lRaw) + ' L';
      }
      if (nRaw != null && nRaw !== '') {
        var nx = parseFloat(String(nRaw).replace(',', '.'));
        n = isFinite(nx) ? String(Math.round(nx)) + ' nos' : String(nRaw) + ' nos';
      }
      if (l && n) return l + ' / ' + n;
      return l || n || '';
    }

    function applyBatchRow(ls) {
      if (isMultiSection()) {
        return;
      }
      if (!ls) {
        clearBatchDisplays();
        return;
      }
      if (batchDtl) batchDtl.value = String(ls.batch_dtl_id || '');
      if (logSheetId) logSheetId.value = String(ls.logsheet_id || '');
      if (mfgDisp) mfgDisp.value = ls.mfg_dt || '';
      if (expDisp) expDisp.value = ls.exp_dt || '';
      if (batchSizeDisp) batchSizeDisp.value = formatBatchSize(ls);
      if (ordDisp) {
        var ord = ls.cust_ord_id || '';
        var dt = ls.ord_rec_dt || '';
        ordDisp.value = ord && dt ? 'Ord. ' + ord + ' · ' + dt : ord || dt || '';
      }
      if (colourDisp) colourDisp.value = ls.slot_label || '';

      if (urls.productMeta && product && product.value) {
        fetch(urls.productMeta + '?prod_id=' + encodeURIComponent(product.value))
          .then(function (r) { return r.json(); })
          .then(function (meta) {
            if (meta.tablet_layer === 'Double') {
              if (layerDisp) layerDisp.value = 'Double layer';
            } else if (meta.tablet_layer === 'Single') {
              if (layerDisp) layerDisp.value = 'Single layer';
            } else if (layerDisp) {
              layerDisp.value = meta.tablet_layer || '';
            }
          })
          .catch(function () { /* ignore */ });
      }

      if (urls.sectionStatus && ls.batch_dtl_id) {
        fetch(urls.sectionStatus + '?batch_dtl_id=' + encodeURIComponent(ls.batch_dtl_id))
          .then(function (r) { return r.json(); })
          .then(function (data) {
            if (!statusBody) return;
            var rows = data.sections || [];
            if (!rows.length) {
              statusBody.innerHTML = '<tr><td colspan="2" class="dpr-muted">No data</td></tr>';
              return;
            }
            statusBody.innerHTML = rows
              .map(function (x) {
                return (
                  '<tr><td>' +
                  esc(x.section) +
                  '</td><td class="dpr-status-numeric">' +
                  esc(x.qty_nos) +
                  '</td></tr>'
                );
              })
              .join('');
          })
          .catch(function () {
            if (statusBody) {
              statusBody.innerHTML = '<tr><td colspan="2" class="dpr-muted">Could not load status</td></tr>';
            }
          });
      }
    }

    function onBatchChange() {
      if (isMultiSection()) return;
      var opt = batchSelect && batchSelect.options[batchSelect.selectedIndex];
      if (!opt || !opt.value) {
        clearBatchDisplays();
        return;
      }
      var parts = opt.value.split('|');
      var ls = null;
      try {
        ls = opt.dataset.row ? JSON.parse(opt.dataset.row) : null;
      } catch (e) {
        ls = null;
      }
      if (!ls) {
        ls = {
          logsheet_id: parts[0],
          batch_dtl_id: parts[1],
          mfg_dt: '',
          exp_dt: '',
          batch_qty_l: '',
          batch_qty_n: '',
          cust_ord_id: '',
          ord_rec_dt: '',
          slot_label: '',
        };
      }
      applyBatchRow(ls);
    }

    function onSpecChange() {
      if (!specSelect || !specId) return;
      specId.value = specSelect.value || '';
    }

    if (section) {
      section.addEventListener('change', function () {
        loadMachines(null);
        loadOperators(null, true);
        toggleBatchLanes();
        applyMachineWorkingUi();
        if (customer && customer.value && product && product.value) {
          loadBatches();
        }
      });
    }

    if (machineWorking) {
      machineWorking.addEventListener('change', function () {
        applyMachineWorkingUi();
      });
    }

    if (operators) {
      operators.addEventListener('change', function () {
        updateOperatorCount();
      });
    }

    if (customer) {
      customer.addEventListener('change', function () {
        loadCustomerProducts().then(function () {
          loadBatches();
          loadSpecs();
        });
      });
    }

    if (product) {
      product.addEventListener('change', function () {
        loadBatches();
        loadSpecs();
      });
    }

    if (batchSelect) {
      batchSelect.addEventListener('change', onBatchChange);
    }

    if (batchAddSelect) {
      batchAddSelect.addEventListener('change', function () {
        if (!isMultiSection()) return;
        var v = batchAddSelect.value;
        if (!v) return;
        var id = parseInt(v, 10);
        if (!isFinite(id)) {
          batchAddSelect.value = '';
          return;
        }
        var name = '';
        multiLogCatalog.forEach(function (ls) {
          if (parseInt(ls.logsheet_id, 10) === id) {
            name = formatLogsheetOptionLabel(ls);
          }
        });
        if (!name) {
          batchAddSelect.value = '';
          return;
        }
        if (multiSelected.some(function (x) { return x.id === id; })) {
          batchAddSelect.value = '';
          return;
        }
        multiSelected.push({ id: id, name: name });
        batchAddSelect.value = '';
        updateMultiBatchUi();
        if (statusBody) {
          statusBody.innerHTML =
            '<tr><td colspan="2" class="dpr-muted">Section status is not loaded for multi-batch sections.</td></tr>';
        }
      });
    }

    if (batchDisplay) {
      batchDisplay.addEventListener('dblclick', function () {
        if (!isMultiSection()) return;
        multiSelected = [];
        updateMultiBatchUi();
      });
    }

    if (form) {
      form.addEventListener('submit', function () {
        if (isMultiSection()) {
          syncLogSheetIdsHidden();
        }
      });
    }

    if (specSelect) {
      specSelect.addEventListener('change', onSpecChange);
    }

    if (startTime) startTime.addEventListener('change', function () {
      updateTotalTimeDisplay(startTime, endTime, totalTime);
    });
    if (endTime) endTime.addEventListener('change', function () {
      updateTotalTimeDisplay(startTime, endTime, totalTime);
    });

    function showGridErr(msg) {
      if (gridErr) gridErr.textContent = msg || '';
    }

    function loadGrid() {
      if (!urls.listRows || !gridBody) return;
      var s = gridStart && gridStart.value;
      var e = gridEnd && gridEnd.value;
      var editBase = form && form.action ? form.action.split('?')[0] : '';
      showGridErr('');
      if (!s || !e) {
        showGridErr('Choose start and end dates.');
        return;
      }
      fetch(urls.listRows + '?start=' + encodeURIComponent(s) + '&end=' + encodeURIComponent(e))
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.error) {
            showGridErr(data.error);
            gridBody.innerHTML = '<tr><td colspan="12" class="dpr-muted">' + esc(data.error) + '</td></tr>';
            return;
          }
          var rows = data.rows || [];
          if (!rows.length) {
            gridBody.innerHTML = '<tr><td colspan="12" class="dpr-muted">No rows in this range.</td></tr>';
            return;
          }
          gridBody.innerHTML = rows
            .map(function (x, i) {
              var editHref = editBase + '?edit_pk=' + encodeURIComponent(String(x.trn_dpr_id));
              return (
                '<tr><td class="col-idx">' +
                esc(i + 1) +
                '</td><td>' +
                esc(x.trn_dpr_dt) +
                '</td><td>' +
                esc(x.section) +
                '</td><td>' +
                esc(x.machine) +
                '</td><td>' +
                esc(x.shift) +
                '</td><td>' +
                esc(x.working) +
                '</td><td>' +
                esc(x.customer) +
                '</td><td>' +
                esc(x.product) +
                '</td><td>' +
                esc(x.batch_no) +
                '</td><td class="dpr-col-qty-left">' +
                esc(x.qty_nos) +
                '</td><td>' +
                esc(x.total_time) +
                '</td><td class="col-actions"><a href="' +
                editHref +
                '" class="btn-action btn-edit" title="Edit"><i class="bi bi-pencil"></i></a></td></tr>'
              );
            })
            .join('');
        })
        .catch(function () {
          showGridErr('Could not load data.');
          gridBody.innerHTML = '<tr><td colspan="12" class="dpr-muted">Could not load data.</td></tr>';
        });
    }

    var showBtn = document.getElementById('dprShowGrid');
    if (showBtn) showBtn.addEventListener('click', loadGrid);

    toggleBatchLanes();
    applyMachineWorkingUi();
    if (section && section.value) {
      loadMachines(machine && machine.value ? machine.value : null).then(function () {
        var selectedOperators = editPayload.operator_ids || [];
        if (!selectedOperators.length && operators) {
          selectedOperators = [].map.call(operators.querySelectorAll('input[name="operators"]:checked'), function (input) {
            return input.value;
          });
        }
        if (!selectedOperators.length && operators && operators.dataset.selectedOperators) {
          selectedOperators = operators.dataset.selectedOperators.split(',').filter(Boolean);
        }
        return loadOperators(selectedOperators);
      });
    }
    if (customer && customer.value) {
      loadCustomerProducts().then(function () {
        if (product && product.value) {
          loadBatches();
          loadSpecs();
        }
      });
    }
    if (batchSelect && batchSelect.value) {
      onBatchChange();
    }
    onSpecChange();
    updateTotalTimeDisplay(startTime, endTime, totalTime);

    if (
      editPayload.trn_dpr_id &&
      editPayload.machine_working === 'working' &&
      editPayload.cust_id &&
      editPayload.prod_id &&
      editPayload.multi_batch &&
      editPayload.log_sheet_ids &&
      editPayload.log_sheet_ids.length
    ) {
      toggleBatchLanes();
      if (customer) customer.value = String(editPayload.cust_id);
      loadCustomerProducts()
        .then(function () {
          if (product) product.value = String(editPayload.prod_id);
          if (typeof initSearchableDropdowns === 'function') initSearchableDropdowns(form);
          return Promise.all([loadSpecs(), loadBatches(true)]);
        })
        .then(function () {
          if (editPayload.log_sheet_ids && editPayload.log_sheet_ids.length) {
            multiSelected = [];
            editPayload.log_sheet_ids.forEach(function (rawId) {
              var id = parseInt(rawId, 10);
              if (!isFinite(id)) return;
              var name = '';
              multiLogCatalog.forEach(function (ls) {
                if (parseInt(ls.logsheet_id, 10) === id) {
                  name = formatLogsheetOptionLabel(ls);
                }
              });
              if (name) multiSelected.push({ id: id, name: name });
            });
            updateMultiBatchUi();
          }
          if (editPayload.batch_size_lakh != null && editPayload.batch_size_lakh !== '') {
            var bslEl = document.getElementById('dprBatchSizeLakh');
            if (bslEl) bslEl.value = String(editPayload.batch_size_lakh);
          }
          if (specSelect && editPayload.spec_id) {
            var sv = String(editPayload.spec_id);
            if ([].some.call(specSelect.options, function (o) { return o.value === sv; })) {
              specSelect.value = sv;
            }
            if (specId) specId.value = sv;
            if (typeof initSearchableDropdowns === 'function') initSearchableDropdowns(form);
          }
        })
        .catch(function () { /* ignore */ });
    } else if (
      editPayload.trn_dpr_id &&
      editPayload.machine_working === 'working' &&
      editPayload.cust_id &&
      editPayload.prod_id &&
      editPayload.batch_dtl_id &&
      editPayload.log_sheet_id
    ) {
      toggleBatchLanes();
      if (customer) customer.value = String(editPayload.cust_id);
      loadCustomerProducts()
        .then(function () {
          if (product) product.value = String(editPayload.prod_id);
          if (typeof initSearchableDropdowns === 'function') initSearchableDropdowns(form);
          return Promise.all([loadSpecs(), loadBatches()]);
        })
        .then(function () {
          var v = String(editPayload.log_sheet_id) + '|' + String(editPayload.batch_dtl_id);
          if (batchSelect) {
            var ok = [].some.call(batchSelect.options, function (o) { return o.value === v; });
            if (ok) batchSelect.value = v;
            if (typeof initSearchableDropdowns === 'function') initSearchableDropdowns(form);
            onBatchChange();
          }
          if (specSelect && editPayload.spec_id) {
            var sv2 = String(editPayload.spec_id);
            if ([].some.call(specSelect.options, function (o) { return o.value === sv2; })) {
              specSelect.value = sv2;
            }
            if (specId) specId.value = sv2;
            if (typeof initSearchableDropdowns === 'function') initSearchableDropdowns(form);
          }
        })
        .catch(function () { /* ignore */ });
    } else if (editPayload.trn_dpr_id && editPayload.machine_working === 'not_working') {
      applyMachineWorkingUi();
    }
  };
})();
