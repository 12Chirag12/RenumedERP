/**
 * Sales order — two-step wizard; lines_json with nested dispatch rows (collapsible).
 */
function initPage_sales_order() {
  var form = document.getElementById('soForm');
  if (!form) return;

  var GST_EXEMPTED = 'EXEMPTED';
  var GST_IGST = 'IGST';
  var GST_CGST_SGST = 'CGST_SGST';

  var step1 = document.getElementById('soStep1');
  var step2 = document.getElementById('soStep2');
  var lineList = document.getElementById('soLineList');
  var lineEmpty = document.getElementById('soLineEmpty');
  var linesHidden = document.getElementById('soLinesJson');
  var btnAdd = document.getElementById('btnSoAddLine');
  var btnNext = document.getElementById('btnSoNext');
  var btnBack = document.getElementById('btnSoBack');
  var btnSave = document.getElementById('btnSoSave');
  var errEl = document.getElementById('err-lines_json');
  var errElStep1 = document.getElementById('err-lines_json_step1');
  var headerIcon = document.getElementById('soHeaderIcon');
  var headerTitle = document.getElementById('soHeaderTitle');
  var headerSub = document.getElementById('soHeaderSub');
  var dot1 = document.getElementById('soDot1');
  var dot2 = document.getElementById('soDot2');
  var docInput = document.getElementById('soHeaderDocInput');
  var docBtn = document.getElementById('soDocUploadBtn');
  var docHint = document.getElementById('soDocHint');
  var previewShell = document.getElementById('soDocPreviewShell');
  var docPreviewImg = document.getElementById('soDocPreviewImg');
  var docPreviewPdf = document.getElementById('soDocPreviewPdf');
  var roTaxable = document.getElementById('soRoTaxable');
  var roCgst = document.getElementById('soRoCgst');
  var roSgst = document.getElementById('soRoSgst');
  var roIgst = document.getElementById('soRoIgst');
  var roTotal = document.getElementById('soRoTotal');
  var DOC_HINT_DEFAULT = 'PDF or image — max 15 MB';
  var docBlobUrl = null;

  var pageData = {};
  try {
    var pd = document.getElementById('soPageData');
    if (pd) pageData = JSON.parse(pd.textContent || '{}');
  } catch (e) { /* ignore */ }

  var isEdit = !!pageData.isEdit;

  var state = { lines: [] };

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

  var products = readJsonScript('soProductsData');
  var ajaxUrls = readJsonObject('soAjaxUrls');
  var URL_PRODUCT_META = ajaxUrls.productMeta || '/transactions/ajax/sales-order-product-meta/';
  var URL_CUSTOMER_PRODUCTS = ajaxUrls.customerProducts || '/transactions/ajax/sales-order-customer-products/';
  var fetchOpts = { credentials: 'same-origin', headers: { Accept: 'application/json' } };

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

  function recalcLine(line) {
    var pq = parseFloat(line.order_qty) || 0;
    var rate = parseFloat(line.rate) || 0;
    var pv = line.pkg_style_value != null ? Number(line.pkg_style_value) : 0;
    // order_qty is captured in Lakhs; nos = lakhs * 100000
    line.ord_qty_nos = Math.round(pq * 100000);
    // Amount = ((qty_nos / packing_value) * rate)
    var packs = pv > 0 ? (Number(line.ord_qty_nos) / pv) : 0;
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

  function intStr(v) {
    var n = Number(v);
    if (v == null || isNaN(n)) return '0';
    return String(Math.round(n));
  }

  function refreshHeaderTotals() {
    var sumTax = 0;
    var sumC = 0;
    var sumS = 0;
    var sumI = 0;
    state.lines.forEach(function (ln) {
      if (!ln.prod_id) return;
      recalcLine(ln);
      sumTax += ln.taxable_amt;
      sumC += ln.cgst_amt;
      sumS += ln.sgst_amt;
      sumI += ln.igst_amt;
    });
    var pkg = parseFloat(document.getElementById('soPkgFwd') && document.getElementById('soPkgFwd').value) || 0;
    var frt = parseFloat(document.getElementById('soFreight') && document.getElementById('soFreight').value) || 0;
    var oth = parseFloat(document.getElementById('soOthCharges') && document.getElementById('soOthCharges').value) || 0;
    var rnd = parseFloat(document.getElementById('soRoundOff') && document.getElementById('soRoundOff').value) || 0;
    var total = roundMoney(sumTax + pkg + frt + oth + sumC + sumS + sumI + rnd);
    if (roTaxable) roTaxable.value = moneyStr(sumTax);
    if (roCgst) roCgst.value = moneyStr(sumC);
    if (roSgst) roSgst.value = moneyStr(sumS);
    if (roIgst) roIgst.value = moneyStr(sumI);
    if (roTotal) roTotal.value = moneyStr(total);
  }

  function setLinesErr(msg) {
    if (errEl) errEl.textContent = msg || '';
    if (errElStep1) errElStep1.textContent = msg || '';
  }

  function hasAtLeastOneProduct() {
    for (var i = 0; i < state.lines.length; i++) {
      var id = state.lines[i] && state.lines[i].prod_id ? String(state.lines[i].prod_id) : '';
      if (id && id !== '0') return true;
    }
    return false;
  }

  function updateSaveState() {
    if (!btnSave) return;
    var ok = hasAtLeastOneProduct();
    btnSave.setAttribute('aria-disabled', ok ? 'false' : 'true');
  }

  function setHeader(step) {
    var H = {
      1: {
        icon: isEdit ? 'bi-pencil-fill' : 'bi-cart-check',
        title: isEdit ? 'Edit sales order' : 'New sales order',
        sub: 'Order details and document',
      },
      2: {
        icon: 'bi-grid-3x3-gap',
        title: 'Products',
        sub: 'Lines and dispatch schedule',
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

  function productOptions(selected) {
    var o = '<option value=""></option>';
    products.forEach(function (p) {
      o += '<option value="' + p.prod_id + '"' +
        (String(p.prod_id) === String(selected) ? ' selected' : '') + '>' +
        escHtml(p.prod_name) + '</option>';
    });
    return o;
  }

  function getProductName(prodId) {
    var id = String(prodId || '');
    if (!id) return '';
    for (var i = 0; i < products.length; i++) {
      if (String(products[i].prod_id) === id) return String(products[i].prod_name || '');
    }
    return '';
  }

  function loadProductsForCustomer(custId) {
    products = [];
    if (!custId) return Promise.resolve([]);
    return fetch(URL_CUSTOMER_PRODUCTS + '?cust_id=' + encodeURIComponent(custId), fetchOpts)
      .then(function (r) { return r.ok ? r.json() : { products: [] }; })
      .then(function (d) {
        products = Array.isArray(d.products) ? d.products : [];
        return products;
      })
      .catch(function () {
        products = [];
        return [];
      });
  }

  function collapseAllExcept(openIdx) {
    for (var i = 0; i < state.lines.length; i++) {
      state.lines[i].collapsed = (i !== openIdx);
    }
  }

  function packingOptions(line) {
    var o = '<option value=""></option>';
    (line.packing_styles || []).forEach(function (s) {
      o += '<option value="' + s.pkg_style_id + '" data-val="' + escHtml(String(s.pkg_style_value)) + '"' +
        (String(s.pkg_style_id) === String(line.pkg_style_id) ? ' selected' : '') + '>' +
        escHtml(s.pkg_style_name) + '</option>';
    });
    return o;
  }

  function fetchProductMeta(prodId) {
    return fetch(URL_PRODUCT_META + '?prod_id=' + encodeURIComponent(prodId), fetchOpts)
      .then(function (r) {
        if (!r.ok) return { error: true };
        return r.json();
      })
      .catch(function () {
        return { error: true };
      });
  }

  function updateEmptyVisibility() {
    if (lineEmpty) lineEmpty.style.display = state.lines.length ? 'none' : 'block';
  }

  function serialize() {
    var out = [];
    state.lines.forEach(function (line) {
      if (!line.prod_id) return;
      recalcLine(line);
      var disp = [];
      (line.dispatches || []).forEach(function (d) {
        disp.push({
          disp_sche_dt: d.disp_sche_dt || '',
          disp_qty: d.disp_qty != null ? String(d.disp_qty) : '',
          remarks: d.remarks != null ? String(d.remarks) : '',
        });
      });
      out.push({
        prod_id: parseInt(line.prod_id, 10),
        pkg_style_id: line.pkg_style_id ? parseInt(line.pkg_style_id, 10) : null,
        order_qty: line.order_qty,
        rate: line.rate,
        gst_type: line.gst_type || GST_CGST_SGST,
        gst_per: line.gst_type === GST_EXEMPTED ? '0' : String(line.gst_per || '0'),
        export_type: line.export_type || '',
        dispatches: disp,
      });
    });
    if (linesHidden) linesHidden.value = JSON.stringify(out);
    updateSaveState();
    refreshHeaderTotals();
  }

  function renderDispatchRow(lineIdx, didx, d) {
    var wrap = document.createElement('div');
    wrap.className = 'inw-batch-row';
    wrap.dataset.li = String(lineIdx);
    wrap.dataset.di = String(didx);
    wrap.innerHTML =
      '<div class="inw-br-field">' +
        '<label>Dispatch date <span class="req">*</span></label>' +
        '<input type="date" class="cu-input so-d-dt" value="' + escHtml(d.disp_sche_dt) + '">' +
      '</div>' +
      '<div class="inw-br-field inw-br-qty">' +
        '<label>Qty <span class="req">*</span></label>' +
        '<input type="number" class="cu-input so-d-qty" min="0.01" step="0.01" value="' +
        escHtml(d.disp_qty) + '">' +
      '</div>' +
      '<div class="inw-br-field inw-br-batchno">' +
        '<label>Remarks</label>' +
        '<input type="text" class="cu-input so-d-rem" maxlength="20" value="' + escHtml(d.remarks) + '">' +
      '</div>' +
      '<div class="inw-br-del">' +
        '<button type="button" class="btn-del-row so-remove-disp" title="Remove">' +
        '<i class="bi bi-x"></i></button></div>';

    var dt = wrap.querySelector('.so-d-dt');
    var qy = wrap.querySelector('.so-d-qty');
    var rm = wrap.querySelector('.so-d-rem');
    [dt, qy, rm].forEach(function (inp) {
      if (!inp) return;
      inp.addEventListener('change', function () { patchDispatch(lineIdx, didx); });
      inp.addEventListener('input', function () { patchDispatch(lineIdx, didx); });
    });
    wrap.querySelector('.so-remove-disp').addEventListener('click', function () {
      state.lines[lineIdx].dispatches.splice(didx, 1);
      if (!state.lines[lineIdx].dispatches.length) state.lines[lineIdx].dispatchExpanded = false;
      render();
      serialize();
    });
    return wrap;
  }

  function patchDispatch(lineIdx, didx) {
    var panel = lineList && lineList.querySelector('.so-dispatch-panel[data-idx="' + lineIdx + '"]');
    if (!panel) return;
    var row = panel.querySelector('.inw-batch-row[data-di="' + didx + '"]');
    if (!row) return;
    var ln = state.lines[lineIdx];
    if (!ln || !ln.dispatches[didx]) return;
    var d = ln.dispatches[didx];
    d.disp_sche_dt = (row.querySelector('.so-d-dt') || {}).value || '';
    d.disp_qty = (row.querySelector('.so-d-qty') || {}).value || '';
    d.remarks = (row.querySelector('.so-d-rem') || {}).value || '';
    serialize();
  }

  function onGstTypeChange(lineIdx, sel) {
    var ln = state.lines[lineIdx];
    if (!ln) return;
    ln.gst_type = sel.value || GST_CGST_SGST;
    if (ln.gst_type === GST_EXEMPTED) {
      ln.gst_per = '0';
    }
    render();
    serialize();
  }

  function onProductChange(idx, prodId) {
    var line = state.lines[idx];
    line.prod_id = prodId;
    line.pkg_style_id = '';
    line.pkg_style_value = null;
    line.hsn_code = '';
    line.packing_styles = [];
    line.export_type = line.export_type || '';
    if (!prodId) {
      render();
      serialize();
      return;
    }
    fetchProductMeta(prodId).then(function (meta) {
      if (meta.error) {
        render();
        serialize();
        return;
      }
      line.hsn_code = meta.hsn_code || '';
      line.packing_styles = meta.packing_styles || [];
      render();
      serialize();
    });
  }

  function onPkgChange(idx, sel) {
    var line = state.lines[idx];
    line.pkg_style_id = sel.value;
    var opt = sel.options[sel.selectedIndex];
    line.pkg_style_value = opt && opt.dataset ? opt.getAttribute('data-val') : null;
    if (line.pkg_style_value != null) line.pkg_style_value = parseInt(line.pkg_style_value, 10);
    serialize();
    render();
  }

  function render() {
    if (!lineList) return;
    if (typeof destroySearchableDropdownsIn === 'function') destroySearchableDropdownsIn(lineList);
    lineList.innerHTML = '';
    state.lines.forEach(function (line, idx) {
      recalcLine(line);
      var card = document.createElement('div');
      card.className = 'inw-line-card so-line-card';
      card.dataset.lineIdx = String(idx);

      var title = document.createElement('div');
      title.className = 'inw-line-title';
      title.textContent = 'Product ' + (idx + 1);

      // Accordion header row: toggle + remove button (outside collapsible body)
      var head = document.createElement('div');
      head.className = 'so-acc-head';

      var acc = document.createElement('button');
      acc.type = 'button';
      acc.className = 'so-acc-toggle' + (line.collapsed ? '' : ' is-open');
      acc.setAttribute('aria-expanded', line.collapsed ? 'false' : 'true');
      acc.dataset.idx = String(idx);
      var prodName = getProductName(line.prod_id);
      acc.innerHTML =
        '<span class="so-acc-icon"><i class="bi bi-chevron-down"></i></span>' +
        '<span class="so-acc-text">' + (prodName ? escHtml(prodName) : 'Select Product') + '</span>' +
        '<span class="so-acc-meta">' + escHtml('Product ' + (idx + 1)) + '</span>';

      var rm = document.createElement('button');
      rm.type = 'button';
      rm.className = 'so-acc-remove so-remove-line';
      rm.dataset.idx = String(idx);
      rm.title = 'Remove product';
      rm.innerHTML = '<i class="bi bi-x"></i>';

      head.appendChild(acc);
      head.appendChild(rm);
      card.appendChild(head);

      var gstPerDisabled = line.gst_type === GST_EXEMPTED ? ' disabled tabindex="-1"' : '';
      var gstPerVal = line.gst_type === GST_EXEMPTED ? '0' : escHtml(line.gst_per);

      var body = document.createElement('div');
      body.className = 'so-acc-body';
      body.style.display = line.collapsed ? 'none' : 'block';

      var main = document.createElement('div');
      main.className = 'inw-line-main';
      main.innerHTML =
        '<div class="inw-cell inw-cell-item so-cell-product">' +
          '<label>Product <span class="req">*</span></label>' +
          '<select class="cu-select searchable-dropdown so-prod-select" data-idx="' + idx + '">' +
          productOptions(line.prod_id) + '</select></div>' +
        '<div class="inw-cell so-cell-hsn">' +
          '<label>HSN <span class="req">*</span></label>' +
          '<input type="text" class="cu-input so-hsn" readonly tabindex="-1" value="' +
          escHtml(line.hsn_code) + '"></div>' +
        '<div class="inw-cell so-cell-pack">' +
          '<label>Packing style <span class="req">*</span></label>' +
          '<select class="cu-select searchable-dropdown so-pkg-select" data-idx="' + idx + '">' +
          packingOptions(line) + '</select></div>' +
        '<div class="inw-cell so-cell-oqty"><label>Order qty/lakh <span class="req">*</span></label>' +
          '<input type="number" class="cu-input so-oqty" min="0.01" step="0.01" data-idx="' + idx +
          '" value="' + escHtml(line.order_qty) + '"></div>' +
        '<div class="inw-cell so-cell-rate"><label>Rate <span class="req">*</span></label>' +
          '<input type="number" class="cu-input so-rate" min="0.01" step="0.01" data-idx="' + idx +
          '" value="' + escHtml(line.rate) + '"></div>' +
        '<div class="inw-cell so-cell-export">' +
          '<label>Export type <span class="req">*</span></label>' +
          '<input type="text" class="cu-input so-export" maxlength="100" data-idx="' + idx +
          '" value="' + escHtml(line.export_type) + '"></div>' +
        '<div class="inw-cell so-cell-ordnos"><label>Ord. qty (nos.)</label>' +
          '<input type="text" class="cu-input cu-num" readonly tabindex="-1" value="' +
          intStr(line.ord_qty_nos) + '"></div>' +
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
          '<input type="text" class="cu-input cu-num" readonly tabindex="-1" value="' + moneyStr(line.igst_amt) + '"></div>' +
        '<div class="inw-cell so-cell-prod-amt"><label>Product amount</label>' +
          '<input type="text" class="cu-input cu-num" readonly tabindex="-1" value="' + moneyStr(line.prod_amt) + '"></div>' +
        '';

      body.appendChild(main);

      var n = (line.dispatches && line.dispatches.length) ? line.dispatches.length : 0;
      var bar = document.createElement('button');
      bar.type = 'button';
      bar.className = 'inw-batch-toggle' + (line.dispatchExpanded ? ' is-open' : '');
      bar.setAttribute('aria-expanded', line.dispatchExpanded ? 'true' : 'false');
      bar.dataset.idx = String(idx);
      bar.innerHTML =
        '<span class="inw-batch-toggle-icon"><i class="bi bi-chevron-down"></i></span>' +
        '<span class="inw-batch-toggle-text">Dispatch</span>' +
        (n ? '<span class="inw-batch-count">' + n + '</span>' : '');
      body.appendChild(bar);

      var panel = document.createElement('div');
      panel.className = 'inw-batch-panel so-dispatch-panel';
      panel.style.display = line.dispatchExpanded ? 'block' : 'none';
      panel.dataset.idx = String(idx);
      var inner = document.createElement('div');
      inner.className = 'inw-batch-inner';
      (line.dispatches || []).forEach(function (d, didx) {
        inner.appendChild(renderDispatchRow(idx, didx, d));
      });
      var addBtn = document.createElement('button');
      addBtn.type = 'button';
      addBtn.className = 'inw-add-batch';
      addBtn.dataset.idx = String(idx);
      addBtn.innerHTML = '<i class="bi bi-plus-lg"></i><span>Add dispatch</span>';
      panel.appendChild(inner);
      panel.appendChild(addBtn);
      body.appendChild(panel);

      card.appendChild(body);

      bar.addEventListener('click', function () {
        var i = parseInt(bar.dataset.idx, 10);
        var ln = state.lines[i];
        if (!ln) return;
        ln.dispatchExpanded = !ln.dispatchExpanded;
        render();
        serialize();
      });
      addBtn.addEventListener('click', function () {
        var i = parseInt(addBtn.dataset.idx, 10);
        var ln = state.lines[i];
        if (!ln) return;
        if (!ln.dispatches) ln.dispatches = [];
        ln.dispatches.push({ disp_sche_dt: '', disp_qty: '', remarks: '' });
        ln.dispatchExpanded = true;
        render();
        serialize();
      });

      lineList.appendChild(card);

      acc.addEventListener('click', function () {
        var i = parseInt(acc.dataset.idx, 10);
        var ln = state.lines[i];
        if (!ln) return;
        var willOpen = !!ln.collapsed;
        if (willOpen) {
          collapseAllExcept(i);
        } else {
          ln.collapsed = true;
        }
        render();
        serialize();
      });

      var psel = card.querySelector('.so-prod-select');
      if (psel) {
        psel.addEventListener('change', function () {
          onProductChange(idx, psel.value);
        });
      }
      var pkSel = card.querySelector('.so-pkg-select');
      if (pkSel) {
        pkSel.addEventListener('change', function () {
          onPkgChange(idx, pkSel);
        });
      }
      var oq = card.querySelector('.so-oqty');
      if (oq) {
        oq.addEventListener('input', function () {
          state.lines[idx].order_qty = oq.value;
          serialize();
          scheduleRender();
        });
        oq.addEventListener('change', function () {
          state.lines[idx].order_qty = oq.value;
          serialize();
          render();
        });
      }

      var rt = card.querySelector('.so-rate');
      if (rt) {
        rt.addEventListener('input', function () {
          state.lines[idx].rate = rt.value;
          serialize();
          scheduleRender();
        });
        rt.addEventListener('change', function () {
          state.lines[idx].rate = rt.value;
          serialize();
          render();
        });
      }

      var gp = card.querySelector('.so-gst-per');
      if (gp) {
        gp.addEventListener('input', function () {
          state.lines[idx].gst_per = gp.value;
          serialize();
          scheduleRender();
        });
        gp.addEventListener('change', function () {
          state.lines[idx].gst_per = gp.value;
          serialize();
          render();
        });
      }

      var ex = card.querySelector('.so-export');
      if (ex) {
        ex.addEventListener('input', function () {
          state.lines[idx].export_type = ex.value;
          serialize();
          // No render needed while typing.
        });
        ex.addEventListener('change', function () {
          state.lines[idx].export_type = ex.value;
          serialize();
        });
      }
      var gt = card.querySelector('.so-gst-type');
      if (gt) {
        gt.addEventListener('change', function () {
          onGstTypeChange(idx, gt);
        });
      }
      card.querySelectorAll('.so-remove-line').forEach(function (btn) {
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

  // Debounced render for typing-heavy inputs to avoid focus/caret loss.
  // We update state + serialize immediately, but only rerender after the user pauses.
  var _renderTimer = null;
  var _RENDER_DEBOUNCE_MS = 450;
  function scheduleRender() {
    if (_renderTimer) {
      clearTimeout(_renderTimer);
      _renderTimer = null;
    }
    _renderTimer = setTimeout(function () {
      _renderTimer = null;
      render();
    }, _RENDER_DEBOUNCE_MS);
  }

  function addLine() {
    setLinesErr('');
    state.lines.push({
      prod_id: '',
      pkg_style_id: '',
      pkg_style_value: null,
      hsn_code: '',
      packing_styles: [],
      order_qty: '',
      rate: '',
      gst_type: GST_CGST_SGST,
      gst_per: '',
      export_type: '',
      dispatches: [],
      dispatchExpanded: false,
      taxable_amt: 0,
      ord_qty_nos: 0,
      cgst_amt: 0,
      sgst_amt: 0,
      igst_amt: 0,
      prod_amt: 0,
      collapsed: state.lines.length > 0,
    });
    collapseAllExcept(state.lines.length - 1);
    render();
  }

  function prepareLinesForSubmit(showErr) {
    setLinesErr('');
    serialize();
    var raw = (linesHidden && linesHidden.value) ? linesHidden.value.trim() : '';
    if (!raw || raw === '[]') {
      if (showErr) setLinesErr('Add at least one product line.');
      return false;
    }
    try {
      var rows = JSON.parse(raw);
      if (!Array.isArray(rows) || !rows.length) {
        if (showErr) setLinesErr('Add at least one product line.');
        return false;
      }
    } catch (e) {
      if (showErr) setLinesErr('Invalid line data.');
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

  window.goToSoProducts = function () {
    setLinesErr('');
    setStep(2);
  };

  window.goBackSoHeader = function () {
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
  if (btnNext) btnNext.addEventListener('click', function () { window.goToSoProducts(); });
  if (btnBack) btnBack.addEventListener('click', function () { window.goBackSoHeader(); });

  ['soPkgFwd', 'soFreight', 'soOthCharges', 'soRoundOff'].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) {
      el.addEventListener('input', refreshHeaderTotals);
      el.addEventListener('change', refreshHeaderTotals);
    }
  });

  window.resetSalesOrderForm = function () {
    if (typeof clearMasterFormValidationUI === 'function') clearMasterFormValidationUI(form);
    form.querySelectorAll('input, select, textarea').forEach(function (el) {
      if (el.type === 'hidden') return;
      if (el.id === 'soLinesJson') return;
      if (el.type === 'file') {
        el.value = '';
        revokeDocBlobUrl();
        hideDocPreviewLayers();
        return;
      }
      if (el.readOnly && (el.id || '').indexOf('soRo') === 0) return;
      if (el.tagName === 'SELECT') {
        el.selectedIndex = 0;
      } else if (el.type === 'checkbox' || el.type === 'radio') {
        el.checked = false;
      } else {
        el.value = '';
      }
    });
    var ordDt = document.getElementById('soOrdRecDt');
    if (ordDt) {
      var today = new Date();
      ordDt.value = today.getFullYear() + '-' +
        String(today.getMonth() + 1).padStart(2, '0') + '-' +
        String(today.getDate()).padStart(2, '0');
    }
    var editPkInput = form.querySelector('input[name="edit_pk"]');
    if (editPkInput) editPkInput.remove();
    form.action = form.action.split('?')[0];
    state.lines = [];
    if (linesHidden) linesHidden.value = '';
    setLinesErr('');
    if (docHint) docHint.textContent = DOC_HINT_DEFAULT;
    revokeDocBlobUrl();
    hideDocPreviewLayers();
    if (previewShell) delete previewShell.dataset.existingSrc;
    render();
    isEdit = false;
    setStep(1);
  };

  form.addEventListener('submit', function (e) {
    if (!prepareLinesForSubmit(true)) e.preventDefault();
  });

  if (btnSave) {
    btnSave.addEventListener('click', function (e) {
      if (btnSave.getAttribute('aria-disabled') === 'true' || !hasAtLeastOneProduct()) {
        e.preventDefault();
        setLinesErr('Add at least one product line.');
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

  function normalizeDispatchFromJson(d) {
    return {
      disp_sche_dt: d.disp_sche_dt != null ? String(d.disp_sche_dt) : '',
      disp_qty: d.disp_qty != null ? String(d.disp_qty) : '',
      remarks: d.remarks != null ? String(d.remarks) : '',
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

    state.lines = [];
    var tasks = [];
    parsed.forEach(function (row) {
      var disp = Array.isArray(row.dispatches)
        ? row.dispatches.map(normalizeDispatchFromJson)
        : [];
      var line = {
        prod_id: row.prod_id || '',
        pkg_style_id: row.pkg_style_id || '',
        pkg_style_value: null,
        hsn_code: '',
        packing_styles: [],
        order_qty: row.order_qty != null ? String(row.order_qty) : '',
        rate: row.rate != null ? String(row.rate) : '',
        gst_type: row.gst_type || GST_CGST_SGST,
        gst_per: row.gst_per != null ? String(row.gst_per) : '',
        export_type: row.export_type != null ? String(row.export_type) : '',
        dispatches: disp,
        dispatchExpanded: disp.length > 0,
        taxable_amt: 0,
        ord_qty_nos: 0,
        cgst_amt: 0,
        sgst_amt: 0,
        igst_amt: 0,
        prod_amt: 0,
        collapsed: false,
      };
      state.lines.push(line);
      if (line.prod_id) {
        tasks.push(
          fetchProductMeta(line.prod_id).then(function (meta) {
            if (meta.error) return;
            line.hsn_code = meta.hsn_code || '';
            line.packing_styles = meta.packing_styles || [];
            (line.packing_styles || []).forEach(function (s) {
              if (String(s.pkg_style_id) === String(line.pkg_style_id)) {
                line.pkg_style_value = s.pkg_style_value;
              }
            });
          })
        );
      }
    });
    return Promise.all(tasks).then(function () {
      if (state.lines.length > 1) collapseAllExcept(0);
      render();
    });
  }

  var custSel = document.getElementById('soCustomer');

  hydrateFromHidden().then(function () {
    if (!state.lines.length) render();
    var ss = parseInt(pageData.startStep, 10) || 1;
    setStep(ss === 2 ? 2 : 1);
    updateSaveState();
    refreshHeaderTotals();
    var cid = custSel ? custSel.value : '';
    return loadProductsForCustomer(cid);
  }).then(function () {
    render();
    serialize();
  });

  // Customer-filtered products: reload product list when customer changes.
  function onCustomerChanged() {
    var cid = custSel ? custSel.value : '';
    loadProductsForCustomer(cid).then(function () {
      // Clear lines when customer changes to avoid invalid products.
      state.lines = [];
      render();
      serialize();
    });
  }
  if (custSel) {
    custSel.addEventListener('change', onCustomerChanged);
    custSel.addEventListener('input', onCustomerChanged);
  }
}

window.initPage_sales_order = initPage_sales_order;
