/**
 * Sales invoice — two-step wizard; lines from sales order + FG batch rows (log sheet).
 */
function initPage_sales_invoice() {
  var form = document.getElementById('siForm');
  if (!form) return;

  var GST_EXEMPTED = 'EXEMPTED';
  var GST_IGST = 'IGST';
  var GST_CGST_SGST = 'CGST_SGST';

  var step1 = document.getElementById('siStep1');
  var step2 = document.getElementById('siStep2');
  var lineList = document.getElementById('siLineList');
  if (!lineList) return;
  var lineEmpty = document.getElementById('siLineEmpty');
  var linesHidden = document.getElementById('siLinesJson');
  var btnAdd = document.getElementById('btnSiAddLine');
  var btnNext = document.getElementById('btnSiNext');
  var btnBack = document.getElementById('btnSiBack');
  var btnSave = document.getElementById('btnSiSave');
  var btnClear = document.getElementById('btnSiClear');
  var errLines = document.getElementById('err-lines_json');
  var errLinesStep1 = document.getElementById('err-lines_json_step1');
  var errStep1 = document.getElementById('err-step1');
  var STEP1_FIELD_IDS = [
    'siCustomer', 'siOrderRef', 'siTransporter', 'siDeliveryAdd', 'siInvoiceDt', 'siInvoiceNo',
  ];
  var headerIcon = document.getElementById('siHeaderIcon');
  var headerTitle = document.getElementById('siHeaderTitle');
  var headerSub = document.getElementById('siHeaderSub');
  var dot1 = document.getElementById('siDot1');
  var dot2 = document.getElementById('siDot2');
  var orderPick = document.getElementById('siOrderRef');
  var _renderTimer = null;
  var _RENDER_DEBOUNCE_MS = 450;

  var pageData = {};
  try {
    var pd = document.getElementById('siPageData');
    if (pd) pageData = JSON.parse(pd.textContent || '{}');
  } catch (e) { /* ignore */ }

  var isEdit = !!pageData.isEdit;
  var editPk = pageData.editPk || null;
  var numberSuggest = pageData.numberSuggest || {};

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

  var ajaxUrls = readJsonObject('siAjaxUrls');
  var URL_NEXT = ajaxUrls.nextNumbers || '';
  var URL_ORDERS = ajaxUrls.orders || '';
  var URL_FG = ajaxUrls.fgBatches || '';
  var URL_ORDER_DETAIL = ajaxUrls.orderDetail || '';
  var URL_ORDER_PRODUCTS = ajaxUrls.orderProducts || '';
  var fetchOpts = { credentials: 'same-origin', headers: { Accept: 'application/json' } };

  var state = { lines: [] };
  var orderProducts = [];
  var storedOrderId = '';

  function escHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function roundMoney(x) {
    return Math.round(Number(x) * 100) / 100;
  }

  function lineGstParts(taxable, gstPer, gstType) {
    var t = roundMoney(Number(taxable) * Number(gstPer) / 100);
    if (gstType === GST_EXEMPTED) return { cg: 0, sg: 0, ig: 0 };
    if (gstType === GST_IGST) return { cg: 0, sg: 0, ig: t };
    var h = roundMoney(t / 2);
    return { cg: h, sg: h, ig: 0 };
  }

  function sumBatchLac(line) {
    var t = 0;
    (line.batches || []).forEach(function (b) {
      t += parseFloat(b.batch_qty) || 0;
    });
    return t;
  }

  function recalcLine(line) {
    var batchLac = sumBatchLac(line);
    line.batch_lac_sum = batchLac;
    var pv = line.pkg_style_value != null ? Number(line.pkg_style_value) : 0;
    var rate = parseFloat(line.rate) || 0;
    var nos = batchLac * 100000;
    var packs = pv > 0 ? (nos / pv) : 0;
    line.taxable_amt = roundMoney(packs * rate);
    var gp = line.gst_type === GST_EXEMPTED ? 0 : (parseFloat(line.gst_per) || 0);
    var parts = lineGstParts(line.taxable_amt, gp, line.gst_type);
    line.cgst_amt = parts.cg;
    line.sgst_amt = parts.sg;
    line.igst_amt = parts.ig;
    line.prod_amt = roundMoney(line.taxable_amt + parts.cg + parts.sg + parts.ig);
  }

  function moneyStr(v) {
    return (v == null || isNaN(v)) ? '0.00' : Number(v).toFixed(2);
  }

  function lacSumStr(line) {
    var s = sumBatchLac(line);
    return (s == null || isNaN(s)) ? '0.000' : Number(s).toFixed(3);
  }

  function collapseAllExcept(openIdx) {
    for (var i = 0; i < state.lines.length; i++) {
      state.lines[i].collapsed = (i !== openIdx);
    }
  }

  function getOrderProduct(orderLineId) {
    var id = String(orderLineId || '');
    for (var i = 0; i < orderProducts.length; i++) {
      if (String(orderProducts[i].order_line_id) === id) return orderProducts[i];
    }
    return null;
  }

  function productOptions(selected) {
    var o = '<option value=""></option>';
    orderProducts.forEach(function (p) {
      var sel = String(p.order_line_id) === String(selected) ? ' selected' : '';
      var label = p.is_sale_completed
        ? escHtml(p.prod_name) + ' (completed)'
        : escHtml(p.prod_name);
      var dis = p.is_sale_completed ? ' disabled' : '';
      o += '<option value="' + p.order_line_id + '"' + sel + dis + '>' + label + '</option>';
    });
    return o;
  }

  function emptyLine() {
    return {
      order_line_id: '',
      prod_id: '',
      prod_name: '',
      pkg_style_id: '',
      pkg_style_name: '',
      pkg_style_value: null,
      hsn_code: '',
      rate: '',
      export_type: '',
      gst_type: GST_CGST_SGST,
      gst_per: '18',
      batches: [{ batch_dtl_id: '', batch_no: '', mfg: '', exp: '', batch_qty: '' }],
      availBatches: [],
      collapsed: false,
      batchExpanded: true,
    };
  }

  function applyOrderLineToState(line, op) {
    if (!op) return;
    line.order_line_id = String(op.order_line_id);
    line.prod_id = String(op.prod_id);
    line.prod_name = op.prod_name || '';
    line.hsn_code = op.hsn_code || '';
    line.pkg_style_id = String(op.pkg_style_id || '');
    line.pkg_style_name = op.pkg_style_name || '';
    line.pkg_style_value = op.pkg_style_value != null ? Number(op.pkg_style_value) : null;
    line.rate = op.rate != null ? String(op.rate) : '';
    line.export_type = op.export_type || '';
    line.gst_type = op.gst_type || GST_CGST_SGST;
    line.gst_per = op.gst_per != null ? String(op.gst_per) : '18';
  }

  function syncLinesJson() {
    if (!linesHidden) return;
    var out = state.lines.map(function (ln) {
      return {
        order_line_id: ln.order_line_id,
        prod_id: ln.prod_id,
        pkg_style_id: ln.pkg_style_id,
        rate: String(ln.rate || ''),
        gst_type: ln.gst_type,
        gst_per: String(ln.gst_per || '0'),
        batches: (ln.batches || []).map(function (b) {
          return {
            batch_dtl_id: b.batch_dtl_id ? String(b.batch_dtl_id) : '',
            batch_qty: String(b.batch_qty || ''),
          };
        }),
      };
    });
    linesHidden.value = JSON.stringify(out);
  }

  function setAllByClass(cls, val) {
    form.querySelectorAll('.' + cls).forEach(function (el) {
      el.value = val;
    });
  }

  function refreshHeaderTotals() {
    var sumTax = 0;
    var sumC = 0;
    var sumS = 0;
    var sumI = 0;
    state.lines.forEach(function (ln) {
      if (!ln.order_line_id) return;
      recalcLine(ln);
      sumTax += ln.taxable_amt;
      sumC += ln.cgst_amt;
      sumS += ln.sgst_amt;
      sumI += ln.igst_amt;
    });
    var pkg = parseFloat(document.getElementById('siPkgFwd') && document.getElementById('siPkgFwd').value) || 0;
    var frt = parseFloat(document.getElementById('siFreight') && document.getElementById('siFreight').value) || 0;
    var oth = parseFloat(document.getElementById('siOthCharges') && document.getElementById('siOthCharges').value) || 0;
    var rnd = parseFloat(document.getElementById('siRoundOff') && document.getElementById('siRoundOff').value) || 0;
    var total = roundMoney(sumTax + pkg + frt + oth + sumC + sumS + sumI + rnd);
    setAllByClass('si-ro-taxable', moneyStr(sumTax));
    setAllByClass('si-ro-cgst', moneyStr(sumC));
    setAllByClass('si-ro-sgst', moneyStr(sumS));
    setAllByClass('si-ro-igst', moneyStr(sumI));
    setAllByClass('si-ro-total', moneyStr(total));
  }

  function scheduleRender() {
    if (_renderTimer) clearTimeout(_renderTimer);
    _renderTimer = setTimeout(function () {
      _renderTimer = null;
      refreshLines();
    }, _RENDER_DEBOUNCE_MS);
  }

  function updateLineCardDisplay(idx) {
    var line = state.lines[idx];
    var card = lineList.querySelector('[data-line-idx="' + idx + '"]');
    if (!line || !card) return;
    recalcLine(line);
    var setRo = function (sel, val) {
      var el = card.querySelector(sel);
      if (el) el.value = val;
    };
    setRo('.so-cell-prod-amt input', moneyStr(line.prod_amt));
    setRo('.so-cell-ordnos input', lacSumStr(line));
    setRo('.so-cell-taxable input', moneyStr(line.taxable_amt));
    setRo('.so-cell-cgst input', moneyStr(line.cgst_amt));
    setRo('.so-cell-sgst input', moneyStr(line.sgst_amt));
    setRo('.so-cell-igst input', moneyStr(line.igst_amt));
    refreshHeaderTotals();
    syncLinesJson();
  }

  function onGstTypeChange(idx, sel) {
    var line = state.lines[idx];
    if (!line || !sel) return;
    line.gst_type = sel.value;
    if (line.gst_type === GST_EXEMPTED) {
      line.gst_per = '0';
    } else if (!line.gst_per || line.gst_per === '0') {
      var op = getOrderProduct(line.order_line_id);
      line.gst_per = op && op.gst_per ? String(op.gst_per) : '18';
    }
    refreshLines();
  }

  function bindLineCard(idx, card) {
    var rt = card.querySelector('.so-rate');
    if (rt) {
      rt.addEventListener('input', function () {
        state.lines[idx].rate = rt.value;
        syncLinesJson();
        scheduleRender();
      });
      rt.addEventListener('change', function () {
        state.lines[idx].rate = rt.value;
        syncLinesJson();
        refreshLines();
      });
    }
    var gp = card.querySelector('.so-gst-per');
    if (gp) {
      gp.addEventListener('input', function () {
        if (state.lines[idx].gst_type === GST_EXEMPTED) return;
        state.lines[idx].gst_per = gp.value;
        syncLinesJson();
        updateLineCardDisplay(idx);
      });
      gp.addEventListener('change', function () {
        if (state.lines[idx].gst_type === GST_EXEMPTED) return;
        state.lines[idx].gst_per = gp.value;
        syncLinesJson();
        refreshLines();
      });
    }
    var gt = card.querySelector('.so-gst-type');
    if (gt) {
      gt.addEventListener('change', function () {
        onGstTypeChange(idx, gt);
      });
    }
  }

  function setLinesErr(msg) {
    var t = msg || '';
    if (errLines) errLines.textContent = t;
    if (errLinesStep1) errLinesStep1.textContent = t;
  }

  function clearStep1ClientErrors() {
    STEP1_FIELD_IDS.forEach(function (id) {
      var el = document.getElementById(id);
      if (!el) return;
      el.classList.remove('input-error');
      el.removeAttribute('aria-invalid');
    });
    if (errStep1) errStep1.textContent = '';
  }

  function markStep1Field(fieldId, msg) {
    var el = document.getElementById(fieldId);
    if (el) {
      el.classList.add('input-error');
      el.setAttribute('aria-invalid', 'true');
    }
    if (msg && errStep1 && !errStep1.textContent) errStep1.textContent = msg;
  }

  function prepareLinesForSubmit(showErr) {
    setLinesErr('');
    clearStep1ClientErrors();
    syncLinesJson();

    if (!orderPick || !orderPick.value) {
      if (showErr) {
        markStep1Field('siOrderRef', 'Select a sales order.');
        setStep(1);
      }
      return false;
    }

    if (!hasLines()) {
      if (showErr) {
        setLinesErr('Add at least one product line with batch allocation.');
        setStep(2);
      }
      return false;
    }

    if (!validateStep2()) {
      if (showErr) setStep(2);
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

  function hasLines() {
    for (var i = 0; i < state.lines.length; i++) {
      if (state.lines[i] && state.lines[i].order_line_id) return true;
    }
    return false;
  }

  function updateSaveState() {
    var ok = hasLines();
    form.querySelectorAll('.si-save-btn').forEach(function (btn) {
      btn.setAttribute('aria-disabled', ok ? 'false' : 'true');
    });
  }

  function setHeader(step) {
    var H = {
      1: {
        icon: isEdit ? 'bi-pencil-fill' : 'bi-receipt',
        title: isEdit ? 'Edit sales invoice' : 'New sales invoice',
        sub: 'Invoice details and charges',
      },
      2: {
        icon: 'bi-grid-3x3-gap',
        title: 'Products & batches',
        sub: 'Select products from the sales order and allocate FG batches',
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
    if (step === 1) refreshHeaderTotals();
  }

  function getCustOrderIds() {
    var cust = document.getElementById('siCustomer');
    var order = orderPick;
    return {
      custId: cust && cust.value,
      orderId: (order && order.value) || storedOrderId,
    };
  }

  function batchOptions(line, selId) {
    var opts = '<option value="">— Allocated batch —</option>';
    (line.availBatches || []).forEach(function (b) {
      var id = String(b.batch_dtl_id);
      var sel = String(selId) === id ? ' selected' : '';
      var label = b.label || b.batch_no || '';
      opts += '<option value="' + escHtml(id) + '"' + sel + '>' + escHtml(label) + '</option>';
    });
    return opts;
  }

  function renderBatchRows(lineIdx, line) {
    var wrap = document.createElement('div');
    wrap.className = 'inw-batch-inner';
    (line.batches || []).forEach(function (b, bidx) {
      var row = document.createElement('div');
      row.className = 'inw-batch-row si-batch-row';
      row.dataset.lineIdx = String(lineIdx);
      row.dataset.batchIdx = String(bidx);
      row.innerHTML =
        '<div class="inw-cell"><label>Allocated batch <span class="req">*</span></label>' +
        '<select class="cu-select searchable-dropdown si-batch-dtl" data-line="' + lineIdx + '" data-bidx="' + bidx + '">' +
        batchOptions(line, b.batch_dtl_id) + '</select></div>' +
        '<div class="inw-cell"><label>Mfg</label><input type="text" class="cu-input si-batch-mfg" readonly tabindex="-1" value="' +
        escHtml(b.mfg || '') + '"></div>' +
        '<div class="inw-cell"><label>Exp</label><input type="text" class="cu-input si-batch-exp" readonly tabindex="-1" value="' +
        escHtml(b.exp || '') + '"></div>' +
        '<div class="inw-cell"><label>Batch qty (lac) <span class="req">*</span></label>' +
        '<input type="number" class="cu-input si-batch-qty" min="0.001" step="0.001" data-line="' + lineIdx + '" data-bidx="' + bidx +
        '" value="' + escHtml(b.batch_qty) + '"></div>' +
        '<div class="inw-cell si-batch-actions"><button type="button" class="btn-cancel si-batch-rm" data-line="' + lineIdx + '" data-bidx="' + bidx +
        '"><i class="bi bi-trash"></i></button></div>';
      wrap.appendChild(row);
    });
    return wrap;
  }

  function refreshLines() {
    if (!lineList) return;
    if (typeof destroySearchableDropdownsIn === 'function') destroySearchableDropdownsIn(lineList);
    lineList.innerHTML = '';
    var ids = getCustOrderIds();
    var hasOrder = !!(ids.custId && ids.orderId);

    state.lines.forEach(function (line, idx) {
      recalcLine(line);
      var card = document.createElement('div');
      card.className = 'inw-line-card so-line-card';
      card.dataset.lineIdx = String(idx);

      var head = document.createElement('div');
      head.className = 'so-acc-head';

      var acc = document.createElement('button');
      acc.type = 'button';
      acc.className = 'so-acc-toggle' + (line.collapsed ? '' : ' is-open');
      acc.setAttribute('aria-expanded', line.collapsed ? 'false' : 'true');
      acc.dataset.idx = String(idx);
      var prodName = line.prod_name || (getOrderProduct(line.order_line_id) || {}).prod_name;
      acc.innerHTML =
        '<span class="so-acc-icon"><i class="bi bi-chevron-down"></i></span>' +
        '<span class="so-acc-text">' + (prodName ? escHtml(prodName) : 'Select product') + '</span>' +
        '<span class="so-acc-meta">' + escHtml('Line ' + (idx + 1)) + '</span>';

      var rm = document.createElement('button');
      rm.type = 'button';
      rm.className = 'so-acc-remove so-remove-line';
      rm.dataset.idx = String(idx);
      rm.title = 'Remove line';
      rm.innerHTML = '<i class="bi bi-x"></i>';

      head.appendChild(acc);
      head.appendChild(rm);
      card.appendChild(head);

      var gstPerDisabled = line.gst_type === GST_EXEMPTED ? ' disabled tabindex="-1"' : '';
      var gstPerVal = line.gst_type === GST_EXEMPTED ? '0' : escHtml(line.gst_per);

      var body = document.createElement('div');
      body.className = 'so-acc-body';
      body.style.display = line.collapsed ? 'none' : 'block';

      var prodSelInner = hasOrder
        ? productOptions(line.order_line_id)
        : '<option value="">— Select sales order in step 1 —</option>';

      var main = document.createElement('div');
      main.className = 'inw-line-main';
      main.innerHTML =
        '<div class="inw-cell inw-cell-item so-cell-product">' +
        '<label>Product <span class="req">*</span></label>' +
        '<select class="cu-select searchable-dropdown si-prod-select" data-idx="' + idx + '">' + prodSelInner + '</select></div>' +
        '<div class="inw-cell so-cell-hsn">' +
        '<label>HSN <span class="req">*</span></label>' +
        '<input type="text" class="cu-input so-hsn" readonly tabindex="-1" value="' +
        escHtml(line.hsn_code || '') + '"></div>' +
        '<div class="inw-cell so-cell-pack">' +
        '<label>Packing style <span class="req">*</span></label>' +
        '<input type="text" class="cu-input" readonly tabindex="-1" value="' +
        escHtml(line.pkg_style_name || '') + '"></div>' +
        '<div class="inw-cell so-cell-rate"><label>Rate <span class="req">*</span></label>' +
        '<input type="number" class="cu-input so-rate" min="0.0001" step="0.0001" data-idx="' + idx +
        '" value="' + escHtml(line.rate) + '"></div>' +
        '<div class="inw-cell so-cell-export">' +
        '<label>Export type</label>' +
        '<input type="text" class="cu-input so-export" readonly tabindex="-1" value="' +
        escHtml(line.export_type || '') + '"></div>' +
        '<div class="inw-cell so-cell-prod-amt"><label>Product amount</label>' +
        '<input type="text" class="cu-input cu-num" readonly tabindex="-1" value="' + moneyStr(line.prod_amt) + '"></div>' +
        '<div class="inw-cell so-cell-ordnos"><label>Batch qty (lac)</label>' +
        '<input type="text" class="cu-input cu-num" readonly tabindex="-1" value="' +
        lacSumStr(line) + '"></div>' +
        '<div class="inw-cell so-cell-taxable"><label>Taxable</label>' +
        '<input type="text" class="cu-input cu-num" readonly tabindex="-1" value="' +
        moneyStr(line.taxable_amt) + '"></div>' +
        '<div class="inw-cell so-cell-gst-type">' +
        '<label>GST type <span class="req">*</span></label>' +
        '<select class="cu-select so-gst-type" data-idx="' + idx + '">' +
        '<option value="' + GST_CGST_SGST + '"' + (line.gst_type === GST_CGST_SGST ? ' selected' : '') + '>CGST + SGST</option>' +
        '<option value="' + GST_IGST + '"' + (line.gst_type === GST_IGST ? ' selected' : '') + '>IGST</option>' +
        '<option value="' + GST_EXEMPTED + '"' + (line.gst_type === GST_EXEMPTED ? ' selected' : '') + '>Exempted</option>' +
        '</select></div>' +
        '<div class="inw-cell so-cell-gst-per"><label>GST % <span class="req">*</span></label>' +
        '<input type="number" class="cu-input so-gst-per" min="0" max="100" step="0.01" data-idx="' + idx +
        '" value="' + gstPerVal + '"' + gstPerDisabled + '></div>' +
        '<div class="inw-cell so-cell-cgst"><label>CGST</label>' +
        '<input type="text" class="cu-input cu-num" readonly tabindex="-1" value="' + moneyStr(line.cgst_amt) + '"></div>' +
        '<div class="inw-cell so-cell-sgst"><label>SGST</label>' +
        '<input type="text" class="cu-input cu-num" readonly tabindex="-1" value="' + moneyStr(line.sgst_amt) + '"></div>' +
        '<div class="inw-cell so-cell-igst"><label>IGST</label>' +
        '<input type="text" class="cu-input cu-num" readonly tabindex="-1" value="' + moneyStr(line.igst_amt) + '"></div>';

      body.appendChild(main);

      var n = (line.batches && line.batches.length) ? line.batches.length : 0;
      var bbar = document.createElement('button');
      bbar.type = 'button';
      bbar.className = 'inw-batch-toggle' + (line.batchExpanded ? ' is-open' : '');
      bbar.setAttribute('aria-expanded', line.batchExpanded ? 'true' : 'false');
      bbar.dataset.idx = String(idx);
      bbar.innerHTML =
        '<span class="inw-batch-toggle-icon"><i class="bi bi-chevron-down"></i></span>' +
        '<span class="inw-batch-toggle-text">Batches</span>' +
        (n ? '<span class="inw-batch-count">' + n + '</span>' : '');

      body.appendChild(bbar);

      var bpanel = document.createElement('div');
      bpanel.className = 'inw-batch-panel so-dispatch-panel';
      bpanel.style.display = line.batchExpanded ? 'block' : 'none';
      bpanel.dataset.idx = String(idx);
      bpanel.appendChild(renderBatchRows(idx, line));

      var addB = document.createElement('button');
      addB.type = 'button';
      addB.className = 'inw-add-batch';
      addB.dataset.idx = String(idx);
      addB.innerHTML = '<i class="bi bi-plus-lg"></i><span>Add batch row</span>';
      bpanel.appendChild(addB);
      body.appendChild(bpanel);

      card.appendChild(body);
      lineList.appendChild(card);
      bindLineCard(idx, card);
    });

    if (typeof initSearchableDropdowns === 'function') initSearchableDropdowns(lineList);
    if (lineEmpty) lineEmpty.style.display = state.lines.length ? 'none' : '';
    syncLinesJson();
    refreshHeaderTotals();
    updateSaveState();
  }

  function loadFgBatchesForLine(idx) {
    var line = state.lines[idx];
    if (!line || !line.order_line_id) return Promise.resolve();
    var ids = getCustOrderIds();
    if (!ids.custId || !ids.orderId) return Promise.resolve();
    var qs = '?cust_id=' + encodeURIComponent(ids.custId) +
      '&order_id=' + encodeURIComponent(ids.orderId) +
      '&order_line_id=' + encodeURIComponent(line.order_line_id);
    if (editPk) qs += '&exclude_invoice_id=' + encodeURIComponent(editPk);
    return fetch(URL_FG + qs, fetchOpts)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        line.availBatches = data.batches || [];
      })
      .catch(function () {
        line.availBatches = [];
      });
  }

  function fetchOrderProducts() {
    var ids = getCustOrderIds();
    orderProducts = [];
    if (!ids.custId || !ids.orderId || !URL_ORDER_PRODUCTS) {
      refreshLines();
      return Promise.resolve();
    }
    storedOrderId = String(ids.orderId);
    return fetch(
      URL_ORDER_PRODUCTS + '?cust_id=' + encodeURIComponent(ids.custId) +
      '&order_id=' + encodeURIComponent(ids.orderId),
      fetchOpts,
    )
      .then(function (r) { return r.json(); })
      .then(function (data) {
        orderProducts = data.lines || [];
        refreshLines();
      })
      .catch(function () {
        orderProducts = [];
        refreshLines();
      });
  }

  function loadOrderCharges() {
    var ids = getCustOrderIds();
    if (!ids.custId || !ids.orderId || !URL_ORDER_DETAIL) return Promise.resolve();
    return fetch(
      URL_ORDER_DETAIL + '?cust_id=' + encodeURIComponent(ids.custId) +
      '&order_id=' + encodeURIComponent(ids.orderId),
      fetchOpts,
    )
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var pkg = document.getElementById('siPkgFwd');
        var frt = document.getElementById('siFreight');
        var oth = document.getElementById('siOthCharges');
        if (pkg && data.pkg_fwd_amt != null) pkg.value = data.pkg_fwd_amt;
        if (frt && data.freight_amt != null) frt.value = data.freight_amt;
        if (oth && data.oth_charges != null) oth.value = data.oth_charges;
        refreshHeaderTotals();
      })
      .catch(function () { /* ignore */ });
  }

  function hydrateFromHidden() {
    try {
      var raw = linesHidden && linesHidden.value ? JSON.parse(linesHidden.value) : [];
      if (!Array.isArray(raw) || !raw.length) {
        state.lines = [];
        return Promise.resolve();
      }
      state.lines = raw.map(function (r) {
        var ln = emptyLine();
        ln.order_line_id = r.order_line_id ? String(r.order_line_id) : '';
        ln.prod_id = r.prod_id ? String(r.prod_id) : '';
        ln.pkg_style_id = r.pkg_style_id ? String(r.pkg_style_id) : '';
        ln.rate = r.rate != null ? String(r.rate) : '';
        ln.gst_type = r.gst_type || GST_CGST_SGST;
        ln.gst_per = r.gst_per != null ? String(r.gst_per) : '18';
        ln.batches = (r.batches && r.batches.length) ? r.batches.map(function (b) {
          return {
            batch_dtl_id: b.batch_dtl_id ? String(b.batch_dtl_id) : '',
            batch_qty: b.batch_qty != null ? String(b.batch_qty) : '',
            batch_no: '', mfg: '', exp: '',
          };
        }) : [{ batch_dtl_id: '', batch_no: '', mfg: '', exp: '', batch_qty: '' }];
        return ln;
      });
      if (orderPick && orderPick.value) storedOrderId = orderPick.value;
      return fetchOrderProducts().then(function () {
        state.lines.forEach(function (ln, i) {
          var op = getOrderProduct(ln.order_line_id);
          if (op) applyOrderLineToState(ln, op);
        });
        return Promise.all(state.lines.map(function (_, i) {
          return loadFgBatchesForLine(i).then(function () {
            var ln = state.lines[i];
            (ln.batches || []).forEach(function (b) {
              if (!b.batch_dtl_id) return;
              var hit = (ln.availBatches || []).filter(function (x) {
                return String(x.batch_dtl_id) === String(b.batch_dtl_id);
              })[0];
              if (hit) {
                b.batch_no = hit.batch_no;
                b.mfg = hit.mfg;
                b.exp = hit.exp;
              }
            });
          });
        }));
      });
    } catch (e) {
      state.lines = [];
      return Promise.resolve();
    }
  }

  function refreshOrderDropdown() {
    if (!orderPick) return;
    var cust = document.getElementById('siCustomer');
    var cid = cust && cust.value;
    var prevVal = orderPick.value || storedOrderId;
    orderPick.innerHTML = '<option value="">— Select sales order —</option>';
    if (!cid || !URL_ORDERS) {
      if (typeof initSearchableDropdowns === 'function') initSearchableDropdowns(orderPick);
      return;
    }
    var qs = '?cust_id=' + encodeURIComponent(cid);
    if (prevVal) qs += '&include_order_id=' + encodeURIComponent(prevVal);
    fetch(URL_ORDERS + qs, fetchOpts)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        (data.orders || []).forEach(function (o) {
          var opt = document.createElement('option');
          opt.value = o.order_id;
          opt.textContent = o.cust_ord_id + ' @ ' + (o.ord_rec_dt || '');
          orderPick.appendChild(opt);
        });
        if (prevVal) {
          for (var i = 0; i < orderPick.options.length; i++) {
            if (String(orderPick.options[i].value) === String(prevVal)) {
              orderPick.selectedIndex = i;
              break;
            }
          }
        }
        if (typeof initSearchableDropdowns === 'function') initSearchableDropdowns(orderPick);
      });
  }

  function refreshSuggestedInvoiceNo() {
    if (isEdit) return Promise.resolve();
    var dtEl = document.getElementById('siInvoiceDt');
    var invNo = document.getElementById('siInvoiceNo');
    if (!dtEl || !invNo || !URL_NEXT) return Promise.resolve();
    var qs = '?invoice_dt=' + encodeURIComponent(dtEl.value || '');
    return fetch(URL_NEXT + qs, fetchOpts)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.invoice_no && invNo) {
          invNo.value = data.invoice_no;
          if (typeof prefixedSerialNoNormalize === 'function') {
            prefixedSerialNoNormalize(invNo, 'SI-');
          }
        }
      })
      .catch(function () { /* ignore */ });
  }

  function validateStep1() {
    clearStep1ClientErrors();
    var ok = true;
    var cust = document.getElementById('siCustomer');
    var trans = document.getElementById('siTransporter');
    var del = document.getElementById('siDeliveryAdd');
    var dt = document.getElementById('siInvoiceDt');
    var inv = document.getElementById('siInvoiceNo');
    if (!cust || !cust.value) {
      markStep1Field('siCustomer', 'Select a customer.');
      ok = false;
    }
    if (!orderPick || !orderPick.value) {
      markStep1Field('siOrderRef', 'Select a sales order.');
      ok = false;
    }
    if (!trans || !trans.value) {
      markStep1Field('siTransporter', 'Select a transporter.');
      ok = false;
    }
    if (!del || !(del.value || '').trim()) {
      markStep1Field('siDeliveryAdd', 'Enter delivery address.');
      ok = false;
    }
    if (!dt || !dt.value) {
      markStep1Field('siInvoiceDt', 'Enter invoice date.');
      ok = false;
    }
    if (!inv || !(inv.value || '').trim()) {
      markStep1Field('siInvoiceNo', 'Enter invoice number.');
      ok = false;
    }
    if (!ok) return false;
    storedOrderId = orderPick.value;
    return true;
  }

  function validateStep2() {
    if (!hasLines()) {
      setLinesErr('Add at least one product line.');
      return false;
    }
    for (var i = 0; i < state.lines.length; i++) {
      var ln = state.lines[i];
      if (!ln.order_line_id) {
        setLinesErr('Line ' + (i + 1) + ': select a product.');
        return false;
      }
      var hasBatch = false;
      (ln.batches || []).forEach(function (b) {
        if (b.batch_dtl_id && parseFloat(b.batch_qty) > 0) hasBatch = true;
      });
      if (!hasBatch) {
        setLinesErr('Line ' + (i + 1) + ': add at least one batch with quantity.');
        return false;
      }
    }
    setLinesErr('');
    return true;
  }

  lineList.addEventListener('change', function (e) {
    var t = e.target;
    if (!t || !t.dataset) return;
    if (t.classList.contains('si-batch-dtl')) {
      var lidx = parseInt(t.dataset.line, 10);
      var bidx = parseInt(t.dataset.bidx, 10);
      if (isNaN(lidx) || !state.lines[lidx] || isNaN(bidx)) return;
      var line = state.lines[lidx];
      var bid = t.value;
      if (!line.batches[bidx]) return;
      line.batches[bidx].batch_dtl_id = bid;
      var hit = (line.availBatches || []).filter(function (x) {
        return String(x.batch_dtl_id) === String(bid);
      })[0];
      if (hit) {
        line.batches[bidx].batch_no = hit.batch_no;
        line.batches[bidx].mfg = hit.mfg;
        line.batches[bidx].exp = hit.exp;
        if (!line.batches[bidx].batch_qty) {
          line.batches[bidx].batch_qty = hit.batch_qty || '';
        }
      } else {
        line.batches[bidx].batch_no = '';
        line.batches[bidx].mfg = '';
        line.batches[bidx].exp = '';
      }
      refreshLines();
      return;
    }
    var idx = parseInt(t.dataset.idx, 10);
    if (isNaN(idx) || !state.lines[idx]) return;
    if (t.classList.contains('si-prod-select')) {
      var olId = t.value;
      state.lines[idx].order_line_id = olId;
      var op = getOrderProduct(olId);
      if (!olId || !op) {
        state.lines[idx].batches = [{ batch_dtl_id: '', batch_no: '', mfg: '', exp: '', batch_qty: '' }];
        state.lines[idx].availBatches = [];
        refreshLines();
        return;
      }
      applyOrderLineToState(state.lines[idx], op);
      state.lines[idx].batches = [{ batch_dtl_id: '', batch_no: '', mfg: '', exp: '', batch_qty: '' }];
      loadFgBatchesForLine(idx).then(function () { refreshLines(); });
      return;
    }
  });

  lineList.addEventListener('input', function (e) {
    var t = e.target;
    if (!t || !t.dataset) return;
    if (t.classList.contains('si-batch-qty')) {
      var lidx = parseInt(t.dataset.line, 10);
      var bidx = parseInt(t.dataset.bidx, 10);
      if (!isNaN(lidx) && !isNaN(bidx) && state.lines[lidx] && state.lines[lidx].batches[bidx]) {
        state.lines[lidx].batches[bidx].batch_qty = t.value;
        updateLineCardDisplay(lidx);
      }
      return;
    }
  });

  lineList.addEventListener('click', function (e) {
    var btn = e.target.closest('button');
    if (!btn || !btn.dataset) return;
    var idx = parseInt(btn.dataset.idx, 10);
    if (btn.classList.contains('so-acc-toggle')) {
      var line = state.lines[idx];
      if (!line) return;
      var willOpen = !!line.collapsed;
      if (willOpen) collapseAllExcept(idx);
      else line.collapsed = true;
      refreshLines();
      return;
    }
    if (btn.classList.contains('so-remove-line')) {
      state.lines.splice(idx, 1);
      refreshLines();
      return;
    }
    if (btn.classList.contains('inw-batch-toggle')) {
      var ln = state.lines[idx];
      if (ln) {
        ln.batchExpanded = !ln.batchExpanded;
        refreshLines();
      }
      return;
    }
    if (btn.classList.contains('inw-add-batch')) {
      var L = state.lines[idx];
      if (L) {
        L.batches.push({ batch_dtl_id: '', batch_no: '', mfg: '', exp: '', batch_qty: '' });
        refreshLines();
      }
      return;
    }
    if (btn.classList.contains('si-batch-rm')) {
      var lidx = parseInt(btn.dataset.line, 10);
      var bix = parseInt(btn.dataset.bidx, 10);
      var L2 = state.lines[lidx];
      if (L2 && L2.batches && L2.batches.length > 1 && !isNaN(bix)) {
        L2.batches.splice(bix, 1);
        refreshLines();
      }
    }
  });

  if (btnAdd) {
    btnAdd.addEventListener('click', function () {
      state.lines.push(emptyLine());
      collapseAllExcept(state.lines.length - 1);
      refreshLines();
    });
  }

  function bindStep1FieldClear(el) {
    if (!el) return;
    var ev = el.tagName === 'SELECT' ? 'change' : 'input';
    el.addEventListener(ev, function () {
      el.classList.remove('input-error');
      el.removeAttribute('aria-invalid');
      if (errStep1) errStep1.textContent = '';
    });
  }

  STEP1_FIELD_IDS.forEach(function (id) {
    bindStep1FieldClear(document.getElementById(id));
  });

  if (btnNext) {
    btnNext.addEventListener('click', function () {
      if (!validateStep1()) return;
      fetchOrderProducts().then(function () {
        setStep(2);
        if (!state.lines.length) {
          state.lines.push(emptyLine());
          collapseAllExcept(0);
        }
        refreshLines();
      });
    });
  }

  if (btnBack) {
    btnBack.addEventListener('click', function () { setStep(1); });
  }

  var custEl = document.getElementById('siCustomer');
  if (custEl) {
    custEl.addEventListener('change', function () {
      storedOrderId = '';
      state.lines = [];
      refreshOrderDropdown();
      refreshLines();
    });
  }

  if (orderPick) {
    orderPick.addEventListener('change', function () {
      storedOrderId = orderPick.value || '';
      state.lines = [];
      clearStep1ClientErrors();
      if (orderPick.value) {
        loadOrderCharges();
      }
    });
  }

  var invDt = document.getElementById('siInvoiceDt');
  if (invDt) invDt.addEventListener('change', refreshSuggestedInvoiceNo);

  ['siPkgFwd', 'siFreight', 'siOthCharges', 'siRoundOff'].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) {
      el.addEventListener('input', refreshHeaderTotals);
      el.addEventListener('change', refreshHeaderTotals);
    }
  });

  form.addEventListener('submit', function (e) {
    if (!prepareLinesForSubmit(true)) {
      e.preventDefault();
      return;
    }
    syncLinesJson();
  });

  form.querySelectorAll('.si-save-btn').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      if (!prepareLinesForSubmit(true)) {
        e.preventDefault();
      }
    });
  });

  document.body.addEventListener('htmx:configRequest', function (e) {
    if (!isThisFormHtmxRequest(e)) return;
    if (!prepareLinesForSubmit(true)) e.preventDefault();
  });

  document.body.addEventListener('htmx:beforeRequest', function (e) {
    if (!isThisFormHtmxRequest(e)) return;
    if (!prepareLinesForSubmit(true)) e.preventDefault();
  });

  if (!isEdit && numberSuggest.invoice_no) {
    var invNoEl = document.getElementById('siInvoiceNo');
    if (invNoEl && !invNoEl.value) {
      invNoEl.value = numberSuggest.invoice_no;
      if (typeof prefixedSerialNoNormalize === 'function') {
        prefixedSerialNoNormalize(invNoEl, 'SI-');
      }
    }
  }

  var invNoLockEl = document.getElementById('siInvoiceNo');
  if (typeof prefixedSerialNoBindLock === 'function' && invNoLockEl) {
    prefixedSerialNoBindLock(invNoLockEl, function () { return 'SI-'; });
  }

  function finishSiInit() {
    if (orderPick && orderPick.value) storedOrderId = orderPick.value;
    var start = pageData.startStep || 1;
    if (!state.lines.length && start === 2) {
      state.lines.push(emptyLine());
      collapseAllExcept(0);
    }
    refreshOrderDropdown();
    refreshLines();
    if (start > 2) start = 2;
    setStep(start);
    if (start >= 2) fetchOrderProducts();
  }

  if (isEdit && pageData.editPk) {
    editPk = pageData.editPk;
  } else if (form.querySelector('input[name="edit_pk"]')) {
    editPk = form.querySelector('input[name="edit_pk"]').value;
  }

  // Hydrate before any fetch that calls refreshLines/syncLinesJson — otherwise
  // an empty state.lines overwrites server-provided lines_json on edit.
  hydrateFromHidden()
    .then(finishSiInit)
    .catch(function () { finishSiInit(); });

  window.resetSalesInvoiceForm = function () {
    if (typeof clearMasterFormValidationUI === 'function') clearMasterFormValidationUI(form);
    form.querySelectorAll('input, select, textarea').forEach(function (el) {
      if (el.type === 'hidden') return;
      if (el.id === 'siLinesJson') return;
      if (el.readOnly && (
        el.classList.contains('si-ro-taxable') ||
        el.classList.contains('si-ro-cgst') ||
        el.classList.contains('si-ro-sgst') ||
        el.classList.contains('si-ro-igst') ||
        el.classList.contains('si-ro-total')
      )) return;
      if (el.tagName === 'SELECT') {
        el.selectedIndex = 0;
      } else {
        el.value = '';
      }
    });
    setLinesErr('');
    clearStep1ClientErrors();
    var idt = document.getElementById('siInvoiceDt');
    if (idt) {
      var today = new Date();
      idt.value = today.getFullYear() + '-' + String(today.getMonth() + 1).padStart(2, '0') + '-' + String(today.getDate()).padStart(2, '0');
    }
    var editPkInput = form.querySelector('input[name="edit_pk"]');
    if (editPkInput) editPkInput.remove();
    form.action = form.action.split('?')[0];
    state.lines = [];
    storedOrderId = '';
    orderProducts = [];
    refreshSuggestedInvoiceNo().then(function () {
      refreshOrderDropdown();
      refreshLines();
      refreshHeaderTotals();
      setStep(1);
      updateSaveState();
    });
  };
}

window.initPage_sales_invoice = initPage_sales_invoice;
