/**
 * Batch allocation — customer → order → product → batch params → preview → submit.
 */
(function () {
  'use strict';

  var MMM_RE = /^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)-(\d{4})$/i;
  var YM_RE = /^(\d{4})-(\d{2})$/;
  var MON = { JAN: 1, FEB: 2, MAR: 3, APR: 4, MAY: 5, JUN: 6, JUL: 7, AUG: 8, SEP: 9, OCT: 10, NOV: 11, DEC: 12 };

  function readJsonScript(id) {
    var el = document.getElementById(id);
    if (!el || !el.textContent) return {};
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return {};
    }
  }

  function mmmKey(s) {
    if (!s) return null;
    var raw = String(s).trim();
    var m1 = raw.toUpperCase().match(MMM_RE);
    if (m1) {
      var mo1 = MON[m1[1]];
      var y1 = parseInt(m1[2], 10);
      return y1 * 100 + mo1;
    }
    var m2 = raw.match(YM_RE);
    if (m2) {
      var y2 = parseInt(m2[1], 10);
      var mo2 = parseInt(m2[2], 10);
      if (!y2 || !mo2 || mo2 < 1 || mo2 > 12) return null;
      return y2 * 100 + mo2;
    }
    return null;
  }

  function monthInputToMmm(ym) {
    if (!ym || ym.indexOf('-') < 0) return '';
    var p = ym.split('-');
    var y = parseInt(p[0], 10);
    var mo = parseInt(p[1], 10);
    if (!y || !mo) return '';
    var d = new Date(y, mo - 1, 1);
    var mon = d.toLocaleString('en-US', { month: 'short' }).toUpperCase();
    return mon + '-' + y;
  }

  function monthLabel(val) {
    if (!val) return '';
    var s = String(val).trim();
    if (MMM_RE.test(s)) return s.toUpperCase();
    if (YM_RE.test(s)) return monthInputToMmm(s);
    return s;
  }

  /** Remaining order qty display: Lacs max 2 dp; Nos whole number. */
  function formatOrderQtyLDisplay(raw) {
    if (raw == null || String(raw).trim() === '') return '—';
    var x = parseFloat(String(raw).replace(',', '.'));
    if (!isFinite(x)) return String(raw);
    return String(parseFloat(x.toFixed(2)));
  }

  function formatOrderQtyNDisplay(raw) {
    if (raw == null || String(raw).trim() === '') return '—';
    var x = parseFloat(String(raw).replace(',', '.'));
    if (!isFinite(x)) return String(raw);
    return String(Math.round(x));
  }

  function ladderQuantities(target, size, count) {
    var t = Number(target);
    var sz = Number(size);
    if (!count || count < 1) return { ok: false, reason: 'range' };
    if (t === 0 && sz === 0) {
      var z = [];
      for (var i = 0; i < count; i++) z.push(0);
      return { ok: true, rows: z };
    }
    if (!(sz > 0)) return { ok: false, reason: 'size' };
    var last = t - sz * (count - 1);
    if (!(last > 0) || last > sz + 1e-9) return { ok: false, reason: 'fit' };
    var rows = [];
    for (var j = 0; j < count - 1; j++) rows.push(sz);
    rows.push(last);
    return { ok: true, rows: rows };
  }

  function setSectionDisabled(el, dis) {
    if (!el) return;
    if (dis) el.classList.add('ba-section-disabled');
    else el.classList.remove('ba-section-disabled');
    var hard = el.getAttribute('data-ba-hard-disable') === '1';
    if (!hard) return;
    el.querySelectorAll('input,select,button,textarea').forEach(function (n) {
      if (n.id === 'baCustomer') return;
      if (n.type === 'hidden') {
        n.disabled = false;
        return;
      }
      n.disabled = !!dis;
    });
  }

  function initPage_batch_allocation() {
    var root = document.querySelector('.batch-allocation-page');
    if (!root) return;

    var urls = readJsonScript('baAjaxUrls');
    var customer = document.getElementById('baCustomer');
    var orderSelect = document.getElementById('baOrderSelect');
    var orderHidden = document.getElementById('baOrderId');
    var productSelect = document.getElementById('baProductSelect');
    var orderLineHidden = document.getElementById('baOrderLineId');
    var ordDate = document.getElementById('baOrdDateDisplay');
    var ordRemarks = document.getElementById('baOrdRemarks');
    var abbrEl = document.getElementById('baAbbrText');
    var orderQtyL = document.getElementById('baDispOrderQtyL');
    var orderQtyN = document.getElementById('baDispOrderQtyN');
    var exportType = document.getElementById('baDispExportType');
    var partialCb = document.getElementById('baPartialYn');
    var partialL = document.getElementById('baPartialL');
    var partialN = document.getElementById('baPartialN');
    var batchSizeL = document.getElementById('baBatchSizeL');
    var batchSizeN = document.getElementById('baBatchSizeN');
    var batchFrom = document.getElementById('baBatchFrom');
    var batchTo = document.getElementById('baBatchTo');
    var mfg = document.getElementById('baMfgDt');
    var exp = document.getElementById('baExpDt');
    var previewBody = document.getElementById('baPreviewBody');
    var prevBody = document.getElementById('baPrevBody');
    var createBtn = document.getElementById('baCreateBtn');
    var secOrder = document.getElementById('baSecOrder');
    var secProduct = document.getElementById('baSecProduct');
    var secBatch = document.getElementById('baSecBatch');
    var form = document.getElementById('baForm');
    var errForm = document.getElementById('err-baForm');

    var state = {
      orderQtyL: null,
      orderQtyN: null,
      abbr: '',
      abbrOk: false,
    };

    function deriveNosFromLacs(lacsVal) {
      var v = Number(lacsVal);
      if (!(v >= 0)) return '';
      var out = v * 100000;
      return String(Math.round(out));
    }

    function syncNosInputs() {
      if (!batchSizeN || !partialN) return;
      batchSizeN.value = deriveNosFromLacs(batchSizeL.value);
      partialN.value = partialCb.checked ? deriveNosFromLacs(partialL.value) : '';
      batchSizeN.disabled = true;
      partialN.disabled = true;
    }

    function rebindSearchableSelect(sel) {
      if (typeof destroySearchableDropdownsIn === 'function') destroySearchableDropdownsIn(sel);
      if (typeof initSearchableDropdowns === 'function') initSearchableDropdowns(sel);
    }

    function resetFromOrder() {
      if (typeof destroySearchableDropdownsIn === 'function') {
        destroySearchableDropdownsIn(orderSelect);
        destroySearchableDropdownsIn(productSelect);
      }
      orderSelect.innerHTML = '<option value="">— Select order —</option>';
      orderHidden.value = '';
      productSelect.innerHTML = '<option value="">— Select product —</option>';
      if (orderLineHidden) orderLineHidden.value = '';
      ordDate.value = '';
      ordRemarks.value = '';
      if (abbrEl) abbrEl.value = '—';
      if (orderQtyL) orderQtyL.value = '—';
      if (orderQtyN) orderQtyN.value = '—';
      if (exportType) exportType.value = '—';
      state.orderQtyL = state.orderQtyN = null;
      state.abbr = '';
      state.abbrOk = false;
      resetFromProduct();
      rebindSearchableSelect(orderSelect);
      rebindSearchableSelect(productSelect);
    }

    function resetFromProduct() {
      partialCb.checked = false;
      partialL.value = '';
      partialN.value = '';
      batchSizeL.value = '';
      batchSizeN.value = '';
      batchFrom.value = '';
      batchTo.value = '';
      mfg.value = '';
      exp.value = '';
      previewBody.innerHTML = '';
      prevBody.innerHTML = '<tr><td colspan="4" class="ba-muted">Select a product…</td></tr>';
      updatePartialRow();
      syncNosInputs();
      updatePreview();
      updateCreateBtn();
    }

    function updatePartialRow() {
      var on = partialCb.checked;
      partialL.disabled = !on;
      // partial nos is always computed; keep disabled.
      partialN.disabled = true;
      syncNosInputs();
    }

    function currentTargets() {
      var ol = Number(state.orderQtyL);
      if (partialCb.checked) {
        return {
          l: partialL.value === '' ? NaN : Number(partialL.value),
        };
      }
      return { l: ol };
    }

    function updatePreview() {
      previewBody.innerHTML = '';
      var abbr = state.abbr;
      var bf = parseInt(batchFrom.value, 10);
      var bt = parseInt(batchTo.value, 10);
      var bsl = Number(batchSizeL.value);
      if (!abbr || !state.abbrOk || !bf || !bt || bt < bf) return;

      var count = bt - bf + 1;
      var tg = currentTargets();
      if (isNaN(tg.l) || tg.l < 0) return;

      var ladderL = ladderQuantities(tg.l, bsl, count);
      var ladderN = ladderQuantities(tg.l * 100000, bsl * 100000, count);
      if (!ladderL.ok || !ladderN.ok) return;

      for (var i = 0; i < count; i++) {
        var seq = bf + i;
        var tr = document.createElement('tr');
        tr.innerHTML =
          '<td>' +
          abbr +
          seq +
          '</td><td>' +
          monthLabel(mfg.value || '') +
          '</td><td>' +
          monthLabel(exp.value || '') +
          '</td><td>' +
          ladderL.rows[i] +
          ' L / ' +
          ladderN.rows[i] +
          ' Nos</td>';
        previewBody.appendChild(tr);
      }
    }

    function updateCreateBtn() {
      if (!createBtn) return;
      var ok = true;
      if (!customer.value) ok = false;
      if (!orderHidden.value) ok = false;
      if (!productSelect.value) ok = false;
      if (!orderLineHidden || !orderLineHidden.value) ok = false;
      if (!state.abbrOk) ok = false;

      var tg = currentTargets();
      if (partialCb.checked) {
        if (isNaN(tg.l) || tg.l <= 0) ok = false;
      }

      var bf = parseInt(batchFrom.value, 10);
      var bt = parseInt(batchTo.value, 10);
      if (!bf || !bt || bt < bf) ok = false;

      var bsl = Number(batchSizeL.value);
      if (!(bsl > 0)) ok = false;

      var mfgRaw = (mfg.value || '').trim();
      var expRaw = (exp.value || '').trim();
      if (!(MMM_RE.test(mfgRaw) || YM_RE.test(mfgRaw))) ok = false;
      if (!(MMM_RE.test(expRaw) || YM_RE.test(expRaw))) ok = false;

      var km = mmmKey(mfg.value);
      var ke = mmmKey(exp.value);
      if (km === null || ke === null || ke <= km) ok = false;

      var count = bt - bf + 1;
      var ladderL = ladderQuantities(tg.l, bsl, count);
      var ladderN = ladderQuantities(tg.l * 100000, bsl * 100000, count);
      if (!ladderL.ok || !ladderN.ok) ok = false;

      createBtn.setAttribute('aria-disabled', ok ? 'false' : 'true');
    }

    function loadOrders() {
      resetFromOrder();
      var cid = customer.value;
      if (!cid) {
        setSectionDisabled(secOrder, true);
        setSectionDisabled(secProduct, true);
        setSectionDisabled(secBatch, true);
        return;
      }
      setSectionDisabled(secOrder, false);
      // Ensure the order dropdown is enabled (initial HTML has disabled attr).
      if (orderSelect) orderSelect.disabled = false;
      setSectionDisabled(secProduct, true);
      setSectionDisabled(secBatch, true);
      fetch(urls.orders + '?cust_id=' + encodeURIComponent(cid), { credentials: 'same-origin' })
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          (data.orders || []).forEach(function (o) {
            var opt = document.createElement('option');
            opt.value = o.order_id;
            opt.textContent = o.cust_ord_id + ' · ' + (o.ord_rec_dt || '');
            orderSelect.appendChild(opt);
          });
          rebindSearchableSelect(orderSelect);
        })
        .catch(function () {});
    }

    function loadOrderDetailAndProducts() {
      resetFromProduct();
      if (typeof destroySearchableDropdownsIn === 'function') destroySearchableDropdownsIn(productSelect);
      productSelect.innerHTML = '<option value="">— Select product —</option>';
      if (orderLineHidden) orderLineHidden.value = '';
      var cid = customer.value;
      var oid = orderSelect.value;
      orderHidden.value = oid || '';
      if (!cid || !oid) {
        ordDate.value = '';
        ordRemarks.value = '';
        setSectionDisabled(secProduct, true);
        setSectionDisabled(secBatch, true);
        rebindSearchableSelect(productSelect);
        return;
      }
      fetch(
        urls.orderDetail + '?cust_id=' + encodeURIComponent(cid) + '&order_id=' + encodeURIComponent(oid),
        { credentials: 'same-origin' },
      )
        .then(function (r) {
          return r.json();
        })
        .then(function (d) {
          if (d.error) return;
          ordDate.value = d.ord_rec_dt || '';
          ordRemarks.value = d.remarks || '';
        })
        .catch(function () {});

      fetch(
        urls.products + '?cust_id=' + encodeURIComponent(cid) + '&order_id=' + encodeURIComponent(oid),
        { credentials: 'same-origin' },
      )
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          (data.lines || []).forEach(function (ln) {
            var opt = document.createElement('option');
            opt.value = ln.prod_id;
            opt.textContent = ln.prod_name + (ln.packing_style ? (' · ' + ln.packing_style) : '') + (ln.rate ? (' · Rate ' + ln.rate) : '');
            opt.dataset.lineId = ln.dtl1_id;
            opt.dataset.qtyL = ln.remaining_qty_l;
            opt.dataset.qtyN = ln.remaining_qty_n;
            opt.dataset.export = ln.export_type || '';
            opt.dataset.abbr = ln.batch_abbr || '';
            opt.dataset.abbrOk = ln.abbr_ok ? '1' : '0';
            productSelect.appendChild(opt);
          });
          setSectionDisabled(secProduct, false);
          rebindSearchableSelect(productSelect);
        })
        .catch(function () {
          rebindSearchableSelect(productSelect);
        });
      setSectionDisabled(secBatch, true);
    }

    function onProductChange() {
      resetFromProduct();
      var opt = productSelect.selectedOptions[0];
      var pid = productSelect.value;
      if (orderLineHidden) orderLineHidden.value = (opt && opt.dataset ? (opt.dataset.lineId || '') : '');
      if (!opt || !pid) {
        setSectionDisabled(secBatch, true);
        updateCreateBtn();
        return;
      }
      state.orderQtyL = parseFloat(opt.dataset.qtyL || '0');
      state.orderQtyN = parseFloat(opt.dataset.qtyN || '0');
      if (isNaN(state.orderQtyL)) state.orderQtyL = 0;
      if (isNaN(state.orderQtyN)) state.orderQtyN = 0;
      if (orderQtyL) orderQtyL.value = formatOrderQtyLDisplay(opt.dataset.qtyL);
      if (orderQtyN) orderQtyN.value = formatOrderQtyNDisplay(opt.dataset.qtyN);
      if (exportType) exportType.value = opt.dataset.export || '—';
      state.abbr = (opt.dataset.abbr || '').toUpperCase();
      state.abbrOk = opt.dataset.abbrOk === '1';
      if (abbrEl) abbrEl.value = state.abbr || '—';
      syncNosInputs();
      // keep Nos in sync even while typing

      var oid = orderHidden.value;
      var lineId = orderLineHidden ? orderLineHidden.value : '';
      fetch(
        urls.previousBatches + '?order_id=' + encodeURIComponent(oid) + '&line_id=' + encodeURIComponent(lineId),
        { credentials: 'same-origin' },
      )
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          prevBody.innerHTML = '';
          var rows = data.batches || [];
          if (!rows.length) {
            prevBody.innerHTML = '<tr><td colspan="4" class="ba-muted">No previous batches</td></tr>';
            if (batchFrom && !batchFrom.value) batchFrom.value = '1';
            if (batchTo && !batchTo.value) batchTo.value = batchFrom.value;
            return;
          }
          // Auto-fill Batch From based on latest batch number.
          var maxSeq = 0;
          rows.forEach(function (b) {
            var bn = String(b.batch_no || '');
            if (bn.indexOf(state.abbr) === 0) {
              var n = parseInt(bn.slice(state.abbr.length), 10);
              if (n > maxSeq) maxSeq = n;
            }
          });
          var nextSeq = maxSeq ? (maxSeq + 1) : 1;
          if (batchFrom && !batchFrom.value) batchFrom.value = String(nextSeq);
          if (batchTo && !batchTo.value) batchTo.value = batchFrom.value;
          rows.forEach(function (b) {
            var tr = document.createElement('tr');
            tr.innerHTML =
              '<td>' +
              b.batch_no +
              '</td><td>' +
              b.mfg_dt +
              '</td><td>' +
              b.exp_dt +
              '</td><td>' +
              b.batch_qty_l +
              ' L / ' +
              b.batch_qty_n +
              ' Nos</td>';
            prevBody.appendChild(tr);
          });
        })
        .catch(function () {
          prevBody.innerHTML = '<tr><td colspan="4" class="ba-muted">Could not load</td></tr>';
        });

      setSectionDisabled(secBatch, !state.abbrOk);
      updatePreview();
      updateCreateBtn();
    }

    // Some searchable-dropdown wrappers trigger input events; handle both.
    customer.addEventListener('change', loadOrders);
    customer.addEventListener('input', loadOrders);
    orderSelect.addEventListener('change', loadOrderDetailAndProducts);
    productSelect.addEventListener('change', onProductChange);
    partialCb.addEventListener('change', function () {
      updatePartialRow();
      updatePreview();
      updateCreateBtn();
    });

    [partialL, partialN, batchSizeL, batchSizeN, batchFrom, batchTo, mfg, exp].forEach(function (el) {
      if (el) el.addEventListener('input', updateDebounced);
      if (el) el.addEventListener('change', updateDebounced);
    });

    var tmr;
    function updateDebounced() {
      clearTimeout(tmr);
      tmr = setTimeout(function () {
        syncNosInputs();
        updatePreview();
        updateCreateBtn();
      }, 80);
    }

    if (form) {
      form.addEventListener('submit', function (e) {
        updateCreateBtn();
        var dis = createBtn.getAttribute('aria-disabled') === 'true';
        if (dis) {
          e.preventDefault();
          if (errForm) {
            errForm.textContent = 'Please select customer, order, product and fill required batch details before creating batches.';
          }
          return;
        }
        if (errForm) errForm.textContent = '';
        createBtn.setAttribute('aria-disabled', 'true');
      });
    }

    // Initial state.
    setSectionDisabled(secOrder, true);
    setSectionDisabled(secProduct, true);
    setSectionDisabled(secBatch, true);
    if (customer.value) {
      loadOrders();
      setSectionDisabled(secOrder, false);
    }
    updatePartialRow();
    updateCreateBtn();
  }

  window.initPage_batch_allocation = initPage_batch_allocation;
})();
