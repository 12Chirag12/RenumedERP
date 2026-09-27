/**
 * RM Dispensing — customer → product → batch/spec → BOM grid → save.
 */
(function () {
  'use strict';

  function readJsonObject(id) {
    var el = document.getElementById(id);
    if (!el || !el.textContent) return {};
    try {
      var o = JSON.parse(el.textContent);
      return o && typeof o === 'object' ? o : {};
    } catch (e) {
      return {};
    }
  }

  function esc(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function initPage_rm_dispensing() {
    var form = document.getElementById('rmForm');
    if (!form) return;

    var urls = readJsonObject('rmAjaxUrls');
    var editPayload = readJsonObject('rmEditPayload');
    var customer = document.getElementById('rmCustomer');
    var product = document.getElementById('rmProduct');
    var batchSelect = document.getElementById('rmBatchSelect');
    var batchHidden = document.getElementById('rmLogsheetId');
    var spec = document.getElementById('rmSpec');
    var layerDisp = document.getElementById('rmLayerDisplay');
    var sizeLDisp = document.getElementById('rmBatchSizeL');
    var sizeNDisp = document.getElementById('rmBatchSizeN');
    var gridBody = document.getElementById('rmGridBody');
    var gridErr = document.getElementById('rmGridErr');
    var linesHidden = document.getElementById('rmLinesJson');
    var dispDt = document.getElementById('rmDispDt');
    var listBody = document.getElementById('rmListBody');
    var listCount = document.getElementById('rmListCount');

    var fetchOpts = { credentials: 'same-origin', headers: { Accept: 'application/json' } };

    var state = {
      logsheets: [],
      bomItems: [],
    };
    var isEdit = !!(editPayload && editPayload.dispensing_id);
    var editDefaults = {
      logsheet_id: (batchHidden && batchHidden.value) ? String(batchHidden.value) : '',
      spec_id: (spec && spec.value) ? String(spec.value) : '',
    };
    var editInitDone = false;

    if (typeof initSearchableDropdowns === 'function') {
      initSearchableDropdowns(form);
    }

    function setGridErr(msg) {
      if (gridErr) gridErr.textContent = msg || '';
    }

    function resetBatchUI(preserveHidden) {
      state.logsheets = [];
      if (batchSelect) {
        batchSelect.innerHTML = '<option value="">— Select batch —</option>';
        batchSelect.value = '';
      }
      if (batchHidden && !preserveHidden) batchHidden.value = '';
      if (sizeLDisp) sizeLDisp.value = '';
      if (sizeNDisp) sizeNDisp.value = '';
    }

    function resetSpecUI() {
      if (spec) {
        spec.innerHTML = '<option value="">— Select specification —</option>';
        if (!isEdit) spec.value = '';
      }
    }

    function resetGridUI(hint) {
      state.bomItems = [];
      setGridErr('');
      if (!gridBody) return;
      gridBody.innerHTML = '<tr><td colspan="9" class="rm-muted">' + esc(hint || 'Select inputs…') + '</td></tr>';
      serialize();
    }

    function rebuildSelect2(el) {
      if (!el) return;
      if (window.jQuery && el.classList.contains('searchable-dropdown')) {
        try { window.jQuery(el).select2('destroy'); } catch (e) {}
      }
      if (typeof initSearchableDropdowns === 'function') initSearchableDropdowns(form);
    }

    function setProductOptions(rows) {
      if (!product) return;
      var cur = product.value;
      product.innerHTML = '<option value="">— Select product —</option>';
      (rows || []).forEach(function (r) {
        var o = document.createElement('option');
        o.value = r.prod_id;
        o.textContent = r.prod_name;
        product.appendChild(o);
      });
      if (cur && [].some.call(product.options, function (op) { return op.value === cur; })) {
        product.value = cur;
      }
      rebuildSelect2(product);

      // Edit bootstrap: once product options exist (and value is set by server),
      // explicitly load dependent batches/specs (change event won't fire).
      if (!editInitDone && editPayload && editPayload.dispensing_id && product.value) {
        fetchBatchesAndSpecs();
      }
    }

    function setBatchOptions(rows) {
      if (!batchSelect) return;
      var cur = (batchHidden && batchHidden.value)
        ? String(batchHidden.value)
        : (batchSelect.value ? String(batchSelect.value) : (isEdit ? String(editDefaults.logsheet_id || '') : ''));
      batchSelect.innerHTML = '<option value="">— Select batch —</option>';
      (rows || []).forEach(function (b) {
        var o = document.createElement('option');
        o.value = String(b.logsheet_id);
        var ord = (b.cust_ord_id || '').trim();
        var dt = (b.ord_rec_dt || '').trim();
        var extra = ord && dt ? (' — ' + ord + ' / ' + dt) : (ord || dt ? (' — ' + (ord || dt)) : '');
        var slot = (b.slot_label || '').trim();
        var slotTxt = slot ? (' [' + slot + ']') : '';
        o.textContent = (b.batch_no || '') + slotTxt + extra;
        batchSelect.appendChild(o);
      });
      if (cur && [].some.call(batchSelect.options, function (op) { return op.value === cur; })) {
        batchSelect.value = cur;
        applySelectedBatch();
      }
      rebuildSelect2(batchSelect);
    }

    function setSpecOptions(rows) {
      if (!spec) return;
      var cur = spec.value || (isEdit ? String(editDefaults.spec_id || '') : '');
      spec.innerHTML = '<option value="">— Select specification —</option>';
      (rows || []).forEach(function (s) {
        var o = document.createElement('option');
        o.value = String(s.spec_id);
        o.textContent = s.spec_name || ('Spec ' + s.spec_id);
        spec.appendChild(o);
      });
      if (cur && [].some.call(spec.options, function (op) { return op.value === cur; })) {
        spec.value = cur;
        loadBomItems();
      }
      rebuildSelect2(spec);
    }

    function fetchCustomerProducts(opts) {
      opts = opts || {};
      resetBatchUI(!!opts.preserveHidden);
      resetSpecUI();
      if (!opts.preserveGrid) resetGridUI('Select customer and product…');
      if (layerDisp) layerDisp.value = '';
      loadList();

      if (!customer || !customer.value) {
        setProductOptions([]);
        return;
      }
      fetch(urls.customerProducts + '?cust_id=' + encodeURIComponent(customer.value), fetchOpts)
        .then(function (r) { return r.json(); })
        .then(function (d) {
          setProductOptions(d.products || []);
          if (isEdit && product && product.value) fetchBatchesAndSpecs({ preserveHidden: true, preserveGrid: true });
        })
        .catch(function () { setProductOptions([]); });
    }

    function fetchProductMeta() {
      if (!layerDisp) return;
      layerDisp.value = '';
      if (!urls.productMeta || !product || !product.value) return;
      fetch(urls.productMeta + '?prod_id=' + encodeURIComponent(product.value), fetchOpts)
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d && !d.error) layerDisp.value = d.tablet_layer || '';
        })
        .catch(function () { layerDisp.value = ''; });
    }

    function fetchBatchesAndSpecs(opts) {
      opts = opts || {};
      resetBatchUI(!!opts.preserveHidden);
      resetSpecUI();
      if (!opts.preserveGrid) resetGridUI('Select batch and specification…');
      fetchProductMeta();
      loadList();

      if (!customer || !customer.value || !product || !product.value) return;

      var q = '?cust_id=' + encodeURIComponent(customer.value) + '&prod_id=' + encodeURIComponent(product.value);

      fetch(urls.batches + q, fetchOpts)
        .then(function (r) { return r.json(); })
        .then(function (d) {
          state.logsheets = d.logsheets || [];
          setBatchOptions(state.logsheets);
        })
        .catch(function () {
          state.logsheets = [];
          setBatchOptions([]);
        });

      fetch(urls.specs + q, fetchOpts)
        .then(function (r) { return r.json(); })
        .then(function (d) { setSpecOptions(d.specs || []); })
        .catch(function () { setSpecOptions([]); });
    }

    function applySelectedBatch() {
      setGridErr('');
      if (!batchSelect || !batchHidden) return;
      var id = batchSelect.value || '';
      batchHidden.value = id;
      var b = null;
      for (var i = 0; i < state.logsheets.length; i++) {
        if (String(state.logsheets[i].logsheet_id) === String(id)) { b = state.logsheets[i]; break; }
      }
      if (!b) {
        if (sizeLDisp) sizeLDisp.value = '';
        if (sizeNDisp) sizeNDisp.value = '';
        return;
      }
      function fmt3(x) {
        var n = parseFloat(String(x).replace(',', '.'));
        if (!isFinite(n)) return (x == null ? '' : String(x));
        return n.toFixed(3);
      }
      if (sizeLDisp) sizeLDisp.value = fmt3(b.batch_qty_l || '');
      if (sizeNDisp) sizeNDisp.value = b.batch_qty_n || '';
      loadList();
      // Batch size affects auto-calculated standard qty.
      if (spec && spec.value) loadBomItems();
    }

    function todayIso() {
      var d = new Date();
      return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
    }

    function defaultIssueDate() {
      var v = dispDt && dispDt.value ? String(dispDt.value).trim() : '';
      return v || todayIso();
    }

    function getCheckedStageIdsInGrid() {
      if (!gridBody) return [];
      var out = [];
      gridBody.querySelectorAll('input.rm-stage-toggle[type="checkbox"]').forEach(function (cb) {
        if (cb && cb.checked && cb.dataset && cb.dataset.stageId) out.push(String(cb.dataset.stageId));
      });
      return out;
    }

    function renderGrid(items) {
      if (!gridBody) return;
      gridBody.innerHTML = '';
      if (!items || !items.length) {
        gridBody.innerHTML = '<tr><td colspan="9" class="rm-muted">No BOM items for this specification.</td></tr>';
        serialize();
        return;
      }

      // Group by stage while preserving BOM order.
      var stageChecked = {};
      if (editPayload && editPayload.selected_stage_ids && editPayload.selected_stage_ids.length) {
        editPayload.selected_stage_ids.forEach(function (x) { stageChecked[String(x)] = true; });
      }

      var stageOrder = [];
      var groups = {};
      items.forEach(function (it) {
        var sid = String(it.stage_id);
        if (!groups[sid]) { groups[sid] = []; stageOrder.push(sid); }
        groups[sid].push(it);
      });

      stageOrder.forEach(function (stageId) {
        var rows = groups[stageId] || [];
        if (!rows.length) return;
        var checkedAttr = stageChecked[stageId] ? ' checked' : '';
        var rowspan = rows.length;

        rows.forEach(function (it, idx) {
          var tr = document.createElement('tr');
          tr.className = 'rm-grid-row';
          tr.dataset.stageId = String(it.stage_id);
          tr.dataset.itemId = String(it.item_id);

          var stageCells = '';
          if (idx === 0) {
            stageCells =
              '<td rowspan="' + String(rowspan) + '">' +
                '<label class="rm-stage-check" title="Select stage">' +
                  '<input type="checkbox" class="rm-stage-toggle" data-stage-id="' + esc(stageId) + '"' + checkedAttr + '>' +
                '</label>' +
              '</td>' +
              '<td class="rm-ro" rowspan="' + String(rowspan) + '">' + esc(it.stage_name || '') + '</td>';
          }
          var uom = (it.uom || '').trim();
          var uomS = uom ? (' ' + uom) : '';
          function fmt3(x) {
            var n = parseFloat(String(x).replace(',', '.'));
            if (!isFinite(n)) return (x == null ? '' : String(x));
            return n.toFixed(3);
          }
          var perLakhTxt = fmt3(it.qty_per_lakh) + uomS;
          var autoStd = fmt3(it.std_qty);
          var availTxt = (it.available_qty != null && String(it.available_qty).trim() !== '')
            ? fmt3(it.available_qty)
            : '—';

          tr.innerHTML =
            stageCells +
            '<td class="rm-ro">' + esc(it.item_name || '') + '</td>' +
            '<td class="rm-ro num"><span class="rm-qty-cell"><span class="rm-qty-val">' + esc(availTxt) +
            '</span>' + (uom ? '<span class="rm-uom">' + esc(uom) + '</span>' : '') + '</span></td>' +
            '<td class="rm-ro rm-perlakh">' + esc(perLakhTxt) + '</td>' +
            '<td class="rm-ro rm-stdqty">' + esc(autoStd + uomS) + '</td>' +
            '<td><input type="number" class="cu-input rm-add rm-num" min="0" step="0.001" value=""></td>' +
            '<td><input type="date" class="cu-input rm-date" value="' + esc(defaultIssueDate()) + '"></td>' +
            '<td><input type="text" class="cu-input rm-rem" maxlength="20" value="" placeholder="Optional"></td>';

          gridBody.appendChild(tr);
        });
      });
      serialize();
    }

    function applyEditLineValuesIfAny() {
      if (!editPayload || !editPayload.lines || !editPayload.lines.length) return;
      if (!gridBody) return;
      var map = {};
      editPayload.lines.forEach(function (ln) {
        var key = String(ln.stage_id) + '|' + String(ln.item_id);
        map[key] = ln;
      });
      gridBody.querySelectorAll('tr.rm-grid-row').forEach(function (tr) {
        var stageId = tr.dataset.stageId || '';
        var itemId = tr.dataset.itemId || '';
        var key = String(stageId) + '|' + String(itemId);
        var ln = map[key];
        if (!ln) return;
        var add = tr.querySelector('input.rm-add');
        var dt = tr.querySelector('input.rm-date');
        var rem = tr.querySelector('input.rm-rem');
        if (add) add.value = (ln.issue_add_qty == null ? '0' : String(ln.issue_add_qty));
        if (dt && ln.issue_date) dt.value = ln.issue_date;
        if (rem) rem.value = ln.remarks || '';
      });
      serialize();
    }

    function loadBomItems() {
      setGridErr('');
      if (!spec || !spec.value) {
        resetGridUI('Select specification…');
        return;
      }
      var u = urls.bomItems + '?spec_id=' + encodeURIComponent(spec.value);
      if (customer && customer.value) u += '&cust_id=' + encodeURIComponent(customer.value);
      if (batchHidden && batchHidden.value) u += '&logsheet_id=' + encodeURIComponent(batchHidden.value);
      fetch(u, fetchOpts)
        .then(function (r) {
          if (!r.ok) return r.json().then(function (j) { throw new Error(j.error || r.statusText); });
          return r.json();
        })
        .then(function (d) {
          state.bomItems = d.items || [];
          renderGrid(state.bomItems);
          applyEditLineValuesIfAny();
        })
        .catch(function (e) {
          resetGridUI('—');
          setGridErr(e.message || 'Could not load BOM items.');
        });
    }

    function serialize() {
      if (!linesHidden) return;
      if (!gridBody) { linesHidden.value = '[]'; return; }
      var allowed = {};
      getCheckedStageIdsInGrid().forEach(function (sid) { allowed[String(sid)] = true; });
      var out = [];
      gridBody.querySelectorAll('tr.rm-grid-row').forEach(function (tr) {
        var stageId = tr.dataset.stageId;
        var itemId = tr.dataset.itemId;
        if (!allowed[String(stageId)]) return;
        var add = tr.querySelector('input.rm-add');
        var dt = tr.querySelector('input.rm-date');
        var rem = tr.querySelector('input.rm-rem');
        out.push({
          stage_id: stageId ? parseInt(stageId, 10) : null,
          item_id: itemId ? parseInt(itemId, 10) : null,
          // Server calculates standard dispensing qty; client does not send it.
          issue_qty: '',
          issue_add_qty: add ? add.value : '',
          issue_date: dt ? dt.value : '',
          remarks: rem ? rem.value : '',
        });
      });
      linesHidden.value = JSON.stringify(out);
    }

    form.addEventListener('input', function (e) {
      if (!e.target) return;
      if (e.target.classList.contains('rm-issue') || e.target.classList.contains('rm-add') ||
          e.target.classList.contains('rm-date') || e.target.classList.contains('rm-rem')) {
        serialize();
      }
    });

    form.addEventListener('change', function (e) {
      if (!e.target) return;
      if (e.target.classList.contains('rm-stage-toggle')) {
        serialize();
      }
    });

    form.addEventListener('submit', function (e) {
      serialize();
      setGridErr('');
      var selStages = getCheckedStageIdsInGrid();
      if (!selStages.length) {
        setGridErr('Select at least one stage.');
        e.preventDefault();
        return;
      }
      var raw = (linesHidden && linesHidden.value) ? linesHidden.value.trim() : '';
      if (!raw || raw === '[]') {
        setGridErr('Add at least one dispensing row.');
        e.preventDefault();
        return;
      }
      try {
        var rows = JSON.parse(raw);
        var any = false;
        for (var i = 0; i < rows.length; i++) {
          var iq = parseFloat(rows[i].issue_qty || 0);
          var aq = parseFloat(rows[i].issue_add_qty || 0);
          if ((iq > 0) || (aq > 0)) { any = true; break; }
        }
        if (!any) {
          setGridErr('Enter quantity in at least one row.');
          e.preventDefault();
        }
      } catch (ex) {
        setGridErr('Invalid dispensing grid data.');
        e.preventDefault();
      }
    });

    function renderListRows(rows) {
      if (!listBody) return;
      listBody.innerHTML = '';
      if (!rows || !rows.length) {
        listBody.innerHTML = '<tr><td colspan="9" class="empty-row">No dispensing records found.</td></tr>';
        if (listCount) listCount.textContent = '(0)';
        return;
      }
      if (listCount) listCount.textContent = '(' + String(rows.length) + ')';
      rows.forEach(function (r) {
        var tr = document.createElement('tr');
        var ok = String(r.rm_complete || 'N').toUpperCase() === 'Y';
        var editHref = (window.location.pathname || '') + '?edit_pk=' + encodeURIComponent(r.dispensing_id);
        tr.innerHTML =
          '<td class="rm-ro">' + esc(r.dispensing_id) + '</td>' +
          '<td>' + esc(r.dispensing_dt || '') + '</td>' +
          '<td>' + esc(r.customer || '') + '</td>' +
          '<td>' + esc(r.product || '') + '</td>' +
          '<td>' + esc((r.batch_no || '') + (r.slot_label ? (' [' + r.slot_label + ']') : '')) + '</td>' +
          '<td>' + esc(r.spec || '') + '</td>' +
          '<td>' + esc(r.stage_count || 0) + '</td>' +
          '<td>' + (ok ? 'Yes' : 'No') + '</td>' +
          '<td class="col-actions"><a href="' + esc(editHref) + '" class="btn-action btn-edit" title="Edit"><i class="bi bi-pencil"></i></a></td>';
        listBody.appendChild(tr);
      });
    }

    function loadList() {
      if (!urls.listRows) return;
      var q = '?';
      if (customer && customer.value) q += '&cust_id=' + encodeURIComponent(customer.value);
      if (product && product.value) q += '&prod_id=' + encodeURIComponent(product.value);
      if (batchHidden && batchHidden.value) q += '&logsheet_id=' + encodeURIComponent(batchHidden.value);
      fetch(urls.listRows + q, fetchOpts)
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d && d.error) { renderListRows([]); return; }
          renderListRows((d && d.rows) ? d.rows : []);
        })
        .catch(function () {
          if (listBody) listBody.innerHTML = '<tr><td colspan="9" class="empty-row">Could not load dispensing records.</td></tr>';
          if (listCount) listCount.textContent = '';
        });
    }

    if (customer) customer.addEventListener('change', fetchCustomerProducts);
    if (product) product.addEventListener('change', fetchBatchesAndSpecs);
    if (batchSelect) batchSelect.addEventListener('change', applySelectedBatch);
    if (spec) spec.addEventListener('change', loadBomItems);
    // Initial hydration (edit/new)
    if (isEdit) {
      if (customer && customer.value) fetchCustomerProducts({ preserveHidden: true, preserveGrid: true });
      else if (product && product.value) fetchBatchesAndSpecs({ preserveHidden: true, preserveGrid: true });
    } else {
      if (customer && customer.value) fetchCustomerProducts();
      if (customer && customer.value && product && product.value) fetchBatchesAndSpecs();
    }
    if (spec && spec.value) loadBomItems();
    loadList();
    if (editPayload && editPayload.dispensing_id) editInitDone = true;
  }

  window.initPage_rm_dispensing = initPage_rm_dispensing;
})();

