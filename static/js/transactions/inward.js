/**
 * Inward (GRN) — two-step wizard; lines_json with batch blocks (collapsible).
 */
function initPage_inward() {
  var form = document.getElementById('inwForm');
  if (!form) return;

  var step1 = document.getElementById('inwStep1');
  var step2 = document.getElementById('inwStep2');
  var lineList = document.getElementById('inwLineList');
  var lineEmpty = document.getElementById('inwLineEmpty');
  var linesHidden = document.getElementById('inwLinesJson');
  var grnCat = document.getElementById('inwGrnCategory');
  var grnNoInput = document.getElementById('inwGrnNo');
  var registerNoInput = document.getElementById('inwRegisterNo');
  var btnAdd = document.getElementById('btnInwAddLine');
  var btnNext = document.getElementById('btnInwNext');
  var btnBack = document.getElementById('btnInwBack');
  var btnSave = document.getElementById('btnInwSave');
  var errEl = document.getElementById('err-lines_json');
  var errElStep1 = document.getElementById('err-lines_json_step1');
  var headerIcon = document.getElementById('inwHeaderIcon');
  var headerTitle = document.getElementById('inwHeaderTitle');
  var headerSub = document.getElementById('inwHeaderSub');
  var dot1 = document.getElementById('inwDot1');
  var dot2 = document.getElementById('inwDot2');
  var docInput = document.getElementById('inwHeaderDocInput');
  var docBtn = document.getElementById('inwDocUploadBtn');
  var docHint = document.getElementById('inwDocHint');
  var previewShell = document.getElementById('inwDocPreviewShell');
  var docPreviewImg = document.getElementById('inwDocPreviewImg');
  var docPreviewPdf = document.getElementById('inwDocPreviewPdf');
  var DOC_HINT_DEFAULT = 'PDF or image — max 15 MB';
  var docBlobUrl = null;

  var pageData = {};
  try {
    var pd = document.getElementById('inwPageData');
    if (pd) pageData = JSON.parse(pd.textContent || '{}');
  } catch (e) { /* ignore */ }

  var isEdit = !!pageData.isEdit;

  var bindSerialLock = typeof prefixedSerialNoBindLock === 'function' ? prefixedSerialNoBindLock : function () {};
  var normSerial = typeof prefixedSerialNoNormalize === 'function' ? prefixedSerialNoNormalize : function () {};

  // Register no: keep "R-" and allow digits only after it.
  bindSerialLock(registerNoInput, function () { return 'R-'; });

  // GRN no: prefix depends on GRN type dropdown.
  bindSerialLock(grnNoInput, function () {
    var cat = (grnCat && grnCat.value) ? String(grnCat.value).trim().toUpperCase() : '';
    if (cat === 'RM' || cat === 'PM') return cat + '-';
    // If category not selected yet, don't enforce a prefix.
    return '';
  });

  var state = {
    lines: [],
    itemOptions: [],
  };

  function cacheKey(id) {
    if (id === null || id === undefined || id === '') return '';
    return String(id);
  }

  function readJsonScript(id) {
    var el = document.getElementById(id);
    if (!el) return [];
    try {
      return JSON.parse(el.textContent || '[]');
    } catch (e) {
      return [];
    }
  }

  function readJsonObject(id) {
    var el = document.getElementById(id);
    if (!el) return {};
    try {
      var o = JSON.parse(el.textContent || '{}');
      return o && typeof o === 'object' && !Array.isArray(o) ? o : {};
    } catch (e) {
      return {};
    }
  }

  var products = readJsonScript('inwProductsData');
  var ajaxUrls = readJsonObject('inwAjaxUrls');
  var URL_ITEMS = ajaxUrls.items || '/transactions/ajax/inward-items/';
  var URL_ITEM_META = ajaxUrls.itemMeta || '/transactions/ajax/inward-item-meta/';
  var URL_NEXT_NUMBERS = ajaxUrls.nextNumbers || '';
  var URL_SUGGEST_GRN = ajaxUrls.suggestGrn || '/api/suggest-grn/';
  var fetchOpts = { credentials: 'same-origin', headers: { Accept: 'application/json' } };

  function formatSerialSuffix(n) {
    return typeof prefixedSerialNoFormatSuffix === 'function'
      ? prefixedSerialNoFormatSuffix(n)
      : (function () {
        var v = parseInt(n, 10);
        if (isNaN(v)) return '';
        if (v < 100000) return String(v).padStart(5, '0');
        return String(v);
      })();
  }

  function applySuggestedGrn(force) {
    if (isEdit || !grnNoInput || !grnCat) return;
    if (!force && (grnNoInput.value || '').trim()) return;
    var cat = (grnCat.value || '').trim().toUpperCase();
    if (cat !== 'RM' && cat !== 'PM') return;
    var inwDt = document.getElementById('inwInwardDt');
    var inwardDtVal = inwDt ? (inwDt.value || '').trim() : '';

    // Prefer server-suggested GRN (FY scoped). Fall back to legacy grn_seq if needed.
    if (URL_SUGGEST_GRN) {
      var url = URL_SUGGEST_GRN +
        '?grn_category_id=' + encodeURIComponent(cat) +
        (inwardDtVal ? ('&inward_dt=' + encodeURIComponent(inwardDtVal)) : '');
      fetch(url, fetchOpts)
        .then(function (r) { if (!r.ok) throw new Error('bad'); return r.json(); })
        .then(function (d) {
          if (d && d.grn_no) grnNoInput.value = d.grn_no;
          pageData.numberSuggest = pageData.numberSuggest || {};
          if (d && d.grn_seq != null) pageData.numberSuggest.grn_seq = d.grn_seq;
          if (d && d.working_year) pageData.numberSuggest.working_year = d.working_year;
        })
        .catch(function () {
          var ns = pageData.numberSuggest;
          if (!ns || ns.grn_seq == null || ns.grn_seq === '') return;
          var n = parseInt(ns.grn_seq, 10);
          if (isNaN(n)) return;
          grnNoInput.value = cat + '-' + formatSerialSuffix(n);
          normSerial(grnNoInput, cat + '-');
        });
      return;
    }

    var ns = pageData.numberSuggest;
    if (!ns || ns.grn_seq == null || ns.grn_seq === '') return;
    var n = parseInt(ns.grn_seq, 10);
    if (isNaN(n)) return;
    grnNoInput.value = cat + '-' + formatSerialSuffix(n);
    normSerial(grnNoInput, cat + '-');
  }

  /** Ensures pageData.numberSuggest has grn_seq (e.g. after template JSON issues). */
  function hydrateNumberSuggestIfNeeded() {
    var ns = pageData.numberSuggest;
    if (ns && ns.grn_seq != null && ns.grn_seq !== '') {
      return Promise.resolve();
    }
    if (!URL_NEXT_NUMBERS) return Promise.resolve();
    return fetch(URL_NEXT_NUMBERS, fetchOpts)
      .then(function (r) {
        if (!r.ok) throw new Error('bad');
        return r.json();
      })
      .then(function (d) {
        pageData.numberSuggest = pageData.numberSuggest || {};
        if (d.grn_seq != null) pageData.numberSuggest.grn_seq = d.grn_seq;
        if (d.register_no) pageData.numberSuggest.register_no = d.register_no;
      })
      .catch(function () { /* keep existing pageData */ });
  }

  function escHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function setLinesErr(msg) {
    if (errEl) errEl.textContent = msg || '';
    if (errElStep1) errElStep1.textContent = msg || '';
  }

  function hasAtLeastOneItemSelected() {
    for (var i = 0; i < state.lines.length; i++) {
      var id = state.lines[i] && state.lines[i].item_id ? String(state.lines[i].item_id) : '';
      if (id && id !== '0') return true;
    }
    return false;
  }

  function updateSaveState() {
    if (!btnSave) return;
    var ok = hasAtLeastOneItemSelected();
    btnSave.setAttribute('aria-disabled', ok ? 'false' : 'true');
  }

  function setHeader(step) {
    var H = {
      1: {
        icon: isEdit ? 'bi-pencil-fill' : 'bi-box-arrow-in-down',
        title: isEdit ? 'Edit inward' : 'New inward',
        sub: 'Inward details and transport',
      },
      2: {
        icon: 'bi-grid-3x3-gap',
        title: 'Items',
        sub: 'Items and batches',
      },
    };
    var h = H[step] || H[1];
    if (headerIcon) headerIcon.className = 'bi ' + h.icon;
    if (headerTitle) headerTitle.textContent = h.title;
    if (headerSub) headerSub.textContent = h.sub;
    if (dot1) dot1.className = 'step-dot' + (step === 1 ? ' active' : ' done');
    if (dot2) dot2.className = 'step-dot' + (step === 2 ? ' active' : '');
  }

  function setStep(step) {
    if (step1) {
      step1.style.display = step === 1 ? 'flex' : 'none';
      step1.style.flexDirection = 'column';
    }
    if (step2) {
      step2.style.display = step === 2 ? 'flex' : 'none';
      step2.style.flexDirection = 'column';
    }
    setHeader(step);
  }

  function productOptions(selected) {
    var o = '<option value=""></option>';
    products.forEach(function (p) {
      o += '<option value="' + p.prod_id + '"' +
        (String(p.prod_id) === String(selected) ? ' selected' : '') + '>' +
        escHtml(p.prod_name) + '</option>';
    });
    return o;
  }

  function itemOptionsHtml(selected) {
    var o = '<option value=""></option>';
    state.itemOptions.forEach(function (i) {
      o += '<option value="' + i.item_id + '"' +
        (String(i.item_id) === String(selected) ? ' selected' : '') + '>' +
        escHtml(i.item_name) + '</option>';
    });
    return o;
  }

  function fetchItemsForGrn() {
    var cat = grnCat && grnCat.value ? grnCat.value : '';
    if (!cat) {
      state.itemOptions = [];
      return Promise.resolve();
    }
    return fetch(URL_ITEMS + '?grn_cat=' + encodeURIComponent(cat), fetchOpts)
      .then(function (r) {
        if (!r.ok) return { items: [] };
        return r.json();
      })
      .then(function (d) {
        state.itemOptions = d.items || [];
      })
      .catch(function () { state.itemOptions = []; });
  }

  function fetchItemMeta(itemId) {
    return fetch(URL_ITEM_META + '?item_id=' + encodeURIComponent(itemId), fetchOpts)
      .then(function (r) {
        if (!r.ok) return { error: 'bad_response', status: r.status };
        return r.json();
      })
      .catch(function () {
        return { error: 'network' };
      });
  }

  function updateEmptyVisibility() {
    if (lineEmpty) lineEmpty.style.display = state.lines.length ? 'none' : 'block';
  }

  function serialize() {
    var out = [];
    state.lines.forEach(function (line) {
      var row = {
        item_id: line.item_id ? parseInt(line.item_id, 10) : null,
        pkg_style: line.pkg_style,
        qty: line.qty,
        rate: line.rate,
        batches: [],
      };
      if (line.maintain_batch && line.batches && line.batches.length) {
        line.batches.forEach(function (b) {
          row.batches.push({
            batch_no: b.batch_no,
            arn_no: b.arn_no,
            pack_style: b.pack_style,
            mfg_dt: line.mfg_date_enabled ? b.mfg_dt : '',
            exp_dt: line.exp_date_enabled ? b.exp_dt : '',
            batch_qty: b.batch_qty,
            prod_id: b.prod_id,
          });
        });
      }
      out.push(row);
    });
    if (linesHidden) linesHidden.value = JSON.stringify(out);
    updateSaveState();
  }

  function renderBatchRow(lineIdx, bidx, b, line) {
    var wrap = document.createElement('div');
    wrap.className = 'inw-batch-row';
    wrap.dataset.li = String(lineIdx);
    wrap.dataset.bi = String(bidx);

    var mfgRO = !line.mfg_date_enabled;
    var expRO = !line.exp_date_enabled;

    wrap.innerHTML =
      '<div class="inw-br-field inw-br-batch-arn">' +
        '<div class="inw-br-sub">' +
          '<label>Batch no. <span class="req">*</span></label>' +
          '<input type="text" class="cu-input inw-b-batchno" value="' + escHtml(b.batch_no) + '">' +
        '</div>' +
        '<div class="inw-br-sub">' +
          '<label>ARN no.</label>' +
          '<input type="text" class="cu-input inw-b-arn" maxlength="15" value="' + escHtml(b.arn_no) + '" placeholder="Optional">' +
        '</div>' +
      '</div>' +
      '<div class="inw-br-field">' +
        '<label>Manufacturing date</label>' +
        '<input type="date" class="cu-input inw-b-mfg" value="' + escHtml(b.mfg_dt) + '"' +
        (mfgRO ? ' readonly tabindex="-1"' : '') + '>' +
      '</div>' +
      '<div class="inw-br-field">' +
        '<label>Expiry date</label>' +
        '<input type="date" class="cu-input inw-b-exp" value="' + escHtml(b.exp_dt) + '"' +
        (expRO ? ' readonly tabindex="-1"' : '') + '>' +
      '</div>' +
      '<div class="inw-br-field inw-br-pack">' +
        '<label>Packing style <span class="req">*</span></label>' +
        '<input type="text" maxlength="30" class="cu-input inw-b-packstyle" value="' + escHtml(b.pack_style) + '">' +
      '</div>' +
      '<div class="inw-br-field inw-br-qty">' +
        '<label>Qty <span class="req">*</span></label>' +
        '<input type="number" class="cu-input inw-b-qty" min="0.001" step="0.001" value="' +
        escHtml(b.batch_qty) + '">' +
      '</div>' +
      '<div class="inw-br-field inw-br-prod">' +
        '<label>Product</label>' +
        '<select class="cu-select searchable-dropdown inw-b-prod">' + productOptions(b.prod_id) + '</select>' +
      '</div>' +
      '<div class="inw-br-del">' +
        '<button type="button" class="btn-del-row inw-remove-batch" title="Remove">' +
        '<i class="bi bi-x"></i></button></div>';

    var batchno = wrap.querySelector('.inw-b-batchno');
    var arn = wrap.querySelector('.inw-b-arn');
    var mfg = wrap.querySelector('.inw-b-mfg');
    var exp = wrap.querySelector('.inw-b-exp');
    var packstyle = wrap.querySelector('.inw-b-packstyle');
    var qty = wrap.querySelector('.inw-b-qty');
    var prod = wrap.querySelector('.inw-b-prod');

    [batchno, arn, mfg, exp, packstyle, qty].forEach(function (inp) {
      if (!inp) return;
      inp.addEventListener('change', function () {
        patchBatch(lineIdx, bidx, inp.className, inp.value);
      });
      inp.addEventListener('input', function () {
        patchBatch(lineIdx, bidx, inp.className, inp.value);
      });
    });
    if (prod) {
      prod.addEventListener('change', function () {
        patchBatch(lineIdx, bidx, prod.className, prod.value);
      });
    }

    wrap.querySelector('.inw-remove-batch').addEventListener('click', function () {
      state.lines[lineIdx].batches.splice(bidx, 1);
      if (!state.lines[lineIdx].batches.length) state.lines[lineIdx].batchExpanded = false;
      render();
      serialize();
    });

    if (mfgRO && mfg) {
      mfg.classList.add('inw-input-disabled');
    }
    if (expRO && exp) {
      exp.classList.add('inw-input-disabled');
    }

    return wrap;
  }

  function patchBatch(li, bi, cls, val) {
    var line = state.lines[parseInt(li, 10)];
    if (!line || !line.batches) return;
    var row = line.batches[parseInt(bi, 10)];
    if (!row) return;
    if (cls.indexOf('inw-b-batchno') >= 0) row.batch_no = val;
    if (cls.indexOf('inw-b-arn') >= 0) row.arn_no = val;
    if (cls.indexOf('inw-b-packstyle') >= 0) row.pack_style = val;
    if (cls.indexOf('inw-b-mfg') >= 0 && line.mfg_date_enabled) row.mfg_dt = val;
    if (cls.indexOf('inw-b-exp') >= 0 && line.exp_date_enabled) row.exp_dt = val;
    if (cls.indexOf('inw-b-qty') >= 0) row.batch_qty = val;
    if (cls.indexOf('inw-b-prod') >= 0) row.prod_id = val;
    serialize();
  }

  function render() {
    if (!lineList) return;
    if (typeof destroySearchableDropdownsIn === 'function') destroySearchableDropdownsIn(lineList);
    lineList.innerHTML = '';
    state.lines.forEach(function (line, idx) {
      var card = document.createElement('div');
      card.className = 'inw-line-card';
      card.dataset.lineIdx = String(idx);

      var title = document.createElement('div');
      title.className = 'inw-line-title';
      title.textContent = 'Item ' + (idx + 1);
      card.appendChild(title);

      var main = document.createElement('div');
      main.className = 'inw-line-main';
      main.innerHTML =
        '<div class="inw-cell inw-cell-item">' +
          '<label>Item <span class="req">*</span></label>' +
          '<select class="cu-select searchable-dropdown inw-item-select" data-idx="' + idx + '">' +
          itemOptionsHtml(line.item_id) + '</select></div>' +
          '<div class="inw-cell"><label>Packing Style <span  </span></label>' +
          '<input type="text" maxlength="30" " class="cu-input inw-pkg" value="' + 
          escHtml(line.pkg_style) + '"></div>' +
          '<div class="inw-cell"><label>Quantity <span class="req">*</span></label>' +
          '<input type="number" class="cu-input inw-qty" min="0.001" max="99999999.999" step="0.001" data-idx="' + idx + '" value="' +
          escHtml(line.qty) + '"></div>' +
        '<div class="inw-cell"><label>UOM</label>' +
          '<input type="text" class="cu-input" readonly value="' + escHtml(line.uom_name) + '"></div>' +
        '<div class="inw-cell"><label>Rate </label>' +
          '<input type="number" class="cu-input inw-rate" min="0" max="99999999.999" step="0.01" data-idx="' + idx + '" value="' +
          escHtml(line.rate) + '"></div>' +
        '<div class="inw-cell inw-cell-del">' +
          '<button type="button" class="btn-del-row inw-remove-line" data-idx="' + idx + '" title="Remove">' +
          '<i class="bi bi-x"></i></button></div>';

      card.appendChild(main);

      if (line.maintain_batch) {
        var n = (line.batches && line.batches.length) ? line.batches.length : 0;
        var bar = document.createElement('button');
        bar.type = 'button';
        bar.className = 'inw-batch-toggle' + (line.batchExpanded ? ' is-open' : '');
        bar.setAttribute('aria-expanded', line.batchExpanded ? 'true' : 'false');
        bar.dataset.idx = String(idx);
        bar.innerHTML =
          '<span class="inw-batch-toggle-icon"><i class="bi bi-chevron-down"></i></span>' +
          '<span class="inw-batch-toggle-text">Batches</span>' +
          (n ? '<span class="inw-batch-count">' + n + '</span>' : '');
        card.appendChild(bar);

        var panel = document.createElement('div');
        panel.className = 'inw-batch-panel';
        panel.style.display = line.batchExpanded ? 'block' : 'none';
        panel.dataset.idx = String(idx);

        var inner = document.createElement('div');
        inner.className = 'inw-batch-inner';
        (line.batches || []).forEach(function (b, bidx) {
          inner.appendChild(renderBatchRow(idx, bidx, b, line));
        });

        var addBtn = document.createElement('button');
        addBtn.type = 'button';
        addBtn.className = 'inw-add-batch';
        addBtn.dataset.idx = String(idx);
        addBtn.innerHTML = '<i class="bi bi-plus-lg"></i><span>Add batch</span>';

        panel.appendChild(inner);
        panel.appendChild(addBtn);
        card.appendChild(panel);

        bar.addEventListener('click', function () {
          var i = parseInt(bar.dataset.idx, 10);
          var ln = state.lines[i];
          if (!ln) return;
          ln.batchExpanded = !ln.batchExpanded;
          render();
          serialize();
        });

        addBtn.addEventListener('click', function () {
          var i = parseInt(addBtn.dataset.idx, 10);
          var ln = state.lines[i];
          if (!ln) return;
          if (!ln.batches) ln.batches = [];
          ln.batches.push({
            batch_no: '',
            arn_no: '',
            pack_style: '',
            mfg_dt: '',
            exp_dt: '',
            batch_qty: '',
            prod_id: '',
          });
          ln.batchExpanded = true;
          render();
          serialize();
        });
      }

      lineList.appendChild(card);

      var itemSel = card.querySelector('.inw-item-select');
      if (itemSel) {
        itemSel.addEventListener('change', function () {
          onItemChange(idx, itemSel.value);
        });
      }
      var pkg_StyleIn = card.querySelector('.inw-pkg');
      if (pkg_StyleIn) {
        pkg_StyleIn.addEventListener('input', function () {
          state.lines[idx].pkg_style = pkg_StyleIn.value;
          serialize();
        });
      }
      var qtyIn = card.querySelector('.inw-qty');
      if (qtyIn) {
        qtyIn.addEventListener('input', function () {
          state.lines[idx].qty = qtyIn.value;
          serialize();
        });
      }
      var rateIn = card.querySelector('.inw-rate');
      if (rateIn) {
        rateIn.addEventListener('input', function () {
          state.lines[idx].rate = rateIn.value;
          serialize();
        });
      }
      card.querySelectorAll('.inw-remove-line').forEach(function (btn) {
        btn.addEventListener('click', function () {
          state.lines.splice(parseInt(btn.dataset.idx, 10), 1);
          render();
          serialize();
        });
      });
    });
    if (typeof initSearchableDropdowns === 'function') initSearchableDropdowns(lineList);
    updateEmptyVisibility();
    serialize();
  }

  function onItemChange(idx, itemId) {
    var line = state.lines[idx];
    line.item_id = itemId;
    line.uom_name = '';
    line.rate = '';
    line.maintain_batch = false;
    line.mfg_date_enabled = false;
    line.exp_date_enabled = false;
    line.batches = [];
    line.batchExpanded = false;
    if (!itemId) {
      render();
      return;
    }
    fetchItemMeta(itemId).then(function (meta) {
      if (meta.error) {
        render();
        return;
      }
      line.uom_name = meta.uom_name || '';
      line.maintain_batch = !!meta.maintain_batch;
      line.mfg_date_enabled = !!meta.mfg_date_enabled;
      line.exp_date_enabled = !!meta.exp_date_enabled;
      if (meta.last_purchase_rate != null && meta.last_purchase_rate !== '') {
        line.rate = String(meta.last_purchase_rate);
      } else {
        line.rate = '0';
      }
      render();
    }).catch(function () { render(); });
  }

  function addLine() {
    setLinesErr('');
    if (!grnCat || !grnCat.value) {
      setLinesErr('Select GRN type first.');
      return;
    }
    state.lines.push({
      item_id: '',
      pkg_style: '',
      qty: '',
      rate: '',
      uom_name: '',
      maintain_batch: false,
      mfg_date_enabled: false,
      exp_date_enabled: false,
      batches: [],
      batchExpanded: false,
    });
    render();
  }

  function prepareLinesForSubmit(showErr) {
    setLinesErr('');
    serialize();
    var raw = (linesHidden && linesHidden.value) ? linesHidden.value.trim() : '';
    if (!raw || raw === '[]') {
      if (showErr) setLinesErr('Add at least one item.');
      return false;
    }
    try {
      var rows = JSON.parse(raw);
      if (!Array.isArray(rows) || !rows.length) {
        if (showErr) setLinesErr('Add at least one item.');
        return false;
      }
    } catch (e) {
      if (showErr) setLinesErr('Invalid item data.');
      return false;
    }
    return true;
  }

  function isThisFormHtmxRequest(e) {
    var elt = e && e.detail && e.detail.elt;
    if (!elt) return false;
    if (elt === form) return true;
    return typeof elt.closest === 'function' && elt.closest('form') === form;
  }

  window.goToInwItems = function () {
    setLinesErr('');
    if (!grnCat || !grnCat.value) {
      setLinesErr('Select GRN type first.');
      return;
    }
    fetchItemsForGrn().then(function () {
      setStep(2);
    });
  };

  window.goBackInwHeader = function () {
    setStep(1);
  };

  function extFromName(name) {
    if (!name) return '';
    var base = String(name).split('?')[0];
    var parts = base.split('.');
    return parts.length > 1 ? parts.pop().toLowerCase() : '';
  }

  var IMAGE_EXT = { jpg: 1, jpeg: 1, png: 1, gif: 1, webp: 1 };

  function revokeDocBlobUrl() {
    if (docBlobUrl) {
      try {
        URL.revokeObjectURL(docBlobUrl);
      } catch (e) { /* ignore */ }
      docBlobUrl = null;
    }
  }

  function hideDocPreviewLayers() {
    if (docPreviewImg) {
      docPreviewImg.src = '';
      docPreviewImg.classList.remove('is-visible');
    }
    if (docPreviewPdf) {
      docPreviewPdf.src = 'about:blank';
      docPreviewPdf.classList.remove('is-visible');
    }
    if (previewShell) previewShell.classList.remove('has-preview');
  }

  function applyDocPreviewFromUrl(url) {
    if (!url || !previewShell) return;
    revokeDocBlobUrl();
    hideDocPreviewLayers();
    var ext = extFromName(url);
    if (IMAGE_EXT[ext]) {
      docPreviewImg.src = url;
      docPreviewImg.classList.add('is-visible');
      previewShell.classList.add('has-preview');
    } else if (ext === 'pdf') {
      /* Avoid <iframe src="/media/..."> — SecurityMiddleware may send X-Frame-Options: DENY
         on media responses; blob URL loads in-frame without framing the HTTP response. */
      fetch(url, { credentials: 'same-origin', cache: 'no-store' })
        .then(function (r) {
          if (!r.ok) throw new Error('pdf fetch failed');
          return r.blob();
        })
        .then(function (blob) {
          var u = URL.createObjectURL(blob);
          docBlobUrl = u;
          if (!docPreviewPdf || !previewShell) return;
          docPreviewPdf.src = u;
          docPreviewPdf.classList.add('is-visible');
          previewShell.classList.add('has-preview');
        })
        .catch(function () {
          if (docHint) docHint.textContent = 'Could not load PDF preview — use “Open current file”.';
        });
    }
  }

  function applyDocPreviewFromFile(file) {
    if (!file || !previewShell) return;
    revokeDocBlobUrl();
    hideDocPreviewLayers();

    if (file.type && file.type.indexOf('image/') === 0) {
      var reader = new FileReader();
      reader.onload = function (e) {
        if (!docPreviewImg || !previewShell) return;
        docPreviewImg.src = e.target.result;
        docPreviewImg.classList.add('is-visible');
        previewShell.classList.add('has-preview');
      };
      reader.readAsDataURL(file);
      return;
    }

    if (file.type === 'application/pdf' || extFromName(file.name) === 'pdf') {
      var u = URL.createObjectURL(file);
      docBlobUrl = u;
      docPreviewPdf.src = u;
      docPreviewPdf.classList.add('is-visible');
      previewShell.classList.add('has-preview');
    }
  }

  if (docBtn && docInput) {
    docBtn.addEventListener('click', function () {
      docInput.click();
    });
  }
  if (docInput) {
    docInput.addEventListener('change', function () {
      var file = this.files && this.files[0];
      if (!file) return;
      if (file.size > 15 * 1024 * 1024) {
        window.alert('File must be 15 MB or smaller.');
        this.value = '';
        return;
      }
      if (docHint) docHint.textContent = file.name;
      applyDocPreviewFromFile(file);
    });
  }

  if (previewShell && previewShell.dataset.existingSrc) {
    applyDocPreviewFromUrl(previewShell.dataset.existingSrc);
  }

  if (btnAdd) btnAdd.addEventListener('click', addLine);
  if (btnNext) btnNext.addEventListener('click', function () { window.goToInwItems(); });
  if (btnBack) btnBack.addEventListener('click', function () { window.goBackInwHeader(); });

  // Clear button — same pattern as all master forms (resetForm / resetBomForm etc.).
  // Pure client-side reset: no navigation, no hx-get.
  window.resetInwardForm = function () {
    if (typeof clearMasterFormValidationUI === 'function') clearMasterFormValidationUI(form);

    // form.reset() in edit mode restores fields to server-rendered initial
    // values (the edit record's data baked into value= attributes), NOT blank.
    // Manually wipe every visible field instead.
    form.querySelectorAll('input, select, textarea').forEach(function (el) {
      if (el.type === 'hidden') return;
      if (el.type === 'file') {
        el.value = '';
        revokeDocBlobUrl();
        hideDocPreviewLayers();
        return;
      }
      if (el.tagName === 'SELECT') {
        el.selectedIndex = 0;
      } else if (el.type === 'checkbox' || el.type === 'radio') {
        el.checked = false;
      } else {
        el.value = '';
      }
    });

    // Default inward date to today (mirrors the server-side new-form default).
    var inwDt = document.getElementById('inwInwardDt');
    if (inwDt) {
      var today = new Date();
      inwDt.value = today.getFullYear() + '-' +
        String(today.getMonth() + 1).padStart(2, '0') + '-' +
        String(today.getDate()).padStart(2, '0');
    }

    // Remove the edit_pk hidden input so a subsequent submit creates a new record.
    var editPkInput = form.querySelector('input[name="edit_pk"]');
    if (editPkInput) editPkInput.remove();

    // Strip ?edit_pk= from the form action so POST goes to the create URL.
    form.action = form.action.split('?')[0];

    // Reset wizard state.
    state.lines    = [];
    if (linesHidden) linesHidden.value = '';
    setLinesErr('');
    if (docHint) docHint.textContent = DOC_HINT_DEFAULT;
    revokeDocBlobUrl();
    hideDocPreviewLayers();
    if (previewShell) delete previewShell.dataset.existingSrc;

    // Re-render empty lines panel and land on step 1 with "New inward" header.
    render();
    isEdit = false;
    pageData.numberSuggest = pageData.numberSuggest || {};
    if (URL_NEXT_NUMBERS) {
      fetch(URL_NEXT_NUMBERS, fetchOpts)
        .then(function (r) {
          if (!r.ok) throw new Error('bad');
          return r.json();
        })
        .then(function (d) {
          if (d && d.register_no && registerNoInput) registerNoInput.value = d.register_no;
          if (d && d.grn_seq != null) pageData.numberSuggest.grn_seq = d.grn_seq;
          applySuggestedGrn(true);
        })
        .catch(function () {
          if (pageData.numberSuggest && pageData.numberSuggest.register_no && registerNoInput) {
            registerNoInput.value = pageData.numberSuggest.register_no;
          }
          applySuggestedGrn(true);
        });
    } else if (pageData.numberSuggest) {
      if (pageData.numberSuggest.register_no && registerNoInput) {
        registerNoInput.value = pageData.numberSuggest.register_no;
      }
      applySuggestedGrn(true);
    }
    setStep(1);
  };

  if (grnCat) {
    function onGrnCategoryChanged() {
      state.lines = [];
      setLinesErr('');
      hydrateNumberSuggestIfNeeded()
        .then(function () {
          applySuggestedGrn(true);
          return fetchItemsForGrn();
        })
        .then(function () {
          applySuggestedGrn(true);
          render();
        });
    }

    // Native <select> change (works without Select2).
    grnCat.addEventListener('change', onGrnCategoryChanged);

    // Select2 sometimes doesn't reliably bubble a plain 'change' in all flows
    // (keyboard selection, clear button, programmatic value set). Listen to
    // its own events as well when available.
    if (window.jQuery && window.jQuery.fn && typeof window.jQuery.fn.select2 === 'function') {
      try {
        window.jQuery(grnCat)
          .on('select2:select', onGrnCategoryChanged)
          .on('select2:clear', onGrnCategoryChanged);
      } catch (e) { /* ignore */ }
    }
  }

  // When inward date changes, refresh suggested GRN to match the FY.
  var inwDtInput = document.getElementById('inwInwardDt');
  if (inwDtInput && !isEdit) {
    inwDtInput.addEventListener('change', function () {
      applySuggestedGrn(true);
    });
  }

  form.addEventListener('submit', function (e) {
    if (!prepareLinesForSubmit(true)) e.preventDefault();
  });

  if (btnSave) {
    btnSave.addEventListener('click', function (e) {
      // Button stays clickable for UX, even when "disabled".
      if (btnSave.getAttribute('aria-disabled') === 'true' || !hasAtLeastOneItemSelected()) {
        e.preventDefault();
        setLinesErr('Add at least one item.');
      }
    });
  }

  document.body.addEventListener('htmx:configRequest', function (e) {
    if (!isThisFormHtmxRequest(e)) return;
    if (!prepareLinesForSubmit(true)) e.preventDefault();
  });

  document.body.addEventListener('htmx:beforeRequest', function (e) {
    if (!isThisFormHtmxRequest(e)) return;
    if (!prepareLinesForSubmit(true)) e.preventDefault();
  });

  function normalizeBatchFromJson(b) {
    return {
      batch_no: b.batch_no != null ? String(b.batch_no) : '',
      arn_no: b.arn_no != null ? String(b.arn_no) : '',
      pack_style: b.pack_style != null ? String(b.pack_style) : '',
      mfg_dt: b.mfg_dt != null ? String(b.mfg_dt) : '',
      exp_dt: b.exp_dt != null ? String(b.exp_dt) : '',
      batch_qty: b.batch_qty != null ? String(b.batch_qty) : '',
      prod_id: b.prod_id != null ? String(b.prod_id) : '',
    };
  }

  function hydrateFromHidden() {
    var raw = (linesHidden && linesHidden.value) ? linesHidden.value.trim() : '';
    if (!raw || raw === '[]') return Promise.resolve();
    var parsed;
    try {
      parsed = JSON.parse(raw);
    } catch (e) {
      return Promise.resolve();
    }
    if (!Array.isArray(parsed) || !parsed.length) return Promise.resolve();

    return fetchItemsForGrn().then(function () {
      state.lines = [];
      parsed.forEach(function (row) {
        var batches = Array.isArray(row.batches)
          ? row.batches.map(normalizeBatchFromJson)
          : [];
        state.lines.push({
          item_id: row.item_id || '',
          pkg_style: row.pkg_style != null ? String(row.pkg_style) : '',
          qty: row.qty != null ? String(row.qty) : '',
          rate: row.rate != null && row.rate !== '' ? String(row.rate) : '0',
          uom_name: '',
          maintain_batch: false,
          mfg_date_enabled: false,
          exp_date_enabled: false,
          batches: batches,
          batchExpanded: batches.length > 0,
        });
      });
      var tasks = state.lines.map(function (line) {
        if (!line.item_id) return Promise.resolve();
        return fetchItemMeta(line.item_id).then(function (meta) {
          if (meta.error) return;
          line.uom_name = meta.uom_name || '';
          line.maintain_batch = !!meta.maintain_batch;
          line.mfg_date_enabled = !!meta.mfg_date_enabled;
          line.exp_date_enabled = !!meta.exp_date_enabled;
        });
      });
      return Promise.all(tasks).then(function () {
        render();
      });
    });
  }

  fetchItemsForGrn().then(function () {
    return hydrateFromHidden();
  }).then(function () {
    if (!state.lines.length) render();
    if (!isEdit) applySuggestedGrn(false);
    var ss = parseInt(pageData.startStep, 10) || 1;
    setStep(ss === 2 ? 2 : 1);
    updateSaveState();
  });
}

window.initPage_inward = initPage_inward;