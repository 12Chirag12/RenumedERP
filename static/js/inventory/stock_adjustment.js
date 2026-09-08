/**
 * Stock adjustment — header + line grid + batch grid; serializes to JSON for POST.
 */
function initPage_stock_adj() {
  var root = document.getElementById('stkAdjRoot');
  if (!root) return;

  var ajaxUrl = root.getAttribute('data-ajax-masters') || '';
  var metaUrl = root.getAttribute('data-ajax-sku-meta') || '';
  var invDefaultsUrl = root.getAttribute('data-ajax-inv-defaults') || '';
  var today = root.getAttribute('data-today') || '';

  var customerSel = document.getElementById('stkAdjCustomer');
  var dateInp = document.getElementById('stkAdjDate');
  var typeRadios = document.querySelectorAll('input[name="stk_adj_type_ui"]');
  var itemTypeSel = document.getElementById('stkAdjItemType');
  var remarksTa = document.getElementById('stkAdjRemarks');
  var lineTbody = document.getElementById('stkAdjLineTbody');
  var lineEmpty = document.getElementById('stkAdjLineEmpty');
  var batchPanel = document.getElementById('stkAdjBatchPanel');
  var batchTitle = document.getElementById('stkAdjBatchTitle');
  var batchTbody = document.getElementById('stkAdjBatchTbody');
  var modeHint = document.getElementById('stkAdjModeHint');
  var docField = document.getElementById('stkAdjDocField');
  var form = document.getElementById('stkAdjMainForm');
  if (!form) return;

  var ignoreHeaderChange = false;

  var state = {
    stk_adj_id: null,
    customer_id: '',
    stk_adj_dt: today,
    stk_adj_type: 'A',
    item_type_id: '',
    remarks: '',
    lines: [],
    masterRows: [],
    masterMode: '',
    activeLine: 0,
  };

  var initEl = document.getElementById('stkAdjInitialDoc-data');
  if (initEl && initEl.textContent) {
    try {
      var parsed = JSON.parse(initEl.textContent);
      if (parsed && typeof parsed === 'object') {
        if (parsed.stk_adj_id != null) state.stk_adj_id = parsed.stk_adj_id;
        if (parsed.customer_id != null) state.customer_id = String(parsed.customer_id);
        if (parsed.stk_adj_dt) state.stk_adj_dt = String(parsed.stk_adj_dt).slice(0, 10);
        if (parsed.stk_adj_type) state.stk_adj_type = parsed.stk_adj_type;
        if (parsed.item_type_id != null) state.item_type_id = String(parsed.item_type_id);
        if (parsed.remarks != null) state.remarks = String(parsed.remarks);
        state.lines = Array.isArray(parsed.lines) ? parsed.lines : [];
        state.lines.forEach(function (ln) {
          if (!ln.batches || !Array.isArray(ln.batches) || ln.batches.length === 0) {
            ln.batches = [{ batch_no: '', mfg_date: '', exp_date: '', batch_qty: '' }];
          }
          if (ln.sku_meta === undefined) ln.sku_meta = null;
        });
      }
    } catch (e) {
      console.warn('stk adj initial doc', e);
    }
  }

  function getAdjType() {
    var v = 'A';
    typeRadios.forEach(function (r) {
      if (r.checked) v = r.value;
    });
    return v;
  }

  /** Keep Select2 UI in sync after programmatic header values (edit / repost). */
  function syncHeaderSelect2Widgets() {
    if (!window.jQuery || !window.jQuery.fn || !window.jQuery.fn.select2) return;
    [customerSel, itemTypeSel].forEach(function (el) {
      if (!el || !el.classList || !el.classList.contains('searchable-dropdown')) return;
      var $el = window.jQuery(el);
      if ($el.hasClass('select2-hidden-accessible')) {
        $el.val(el.value).trigger('change');
      }
    });
  }

  function syncHeaderDom() {
    ignoreHeaderChange = true;
    try {
      if (customerSel) customerSel.value = state.customer_id || '';
      if (dateInp) dateInp.value = state.stk_adj_dt || '';
      typeRadios.forEach(function (r) {
        r.checked = r.value === state.stk_adj_type;
      });
      if (itemTypeSel) itemTypeSel.value = state.item_type_id || '';
      if (remarksTa) remarksTa.value = state.remarks || '';
      syncHeaderSelect2Widgets();
    } finally {
      ignoreHeaderChange = false;
    }
  }

  function readHeaderFromDom() {
    state.customer_id = customerSel ? customerSel.value : '';
    state.stk_adj_dt = dateInp ? dateInp.value : '';
    state.stk_adj_type = getAdjType();
    state.item_type_id = itemTypeSel ? itemTypeSel.value : '';
    state.remarks = remarksTa ? remarksTa.value : '';
  }

  function loadSkuMetaForLine(idx, done) {
    var line = state.lines[idx];
    if (!line || !line.master_id || !state.customer_id || !metaUrl) {
      if (typeof done === 'function') done();
      return;
    }
    var kind = line.kind || state.masterMode;
    fetch(
      metaUrl +
        '?customer_id=' +
        encodeURIComponent(state.customer_id) +
        '&kind=' +
        encodeURIComponent(kind) +
        '&master_id=' +
        encodeURIComponent(line.master_id)
    )
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        line.sku_meta = {
          maintain_batch: data.maintain_batch || 'N',
          mfg_enabled: data.mfg_enabled !== false,
          exp_enabled: data.exp_enabled !== false,
        };
        if (typeof done === 'function') done();
      })
      .catch(function () {
        line.sku_meta = { maintain_batch: 'N', mfg_enabled: true, exp_enabled: true };
        if (typeof done === 'function') done();
      });
  }

  function fetchInvDefaultsForBatch(lineIdx, batchIdx) {
    if (!invDefaultsUrl) return;
    var line = state.lines[lineIdx];
    if (!line || !line.master_id || !state.customer_id) return;
    var b = line.batches && line.batches[batchIdx];
    if (!b) return;
    var bno = (b.batch_no || '').trim();
    if (!bno) return;
    var kind = line.kind || state.masterMode;
    fetch(
      invDefaultsUrl +
        '?customer_id=' +
        encodeURIComponent(state.customer_id) +
        '&kind=' +
        encodeURIComponent(kind) +
        '&master_id=' +
        encodeURIComponent(line.master_id) +
        '&batch_no=' +
        encodeURIComponent(bno)
    )
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        var Ln = state.lines[lineIdx];
        if (!Ln || !Ln.batches || !Ln.batches[batchIdx]) return;
        var bb = Ln.batches[batchIdx];
        var mfgEn = kind === 'P' || (Ln.sku_meta && Ln.sku_meta.mfg_enabled);
        var expEn = kind === 'P' || (Ln.sku_meta && Ln.sku_meta.exp_enabled);
        if (mfgEn && d.mfg_date && !bb.mfg_date) bb.mfg_date = d.mfg_date;
        if (expEn && d.exp_date && !bb.exp_date) bb.exp_date = d.exp_date;
        if (lineIdx === state.activeLine) renderBatches();
      })
      .catch(function () {});
  }

  function lineQty(line) {
    var t = 0;
    (line.batches || []).forEach(function (b) {
      var n = parseFloat(String(b.batch_qty || '').replace(/,/g, ''));
      if (!isNaN(n)) t += n;
    });
    return t;
  }

  function renderLineEmpty() {
    var has = state.lines && state.lines.length > 0;
    if (lineEmpty) lineEmpty.style.display = has ? 'none' : 'block';
    if (lineTbody) lineTbody.style.display = has ? '' : 'none';
  }

  function renderLines() {
    if (!lineTbody) return;
    /* Persist batch panel into state for the current active line before replacing line DOM. */
    syncBatchFromDom();
    if (typeof destroySearchableDropdownsIn === 'function') {
      destroySearchableDropdownsIn(lineTbody);
    }
    lineTbody.innerHTML = '';
    state.lines.forEach(function (line, idx) {
      var tr = document.createElement('tr');
      tr.className = 'stk-adj-line-row' + (idx === state.activeLine ? ' is-active' : '');
      tr.dataset.idx = String(idx);

      var td0 = document.createElement('td');
      var sel = document.createElement('select');
      sel.className = 'cu-select searchable-dropdown stk-adj-line-master';
      sel.dataset.idx = String(idx);
      var opt0 = document.createElement('option');
      opt0.value = '';
      opt0.textContent = '— Select —';
      sel.appendChild(opt0);
      state.masterRows.forEach(function (r) {
        var o = document.createElement('option');
        o.value = String(r.id);
        o.textContent = r.label;
        if (String(line.master_id) === String(r.id)) o.selected = true;
        sel.appendChild(o);
      });
      td0.appendChild(sel);

      var td1 = document.createElement('td');
      td1.className = 'num stk-adj-line-qty';
      td1.textContent = fmtQty(lineQty(line));

      var td2 = document.createElement('td');
      var rin = document.createElement('input');
      rin.type = 'text';
      rin.className = 'cu-input stk-adj-line-remarks';
      rin.maxLength = 20;
      rin.value = line.remarks || '';
      rin.dataset.idx = String(idx);
      td2.appendChild(rin);

      var td3 = document.createElement('td');
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn-icon-danger stk-adj-btn-rm-line';
      btn.textContent = '\u2715';
      btn.dataset.idx = String(idx);
      td3.appendChild(btn);

      tr.appendChild(td0);
      tr.appendChild(td1);
      tr.appendChild(td2);
      tr.appendChild(td3);
      lineTbody.appendChild(tr);
    });
    renderLineEmpty();
    wireLineHandlers();
    renderBatches();
    if (typeof initSearchableDropdowns === 'function') {
      initSearchableDropdowns(lineTbody);
    }
  }

  function fmtQty(n) {
    if (isNaN(n)) return '\u2014';
    return (Math.round(n * 1000) / 1000).toFixed(3);
  }

  function wireLineHandlers() {
    lineTbody.querySelectorAll('.stk-adj-line-master').forEach(function (sel) {
      sel.addEventListener('change', function () {
        var idx = parseInt(sel.dataset.idx, 10);
        var line = state.lines[idx];
        if (!line) return;
        line.master_id = sel.value ? parseInt(sel.value, 10) : '';
        var opt = sel.options[sel.selectedIndex];
        line.label = opt ? opt.textContent : '';
        line.kind = state.masterMode || line.kind;
        if (line.master_id) {
          loadSkuMetaForLine(idx, function () {
            renderLines();
          });
        } else {
          line.sku_meta = null;
          renderLines();
        }
      });
    });
    lineTbody.querySelectorAll('.stk-adj-line-remarks').forEach(function (inp) {
      inp.addEventListener('input', function () {
        var idx = parseInt(inp.dataset.idx, 10);
        if (state.lines[idx]) state.lines[idx].remarks = inp.value;
      });
    });
    lineTbody.querySelectorAll('.stk-adj-btn-rm-line').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var idx = parseInt(btn.dataset.idx, 10);
        state.lines.splice(idx, 1);
        if (state.activeLine >= state.lines.length) {
          state.activeLine = Math.max(0, state.lines.length - 1);
        }
        renderLines();
      });
    });
    lineTbody.querySelectorAll('tr.stk-adj-line-row').forEach(function (tr) {
      tr.addEventListener('click', function (e) {
        if (e.target.closest('.select2-container')) return;
        if (e.target.closest('button')) return;
        if (e.target.tagName === 'SELECT' || e.target.tagName === 'INPUT') return;
        var idx = parseInt(tr.dataset.idx, 10);
        state.activeLine = idx;
        renderLines();
      });
    });
  }

  function renderBatches() {
    var line = state.lines[state.activeLine];
    if (!batchPanel || !batchTbody) return;
    if (!line) {
      batchPanel.style.display = 'none';
      return;
    }
    batchPanel.style.display = 'block';
    batchTitle.textContent = line.label ? ' \u2014 ' + line.label : '';

    if (!line.batches || !Array.isArray(line.batches) || line.batches.length === 0) {
      line.batches = [{ batch_no: '', mfg_date: '', exp_date: '', batch_qty: '' }];
    }

    batchTbody.innerHTML = '';
    (line.batches || []).forEach(function (b, j) {
      var tr = document.createElement('tr');
      tr.dataset.bidx = String(j);

      function makeInput(type, val, cls) {
        var inp = document.createElement('input');
        inp.type = type;
        inp.className = 'cu-input ' + cls;
        inp.value = val != null ? val : '';
        inp.dataset.line = String(state.activeLine);
        inp.dataset.bidx = String(j);
        return inp;
      }

      function tdWithInput(inp) {
        var td = document.createElement('td');
        td.appendChild(inp);
        return td;
      }

      var batchInp = makeInput('text', b.batch_no, 'stk-adj-b-batch');
      var mfgInp = makeInput('date', b.mfg_date || '', 'stk-adj-b-mfg');
      var expInp = makeInput('date', b.exp_date || '', 'stk-adj-b-exp');
      var kind = line.kind || state.masterMode;
      var mfgEn = kind === 'P' || (line.sku_meta && line.sku_meta.mfg_enabled);
      var expEn = kind === 'P' || (line.sku_meta && line.sku_meta.exp_enabled);
      if (!mfgEn) {
        mfgInp.readOnly = true;
        mfgInp.setAttribute('title', 'Manufacturing date not used for this item (master).');
        mfgInp.classList.add('stk-adj-date-locked');
      }
      if (!expEn) {
        expInp.readOnly = true;
        expInp.setAttribute('title', 'Expiry date not used for this item (master).');
        expInp.classList.add('stk-adj-date-locked');
      }

      tr.appendChild(tdWithInput(batchInp));
      tr.appendChild(tdWithInput(mfgInp));
      tr.appendChild(tdWithInput(expInp));

      var tdq = document.createElement('td');
      tdq.className = 'num';
      var inq = makeInput('text', b.batch_qty != null ? String(b.batch_qty) : '', 'stk-adj-b-qty');
      tdq.appendChild(inq);
      tr.appendChild(tdq);

      var tdx = document.createElement('td');
      var bx = document.createElement('button');
      bx.type = 'button';
      bx.className = 'btn-icon-danger stk-adj-btn-rm-batch';
      bx.textContent = '\u2715';
      bx.dataset.line = String(state.activeLine);
      bx.dataset.bidx = String(j);
      tdx.appendChild(bx);
      tr.appendChild(tdx);

      batchTbody.appendChild(tr);

      if (invDefaultsUrl) {
        batchInp.addEventListener('blur', function (ev) {
          var el = ev.target;
          var li = parseInt(el.dataset.line, 10);
          var bi = parseInt(el.dataset.bidx, 10);
          if (!isNaN(li) && !isNaN(bi)) fetchInvDefaultsForBatch(li, bi);
        });
      }
    });

    batchTbody.querySelectorAll('.stk-adj-b-batch, .stk-adj-b-mfg, .stk-adj-b-exp, .stk-adj-b-qty').forEach(function (inp) {
      inp.addEventListener('change', syncBatchFromDom);
      inp.addEventListener('input', syncBatchFromDom);
    });
    batchTbody.querySelectorAll('.stk-adj-btn-rm-batch').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var li = parseInt(btn.dataset.line, 10);
        var bi = parseInt(btn.dataset.bidx, 10);
        var L = state.lines[li];
        if (!L || !L.batches) return;
        L.batches.splice(bi, 1);
        if (!L.batches.length) {
          L.batches.push({ batch_no: '', mfg_date: '', exp_date: '', batch_qty: '' });
        }
        renderLines();
      });
    });
  }

  function updateActiveLineQtyDisplay() {
    var row = lineTbody.querySelector(
      'tr.stk-adj-line-row[data-idx="' + state.activeLine + '"] td.stk-adj-line-qty'
    );
    var line = state.lines[state.activeLine];
    if (row && line) row.textContent = fmtQty(lineQty(line));
  }

  function syncBatchFromDom() {
    var line = state.lines[state.activeLine];
    if (!line || !batchTbody) return;
    if (!line.batches || !Array.isArray(line.batches)) {
      line.batches = [];
    }
    if (line.batches.length === 0) {
      line.batches.push({ batch_no: '', mfg_date: '', exp_date: '', batch_qty: '' });
    }
    var rows = batchTbody.querySelectorAll('tr');
    rows.forEach(function (tr, j) {
      var b = line.batches[j];
      if (!b) return;
      var bn = tr.querySelector('.stk-adj-b-batch');
      var mfg = tr.querySelector('.stk-adj-b-mfg');
      var exp = tr.querySelector('.stk-adj-b-exp');
      var q = tr.querySelector('.stk-adj-b-qty');
      b.batch_no = bn ? bn.value : '';
      b.mfg_date = mfg && mfg.value ? mfg.value : '';
      b.exp_date = exp && exp.value ? exp.value : '';
      b.batch_qty = q ? q.value : '';
    });
    updateActiveLineQtyDisplay();
  }

  function loadMasters(done) {
    var cid = customerSel ? customerSel.value : '';
    var it = itemTypeSel ? itemTypeSel.value : '';
    if (!cid || !it) {
      state.masterRows = [];
      state.masterMode = '';
      if (modeHint) modeHint.textContent = '';
      if (typeof done === 'function') done();
      return;
    }
    fetch(
      ajaxUrl +
        '?customer_id=' +
        encodeURIComponent(cid) +
        '&item_type_id=' +
        encodeURIComponent(it)
    )
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        state.masterMode = data.mode || '';
        state.masterRows = data.rows || [];
        if (modeHint) {
          modeHint.textContent =
            state.masterMode === 'P'
              ? 'Product mode (customer products for this item type).'
              : state.masterMode === 'I'
                ? 'Item mode (items for this item type).'
                : 'No masters for this combination.';
        }
        if (typeof done === 'function') done();
      })
      .catch(function () {
        state.masterRows = [];
        state.masterMode = '';
        if (modeHint) modeHint.textContent = 'Could not load masters.';
        if (typeof done === 'function') done();
      });
  }

  function clearLinesIfContextChanged(done) {
    state.lines = [];
    state.activeLine = 0;
    loadMasters(function () {
      renderLines();
      if (typeof done === 'function') done();
    });
  }

  var btnAddLine = document.getElementById('stkAdjBtnAddLine');
  if (btnAddLine) {
    btnAddLine.addEventListener('click', function () {
      readHeaderFromDom();
      if (!state.customer_id || !state.item_type_id) {
        window.alert('Select customer and item type first.');
        return;
      }
      if (!state.masterMode) {
        window.alert('No product or item list for this combination.');
        return;
      }
      state.lines.push({
        kind: state.masterMode,
        master_id: '',
        label: '',
        remarks: '',
        sku_meta: null,
        batches: [{ batch_no: '', mfg_date: '', exp_date: '', batch_qty: '' }],
      });
      state.activeLine = state.lines.length - 1;
      renderLines();
    });
  }

  var btnAddBatch = document.getElementById('stkAdjBtnAddBatch');
  if (btnAddBatch) {
    btnAddBatch.addEventListener('click', function () {
      syncBatchFromDom();
      var line = state.lines[state.activeLine];
      if (!line) return;
      line.batches = line.batches || [];
      line.batches.push({ batch_no: '', mfg_date: '', exp_date: '', batch_qty: '' });
      renderLines();
    });
  }

  if (customerSel) {
    customerSel.addEventListener('change', function () {
      if (ignoreHeaderChange) return;
      readHeaderFromDom();
      clearLinesIfContextChanged();
    });
  }
  if (itemTypeSel) {
    itemTypeSel.addEventListener('change', function () {
      if (ignoreHeaderChange) return;
      readHeaderFromDom();
      clearLinesIfContextChanged();
    });
  }
  typeRadios.forEach(function (r) {
    r.addEventListener('change', function () {
      state.stk_adj_type = getAdjType();
    });
  });

  form.addEventListener(
    'submit',
    function () {
      readHeaderFromDom();
      syncBatchFromDom();
      var payload = {
        stk_adj_id: state.stk_adj_id,
        customer_id: state.customer_id ? parseInt(state.customer_id, 10) : null,
        stk_adj_dt: state.stk_adj_dt,
        stk_adj_type: state.stk_adj_type,
        item_type_id: state.item_type_id ? parseInt(state.item_type_id, 10) : null,
        remarks: state.remarks,
        lines: state.lines.map(function (ln) {
          return {
            kind: ln.kind,
            master_id: ln.master_id === '' ? null : ln.master_id,
            remarks: ln.remarks || '',
            batches: (ln.batches || []).map(function (b) {
              return {
                batch_no: b.batch_no || '',
                mfg_date: b.mfg_date || '',
                exp_date: b.exp_date || '',
                batch_qty: b.batch_qty === '' ? null : b.batch_qty,
              };
            }),
          };
        }),
      };
      docField.value = JSON.stringify(payload);
    },
    true
  );

  syncHeaderDom();
  loadMasters(function () {
    state.lines.forEach(function (ln) {
      if (!ln.kind && state.masterMode) ln.kind = state.masterMode;
    });
    var todo = [];
    state.lines.forEach(function (ln, i) {
      if (ln.master_id) todo.push(i);
    });
    if (todo.length === 0) {
      renderLines();
      return;
    }
    var left = todo.length;
    todo.forEach(function (i) {
      loadSkuMetaForLine(i, function () {
        left--;
        if (left <= 0) renderLines();
      });
    });
  });
}

window.initPage_stock_adj = initPage_stock_adj;
