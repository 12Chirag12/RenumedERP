/**
 * Transaction Command Center — dashboard.js
 * Comprehensive interactive executive controller:
 * - Two distinct operational modes: Quick Periods vs Selected Time Period (Custom Range)
 * - Strict interactive client-side date validation (From/To missing, From > To checks)
 * - Timezone-safe local date formatting without UTC offset drift
 * - In-table instant text filtering across all columns with DYNAMIC TOTALS RECALCULATION
 * - Total row calculation for every numeric column in tfoot and footer strips
 * - Fixed date formatting to prevent 'Invalid Date' and Excel '########' column clipping
 * - 1-Click Excel (.xls) and CSV export with full auto-width and bold totals
 * - Zero-flicker full screen maximize / minimize (with Esc key support)
 */

var DD = (function () {
  'use strict';

  var currentMode = 'quick'; // 'quick' or 'custom'
  var currentPreset = 'month';

  // In-memory data store for live filtering and instant recalculations
  var DATA_STORE = {
    inward: [],
    logsheet: [],
    dispensing: [],
    dpr: [],
    packing: [],
    orders: [],
    sales: [],
    stock: []
  };

  // ── Date & Number Formatting Utilities ──
  function formatLocalISO(d) {
    if (!d || isNaN(d.getTime())) return '';
    var year = d.getFullYear();
    var month = String(d.getMonth() + 1).padStart(2, '0');
    var day = String(d.getDate()).padStart(2, '0');
    return year + '-' + month + '-' + day;
  }

  function fmtDate(iso) {
    if (!iso || iso === '—' || iso === 'None' || iso === 'null' || iso === 'undefined') return '—';
    try {
      var s = String(iso).trim();
      // If already in Month-Year format (e.g. 'MAR-2026', 'SEP-2029')
      if (/^[A-Za-z]{3}-\d{2,4}$/.test(s)) {
        return s;
      }
      var clean = s.split('T')[0];
      var parts = clean.split('-');
      if (parts.length === 3) {
        var y = parseInt(parts[0], 10);
        var m = parseInt(parts[1], 10) - 1;
        var d = parseInt(parts[2], 10);
        var dateObj = new Date(y, m, d);
        if (!isNaN(dateObj.getTime())) {
          return dateObj.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
        }
      }
      var fallback = new Date(s);
      if (!isNaN(fallback.getTime())) {
        return fallback.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
      }
      return '—';
    } catch (e) {
      return '—';
    }
  }

  function fmtNum(n) {
    if (n === null || n === undefined || isNaN(n)) return '0';
    return Number(n).toLocaleString('en-IN');
  }

  function fmtQty(n) {
    if (n === null || n === undefined || isNaN(n)) return '0.00';
    var num = Number(n);
    return num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 3 });
  }

  function fmtCurrency(n) {
    if (n === null || n === undefined || isNaN(n)) return '₹ 0.00';
    return '₹ ' + Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function getRange() {
    var f = document.getElementById('ddFromDate');
    var t = document.getElementById('ddToDate');
    var fromVal = f && f.value ? f.value.trim() : '';
    var toVal = t && t.value ? t.value.trim() : '';

    var params = {};
    if (currentPreset === 'all') {
      params.all = '1';
    } else {
      if (fromVal) params.from_date = fromVal;
      if (toVal) params.to_date = toVal;
    }
    return params;
  }

  function qs(url, params) {
    var parts = [];
    for (var k in params) {
      if (params[k]) parts.push(k + '=' + encodeURIComponent(params[k]));
    }
    return url + (parts.length ? '?' + parts.join('&') : '');
  }

  function showEl(id) {
    var e = document.getElementById(id);
    if (e) e.style.display = '';
  }

  function hideEl(id) {
    var e = document.getElementById(id);
    if (e) e.style.display = 'none';
  }

  function setText(id, txt) {
    var e = document.getElementById(id);
    if (e) e.textContent = txt;
  }

  function esc(s) {
    if (!s) return '';
    var d = document.createElement('div');
    d.textContent = String(s);
    return d.innerHTML;
  }

  function updateActivePeriodBadge(fromISO, toISO) {
    if (currentPreset === 'all') {
      setText('ddActivePeriodText', 'All Time (Complete Ledger History)');
      return;
    }
    var text = fmtDate(fromISO) + ' – ' + fmtDate(toISO);
    setText('ddActivePeriodText', text);
  }

  function showToast() {
    var toast = document.getElementById('ddFilterSuccessToast');
    if (!toast) return;
    toast.style.display = 'inline-flex';
    setTimeout(function () {
      toast.style.display = 'none';
    }, 2200);
  }

  // ── Validation System ──
  function validateSelectedDates(fromVal, toVal) {
    var fromInput = document.getElementById('ddFromDate');
    var toInput = document.getElementById('ddToDate');

    clearValidation();

    if (!fromVal && !toVal) {
      showValidationError('Please enter both From Date and To Date to filter transactions.');
      if (fromInput) fromInput.classList.add('input-error');
      if (toInput) toInput.classList.add('input-error');
      return false;
    }
    if (!fromVal) {
      showValidationError('Please select a From Date.');
      if (fromInput) {
        fromInput.classList.add('input-error');
        fromInput.focus();
      }
      return false;
    }
    if (!toVal) {
      showValidationError('Please select a To Date.');
      if (toInput) {
        toInput.classList.add('input-error');
        toInput.focus();
      }
      return false;
    }
    if (fromVal > toVal) {
      showValidationError('From Date (' + fmtDate(fromVal) + ') cannot be later than To Date (' + fmtDate(toVal) + ').');
      if (fromInput) fromInput.classList.add('input-error');
      if (toInput) toInput.classList.add('input-error');
      return false;
    }

    return true;
  }

  function showValidationError(msg) {
    var alertBox = document.getElementById('ddValidationAlert');
    var msgSpan = document.getElementById('ddValidationMsg');
    if (msgSpan) msgSpan.textContent = msg;
    if (alertBox) {
      alertBox.style.display = 'flex';
      alertBox.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  function clearValidation() {
    var alertBox = document.getElementById('ddValidationAlert');
    if (alertBox) alertBox.style.display = 'none';

    var fromInput = document.getElementById('ddFromDate');
    var toInput = document.getElementById('ddToDate');
    if (fromInput) fromInput.classList.remove('input-error');
    if (toInput) toInput.classList.remove('input-error');
  }

  function onDateInputChanged() {
    clearValidation();
    currentMode = 'custom';
    currentPreset = null;

    var btns = document.querySelectorAll('.dd-preset-btn');
    btns.forEach(function (b) {
      b.classList.remove('active');
    });

    var badge = document.getElementById('ddModeBadge');
    if (badge) {
      badge.className = 'dd-mode-badge dd-mode-custom';
      badge.innerHTML = '<i class="bi bi-calendar-check"></i> <span>Active Mode:</span> <strong>Custom Date Range</strong>';
    }

    var fromVal = document.getElementById('ddFromDate').value;
    var toVal = document.getElementById('ddToDate').value;
    if (fromVal && toVal && fromVal > toVal) {
      showValidationError('From Date cannot be later than To Date.');
    }
  }

  // ── Mode Switchers ──
  function applySelectedPeriod() {
    var fromInput = document.getElementById('ddFromDate');
    var toInput = document.getElementById('ddToDate');
    var fromVal = fromInput ? fromInput.value.trim() : '';
    var toVal = toInput ? toInput.value.trim() : '';

    if (!validateSelectedDates(fromVal, toVal)) {
      return;
    }

    currentMode = 'custom';
    currentPreset = null;

    var btns = document.querySelectorAll('.dd-preset-btn');
    btns.forEach(function (b) {
      b.classList.remove('active');
    });

    var badge = document.getElementById('ddModeBadge');
    if (badge) {
      badge.className = 'dd-mode-badge dd-mode-custom';
      badge.innerHTML = '<i class="bi bi-calendar-check"></i> <span>Active Mode:</span> <strong>Custom (' + fmtDate(fromVal) + ' to ' + fmtDate(toVal) + ')</strong>';
    }

    var applyBtn = document.getElementById('ddApplyBtn');
    if (applyBtn) {
      applyBtn.disabled = true;
      applyBtn.innerHTML = '<span class="dd-spinner" style="width:12px;height:12px;display:inline-block;"></span> Applying...';
    }

    loadAll(function () {
      if (applyBtn) {
        applyBtn.disabled = false;
        applyBtn.innerHTML = '<i class="bi bi-funnel"></i> <span>Apply</span>';
      }
      showToast();
    });
  }

  function setQuickRange(preset) {
    clearValidation();
    currentMode = 'quick';
    currentPreset = preset;

    var btns = document.querySelectorAll('.dd-preset-btn');
    btns.forEach(function (b) {
      if (b.getAttribute('data-preset') === preset) {
        b.classList.add('active');
      } else {
        b.classList.remove('active');
      }
    });

    var today = new Date();
    var fromDt = new Date();
    var toDt = new Date();
    var presetName = 'Custom';

    switch (preset) {
      case 'today':
        presetName = 'Today';
        break;
      case 'yesterday':
        presetName = 'Yesterday';
        fromDt.setDate(today.getDate() - 1);
        toDt.setDate(today.getDate() - 1);
        break;
      case 'week':
        presetName = 'This Week';
        var dayOfWeek = today.getDay(); // 0 is Sunday
        var distanceToMonday = (dayOfWeek + 6) % 7;
        fromDt.setDate(today.getDate() - distanceToMonday);
        break;
      case 'month':
        presetName = 'This Month';
        fromDt.setDate(1);
        break;
      case 'last_month':
      case 'lastmonth':
        presetName = 'Last Month';
        fromDt = new Date(today.getFullYear(), today.getMonth() - 1, 1);
        toDt = new Date(today.getFullYear(), today.getMonth(), 0);
        break;
      case 'quarter':
        presetName = 'This Quarter';
        var currentQ = Math.floor(today.getMonth() / 3);
        fromDt = new Date(today.getFullYear(), currentQ * 3, 1);
        break;
      case 'year':
        presetName = 'Financial Year';
        var fyStartYear = today.getMonth() >= 3 ? today.getFullYear() : today.getFullYear() - 1;
        fromDt = new Date(fyStartYear, 3, 1);
        toDt = new Date(fyStartYear + 1, 2, 31);
        if (toDt > today) toDt = today;
        break;
      case 'all':
        presetName = 'All Time';
        fromDt = new Date(2000, 0, 1);
        toDt = new Date(2099, 11, 31);
        break;
    }

    var fromStr = (preset === 'all') ? '' : formatLocalISO(fromDt);
    var toStr = (preset === 'all') ? '' : formatLocalISO(toDt);

    var f = document.getElementById('ddFromDate');
    var t = document.getElementById('ddToDate');
    if (f) f.value = fromStr;
    if (t) t.value = toStr;

    var badge = document.getElementById('ddModeBadge');
    if (badge) {
      badge.className = 'dd-mode-badge dd-mode-quick';
      badge.innerHTML = '<i class="bi bi-lightning-charge-fill"></i> <span>Active Mode:</span> <strong>Quick Period (' + presetName + ')</strong>';
    }

    loadAll(function () {
      showToast();
    });
  }

  function resetToDefault() {
    clearValidation();
    setQuickRange('month');
  }

  // ── Data Loaders & Totals Calculations ──

  function loadKPIs(params) {
    fetch(qs('/dashboard/api/summary-kpis/', params))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        setText('kpiTotalInwards', fmtNum(d.total_inwards));
        setText('kpiGrnRm', fmtNum(d.total_grn_rm));
        setText('kpiGrnPm', fmtNum(d.total_grn_pm));
        setText('kpiGrnRmQty', fmtQty(d.total_inw_rm_qty));
        setText('kpiGrnPmQty', fmtNum(d.total_inw_pm_qty));

        setText('kpiLogsheets', fmtNum(d.total_logsheets));
        setText('kpiLogDprDone', fmtNum(d.logsheets_dpr_done));
        setText('kpiLogDispDone', fmtNum(d.logsheets_disp_done));

        setText('kpiDispensing', fmtNum(d.total_rm_dispensings));

        setText('kpiDpr', fmtNum(d.total_dpr));
        setText('kpiDprWorking', fmtNum(d.dpr_working));
        setText('kpiDprStoppage', fmtNum(d.dpr_stoppage));

        setText('kpiProdKg', fmtQty(d.total_prod_kg) + ' kg');
        setText('kpiProdNos', fmtNum(d.total_prod_nos));

        setText('kpiTotalShippers', fmtNum(d.total_shippers) + ' Shippers');
        setText('kpiPackedNos', fmtNum(d.total_packed_nos));

        setText('kpiSalesOrders', fmtNum(d.total_sales_orders));
        setText('kpiOrderVal', fmtCurrency(d.total_order_val));

        setText('kpiSalesInvoices', fmtNum(d.total_sales_invoices));
        setText('kpiInvoiceAmt', fmtCurrency(d.total_invoice_amount));

        setText('kpiActiveStock', fmtNum(d.active_stock_batches));

        updateActivePeriodBadge(d.from_date, d.to_date);
      })
      .catch(function (err) {
        console.error('Error loading summary KPIs:', err);
      });
  }

  function loadInward(params) {
    showEl('loadingInward');
    hideEl('emptyInward');
    hideEl('tableWrapInward');

    fetch(qs('/dashboard/api/inward-logsheet/', params))
      .then(function (r) { return r.json(); })
      .then(function (res) {
        hideEl('loadingInward');
        var data = res.data || [];
        DATA_STORE.inward = data;
        setText('badgeInward', fmtNum(res.total_records));
        setText('footCountInward', fmtNum(res.total_records));

        if (!data.length) {
          showEl('emptyInward');
          setText('footCountInward', '0');
          setText('footCountInwardRm', '0');
          setText('footCountInwardPm', '0');
          setText('footLinesInward', '0');
          setText('footRmQtyInward', '0.00');
          setText('footPmQtyInward', '0');
          setText('footQtyInward', '0.00');
          setText('tfInwardLines', '0');
          setText('tfInwardRmQty', '0.00');
          setText('tfInwardPmQty', '0');
          setText('tfInwardQty', '0.00');
          return;
        }

        var tbody = document.getElementById('tbodyInward');
        var totalQty = 0;
        var totalLines = 0;
        var html = '';

        data.forEach(function (row) {
          totalQty += Number(row.total_qty || 0);
          totalLines += Number(row.items_count || 0);

          var catCode = String(row.grn_category || '').toUpperCase();
          var isRm = (catCode === 'RM');
          var isPm = (catCode === 'PM');
          var uomLabel = row.uom || (isRm ? 'kg' : (isPm ? 'Nos' : ''));
          var qtyDisp = isRm ? fmtQty(row.total_qty) : (isPm ? fmtNum(row.total_qty) : fmtQty(row.total_qty));

          var catBadge = isRm
            ? '<span class="dd-badge-cat dd-badge-rm">RM</span>'
            : (isPm
              ? '<span class="dd-badge-cat dd-badge-pm">PM</span>'
              : '<span class="dd-badge-cat">' + esc(row.grn_category) + '</span>');

          var docBadge = row.has_doc
            ? '<span class="dd-doc-badge" title="Document / COA Attached"><i class="bi bi-file-earmark-check-fill"></i></span>'
            : '<span class="dd-doc-badge empty" title="No Document"><i class="bi bi-dash"></i></span>';

          var driverInfo = '';
          if (row.driver_name || row.driver_no) {
            driverInfo = '<div class="dd-sub-line"><i class="bi bi-person"></i> ' + esc(row.driver_name) + (row.driver_no ? ' (' + esc(row.driver_no) + ')' : '') + '</div>';
          }

          var batchArns = '';
          if (row.batches_display || row.arns_display) {
            batchArns = '<div class="dd-sub-line">';
            if (row.batches_display) batchArns += '<span class="dd-pill-batch">B: ' + esc(row.batches_display) + '</span> ';
            if (row.arns_display) batchArns += '<span class="dd-pill-arn">ARN: ' + esc(row.arns_display) + '</span>';
            batchArns += '</div>';
          }

          html += '<tr data-cat="' + esc(catCode) + '" data-qty="' + Number(row.total_qty || 0) + '" data-lines="' + Number(row.items_count || 0) + '">' +
            '<td data-date="' + esc(row.inward_dt) + '"><strong>' + fmtDate(row.inward_dt) + '</strong></td>' +
            '<td><strong>' + esc(row.grn_no) + '</strong></td>' +
            '<td>' + esc(row.register_no) + '</td>' +
            '<td class="text-center">' + catBadge + '</td>' +
            '<td><strong>' + esc(row.supplier_name) + '</strong></td>' +
            '<td>' + esc(row.customer_name) + '</td>' +
            '<td>' + esc(row.inv_no) + '</td>' +
            '<td data-date="' + esc(row.inv_dt) + '">' + fmtDate(row.inv_dt) + '</td>' +
            '<td>' + esc(row.vehicle_no) + '</td>' +
            '<td>' + esc(row.transporter_name) + driverInfo + '</td>' +
            '<td>' + esc(row.products_display || '—') + '</td>' +
            '<td>' + (batchArns || '—') + '</td>' +
            '<td class="text-right" data-num="' + Number(row.items_count || 0) + '">' + fmtNum(row.items_count) + '</td>' +
            '<td class="text-right font-weight-bold" data-num="' + Number(row.total_qty || 0) + '" data-cat="' + esc(catCode) + '">' + qtyDisp + ' <span class="dd-unit-sub">' + esc(uomLabel) + '</span></td>' +
            '<td class="text-center">' + docBadge + '</td>' +
            '</tr>';
        });

        tbody.innerHTML = html;

        // Populate both tfoot and footer strip with separated RM / PM metrics
        setText('tfInwardLines', fmtNum(totalLines));
        setText('tfInwardRmQty', fmtQty(res.total_rm_qty));
        setText('tfInwardPmQty', fmtNum(res.total_pm_qty));
        setText('tfInwardQty', fmtQty(totalQty));

        setText('footCountInward', fmtNum(res.total_records));
        setText('footCountInwardRm', fmtNum(res.total_rm_count));
        setText('footCountInwardPm', fmtNum(res.total_pm_count));
        setText('footLinesInward', fmtNum(totalLines));
        setText('footRmQtyInward', fmtQty(res.total_rm_qty));
        setText('footPmQtyInward', fmtNum(res.total_pm_qty));
        setText('footQtyInward', fmtQty(totalQty));

        showEl('tableWrapInward');
      })
      .catch(function (err) {
        hideEl('loadingInward');
        showEl('emptyInward');
        console.error('Error loading Inwards:', err);
      });
  }

  function loadLogsheet(params) {
    showEl('loadingLogsheet');
    hideEl('emptyLogsheet');
    hideEl('tableWrapLogsheet');

    fetch(qs('/dashboard/api/granulation-logsheet/', params))
      .then(function (r) { return r.json(); })
      .then(function (res) {
        hideEl('loadingLogsheet');
        var data = res.data || [];
        DATA_STORE.logsheet = data;
        setText('badgeLogsheet', fmtNum(res.total_records));
        setText('footCountLogsheet', fmtNum(res.total_records));

        if (!data.length) {
          showEl('emptyLogsheet');
          setText('footLacsLogsheet', '0.00');
          setText('footNosLogsheet', '0');
          setText('tfLogLacs', '0.00');
          setText('tfLogNos', '0');
          return;
        }

        var tbody = document.getElementById('tbodyLogsheet');
        var totalLacs = 0;
        var totalNos = 0;
        var html = '';

        data.forEach(function (row) {
          totalLacs += Number(row.batch_qty_l || 0);
          totalNos += Number(row.batch_qty_n || 0);

          var rmBadge = row.rm_disp_flg === 'Y'
            ? '<span class="dd-badge-status dd-status-done"><i class="bi bi-check2"></i> Done</span>'
            : '<span class="dd-badge-status dd-status-pending"><i class="bi bi-hourglass-split"></i> Pending</span>';

          var dprBadge = row.dpr_flg === 'Y'
            ? '<span class="dd-badge-status dd-status-done"><i class="bi bi-check2"></i> Done</span>'
            : '<span class="dd-badge-status dd-status-not"><i class="bi bi-x"></i> Not Done</span>';

          var shiftBadge = row.shift_id === 'D' || row.shift_id === 'Day'
            ? 'Day'
            : 'Night';

          html += '<tr>' +
            '<td data-date="' + esc(row.gran_dt) + '"><strong>' + fmtDate(row.gran_dt) + '</strong></td>' +
            '<td>' + shiftBadge + '</td>' +
            '<td>' + esc(row.section_name) + '</td>' +
            '<td>' + esc(row.customer_name) + '</td>' +
            '<td><strong>' + esc(row.product_name) + '</strong></td>' +
            '<td><strong>' + esc(row.batch_no) + '</strong></td>' +
            '<td class="text-right" data-num="' + Number(row.batch_qty_l || 0) + '">' + fmtQty(row.batch_qty_l) + '</td>' +
            '<td class="text-right" data-num="' + Number(row.batch_qty_n || 0) + '">' + fmtNum(row.batch_qty_n) + '</td>' +
            '<td>' + esc(row.mfg_dt) + '</td>' +
            '<td>' + esc(row.exp_dt) + '</td>' +
            '<td data-date="' + esc(row.blend_dt) + '">' + fmtDate(row.blend_dt) + '</td>' +
            '<td>' + esc(row.layer_slot) + '</td>' +
            '<td class="text-center">' + rmBadge + '</td>' +
            '<td class="text-center">' + dprBadge + '</td>' +
            '</tr>';
        });

        tbody.innerHTML = html;

        setText('tfLogLacs', fmtQty(totalLacs));
        setText('tfLogNos', fmtNum(totalNos));
        setText('footLacsLogsheet', fmtQty(totalLacs));
        setText('footNosLogsheet', fmtNum(totalNos));

        showEl('tableWrapLogsheet');
      })
      .catch(function (err) {
        hideEl('loadingLogsheet');
        showEl('emptyLogsheet');
        console.error('Error loading Logsheets:', err);
      });
  }

  function loadDispensing(params) {
    showEl('loadingDispensing');
    hideEl('emptyDispensing');
    hideEl('tableWrapDispensing');

    fetch(qs('/dashboard/api/rm-dispensing/', params))
      .then(function (r) { return r.json(); })
      .then(function (res) {
        hideEl('loadingDispensing');
        var data = res.data || [];
        DATA_STORE.dispensing = data;
        setText('badgeDispensing', fmtNum(res.total_records));
        setText('footCountDispensing', fmtNum(res.total_records));

        if (!data.length) {
          showEl('emptyDispensing');
          setText('footLotsDispensing', '0');
          setText('footItemsDispensing', '0');
          setText('footQtyDispensing', '0.00');
          setText('tfDispLots', '0');
          setText('tfDispItems', '0');
          setText('tfDispQty', '0.00');
          return;
        }

        var tbody = document.getElementById('tbodyDispensing');
        var totalLots = 0;
        var totalItems = 0;
        var totalDisp = 0;
        var html = '';

        data.forEach(function (row) {
          totalLots += Number(row.lot_no || 0);
          totalItems += Number(row.lines_count || 0);
          totalDisp += Number(row.total_dispensed_qty || 0);

          html += '<tr>' +
            '<td data-date="' + esc(row.dispensing_dt) + '"><strong>' + fmtDate(row.dispensing_dt) + '</strong></td>' +
            '<td>' + esc(row.customer_name) + '</td>' +
            '<td><strong>' + esc(row.product_name) + '</strong></td>' +
            '<td><strong>' + esc(row.batch_no) + '</strong></td>' +
            '<td>' + esc(row.spec_name) + '</td>' +
            '<td>' + esc(row.machine_name) + '</td>' +
            '<td class="text-right" data-num="' + Number(row.lot_no || 0) + '">' + fmtNum(row.lot_no) + '</td>' +
            '<td>' + esc(row.dispensed_by) + '</td>' +
            '<td>' + esc(row.worker_name) + '</td>' +
            '<td>' + esc(row.checked_by || '—') + '</td>' +
            '<td>' + esc(row.verified_by || '—') + '</td>' +
            '<td class="text-right" data-num="' + Number(row.lines_count || 0) + '">' + fmtNum(row.lines_count) + '</td>' +
            '<td class="text-right font-weight-bold" data-num="' + Number(row.total_dispensed_qty || 0) + '">' + fmtQty(row.total_dispensed_qty) + '</td>' +
            '</tr>';
        });

        tbody.innerHTML = html;

        setText('tfDispLots', fmtNum(totalLots));
        setText('tfDispItems', fmtNum(totalItems));
        setText('tfDispQty', fmtQty(totalDisp));
        setText('footLotsDispensing', fmtNum(totalLots));
        setText('footItemsDispensing', fmtNum(totalItems));
        setText('footQtyDispensing', fmtQty(totalDisp));

        showEl('tableWrapDispensing');
      })
      .catch(function (err) {
        hideEl('loadingDispensing');
        showEl('emptyDispensing');
        console.error('Error loading Dispensing:', err);
      });
  }

  function loadDPR(params) {
    showEl('loadingDpr');
    hideEl('emptyDpr');
    hideEl('tableWrapDpr');

    fetch(qs('/dashboard/api/dpr-report/', params))
      .then(function (r) { return r.json(); })
      .then(function (res) {
        hideEl('loadingDpr');
        var data = res.data || [];
        DATA_STORE.dpr = data;
        setText('badgeDpr', fmtNum(res.total_records));
        setText('footCountDpr', fmtNum(res.total_records));

        if (!data.length) {
          showEl('emptyDpr');
          setText('footLotsDpr', '0');
          setText('footKgDpr', '0.00');
          setText('footNosDpr', '0');
          setText('footHelpersDpr', '0');
          setText('tfDprLots', '0');
          setText('tfDprKg', '0.00');
          setText('tfDprNos', '0');
          setText('tfDprHelpers', '0');
          return;
        }

        var tbody = document.getElementById('tbodyDpr');
        var totalLots = 0;
        var totalKg = 0;
        var totalNos = 0;
        var totalHelpers = 0;
        var html = '';

        data.forEach(function (row) {
          totalLots += Number(row.lot_no || 0);
          totalKg += Number(row.qty_kg || 0);
          totalNos += Number(row.qty_nos || 0);
          totalHelpers += Number(row.no_of_helper || 0);

          var statusBadge = (row.machine_working === 'working')
            ? '<span class="dd-badge-status dd-status-run">● Running</span>'
            : '<span class="dd-badge-status dd-status-stop">■ Stoppage</span>';

          var timeDisp = esc(row.start_time) + ' – ' + esc(row.end_time);
          if (row.total_time) {
            timeDisp += ' <small class="text-muted">(' + esc(row.total_time) + ')</small>';
          }

          var operatorLine = esc(row.operator1_name);
          if (row.operator2_name) {
            operatorLine += ' / ' + esc(row.operator2_name);
          }

          html += '<tr>' +
            '<td data-date="' + esc(row.trn_dpr_dt) + '"><strong>' + fmtDate(row.trn_dpr_dt) + '</strong></td>' +
            '<td>' + esc(row.section_name) + '</td>' +
            '<td><strong>' + esc(row.machine_name) + '</strong></td>' +
            '<td>' + esc(row.shift_id) + '</td>' +
            '<td>' + esc(row.customer_name) + '</td>' +
            '<td><strong>' + esc(row.product_name) + '</strong></td>' +
            '<td><strong>' + esc(row.batch_no) + '</strong></td>' +
            '<td class="text-right" data-num="' + Number(row.lot_no || 0) + '">' + fmtNum(row.lot_no) + '</td>' +
            '<td>' + timeDisp + '</td>' +
            '<td class="text-center">' + statusBadge + '</td>' +
            '<td class="text-right font-weight-bold" data-num="' + Number(row.qty_kg || 0) + '">' + fmtQty(row.qty_kg) + '</td>' +
            '<td class="text-right font-weight-bold" data-num="' + Number(row.qty_nos || 0) + '">' + fmtNum(row.qty_nos) + '</td>' +
            '<td>' + operatorLine + '</td>' +
            '<td class="text-right" data-num="' + Number(row.no_of_helper || 0) + '">' + fmtNum(row.no_of_helper) + '</td>' +
            '<td>' + esc(row.remarks || '—') + '</td>' +
            '</tr>';
        });

        tbody.innerHTML = html;

        setText('tfDprLots', fmtNum(totalLots));
        setText('tfDprKg', fmtQty(totalKg));
        setText('tfDprNos', fmtNum(totalNos));
        setText('tfDprHelpers', fmtNum(totalHelpers));
        setText('footLotsDpr', fmtNum(totalLots));
        setText('footKgDpr', fmtQty(totalKg));
        setText('footNosDpr', fmtNum(totalNos));
        setText('footHelpersDpr', fmtNum(totalHelpers));

        showEl('tableWrapDpr');
      })
      .catch(function (err) {
        hideEl('loadingDpr');
        showEl('emptyDpr');
        console.error('Error loading DPR:', err);
      });
  }

  function loadPacking(params) {
    showEl('loadingPacking');
    hideEl('emptyPacking');
    hideEl('tableWrapPacking');

    fetch(qs('/dashboard/api/packing-report/', params))
      .then(function (r) { return r.json(); })
      .then(function (res) {
        hideEl('loadingPacking');
        var data = res.data || [];
        DATA_STORE.packing = data;
        setText('badgePacking', fmtNum(res.total_records));
        setText('footCountPacking', fmtNum(res.total_records));

        if (!data.length) {
          showEl('emptyPacking');
          setText('footShippersPacking', '0');
          setText('footPackedNosPacking', '0');
          setText('footLoosePacking', '0');
          setText('footManpowerPacking', '0');
          setText('tfPackShippers', '0');
          setText('tfPackPacked', '0');
          setText('tfPackLoose', '0');
          setText('tfPackManpower', '0');
          return;
        }

        var tbody = document.getElementById('tbodyPacking');
        var totalShippers = 0;
        var totalPacked = 0;
        var totalLoose = 0;
        var totalManpower = 0;
        var html = '';

        data.forEach(function (row) {
          totalShippers += Number(row.shipper_no || 0);
          totalPacked += Number(row.qty_nos || 0);
          totalLoose += Number(row.qty_loose || 0);
          totalManpower += Number(row.no_of_girls || 0);

          html += '<tr>' +
            '<td data-date="' + esc(row.pkgcont_date) + '"><strong>' + fmtDate(row.pkgcont_date) + '</strong></td>' +
            '<td><strong>' + esc(row.contractor_name) + '</strong></td>' +
            '<td>' + esc(row.customer_name) + '</td>' +
            '<td><strong>' + esc(row.product_name) + '</strong></td>' +
            '<td><strong>' + esc(row.batch_no) + '</strong></td>' +
            '<td>' + esc(row.pkg_style_name) + '</td>' +
            '<td class="text-right font-weight-bold" data-num="' + Number(row.shipper_no || 0) + '">' + fmtNum(row.shipper_no) + '</td>' +
            '<td class="text-right font-weight-bold" data-num="' + Number(row.qty_nos || 0) + '">' + fmtNum(row.qty_nos) + '</td>' +
            '<td class="text-right" data-num="' + Number(row.qty_loose || 0) + '">' + fmtNum(row.qty_loose) + '</td>' +
            '<td class="text-right" data-num="' + Number(row.no_of_girls || 0) + '">' + fmtNum(row.no_of_girls) + '</td>' +
            '<td>' + esc(row.remarks || '—') + '</td>' +
            '</tr>';
        });

        tbody.innerHTML = html;

        setText('tfPackShippers', fmtNum(totalShippers));
        setText('tfPackPacked', fmtNum(totalPacked));
        setText('tfPackLoose', fmtNum(totalLoose));
        setText('tfPackManpower', fmtNum(totalManpower));
        setText('footShippersPacking', fmtNum(totalShippers));
        setText('footPackedNosPacking', fmtNum(totalPacked));
        setText('footLoosePacking', fmtNum(totalLoose));
        setText('footManpowerPacking', fmtNum(totalManpower));

        showEl('tableWrapPacking');
      })
      .catch(function (err) {
        hideEl('loadingPacking');
        showEl('emptyPacking');
        console.error('Error loading Packing report:', err);
      });
  }

  function loadOrders(params) {
    showEl('loadingOrders');
    hideEl('emptyOrders');
    hideEl('tableWrapOrders');

    fetch(qs('/dashboard/api/sales-orders/', params))
      .then(function (r) { return r.json(); })
      .then(function (res) {
        hideEl('loadingOrders');
        var data = res.data || [];
        DATA_STORE.orders = data;
        setText('badgeOrders', fmtNum(res.total_records));
        setText('footCountOrders', fmtNum(res.total_records));

        if (!data.length) {
          showEl('emptyOrders');
          setText('footLacsOrders', '0.00');
          setText('footNosOrders', '0');
          setText('footRemOrders', '0.00');
          setText('footAmtOrders', '₹ 0.00');
          setText('tfOrdQtyLacs', '0.00');
          setText('tfOrdQtyNos', '0');
          setText('tfOrdRemLacs', '0.00');
          setText('tfOrdTotal', '₹ 0.00');
          return;
        }

        var tbody = document.getElementById('tbodyOrders');
        var totalLacs = 0;
        var totalNos = 0;
        var totalRem = 0;
        var totalVal = 0;
        var html = '';

        data.forEach(function (row) {
          totalLacs += Number(row.order_qty || 0);
          totalNos += Number(row.ord_qty_nos || 0);
          totalRem += Number(row.remaining_qty || 0);
          totalVal += Number(row.total_amt || 0);

          var allocBadge = row.is_completed
            ? '<span class="dd-badge-status dd-status-done">Allocated</span>'
            : '<span class="dd-badge-status dd-status-pending">In Progress</span>';

          var dispatchBadge = row.is_sale_completed
            ? '<span class="dd-badge-status dd-status-done">Dispatched</span>'
            : '<span class="dd-badge-status dd-status-pending">Pending</span>';

          html += '<tr>' +
            '<td data-date="' + esc(row.ord_rec_dt) + '"><strong>' + fmtDate(row.ord_rec_dt) + '</strong></td>' +
            '<td><strong>' + esc(row.cust_ord_id) + '</strong></td>' +
            '<td data-date="' + esc(row.cust_ord_date) + '">' + fmtDate(row.cust_ord_date) + '</td>' +
            '<td><strong>' + esc(row.customer_name) + '</strong></td>' +
            '<td><strong>' + esc(row.product_name) + '</strong></td>' +
            '<td>' + esc(row.pkg_style_name) + '</td>' +
            '<td class="text-right" data-num="' + Number(row.order_qty || 0) + '">' + fmtQty(row.order_qty) + '</td>' +
            '<td class="text-right" data-num="' + Number(row.ord_qty_nos || 0) + '">' + fmtNum(row.ord_qty_nos) + '</td>' +
            '<td class="text-right font-weight-bold" data-num="' + Number(row.remaining_qty || 0) + '">' + fmtQty(row.remaining_qty) + '</td>' +
            '<td class="text-center">' + allocBadge + '</td>' +
            '<td class="text-center">' + dispatchBadge + '</td>' +
            '<td class="text-right" data-num="' + Number(row.rate || 0) + '">' + fmtCurrency(row.rate) + '</td>' +
            '<td class="text-right font-weight-bold" data-num="' + Number(row.total_amt || 0) + '">' + fmtCurrency(row.total_amt) + '</td>' +
            '</tr>';
        });

        tbody.innerHTML = html;

        setText('tfOrdQtyLacs', fmtQty(totalLacs));
        setText('tfOrdQtyNos', fmtNum(totalNos));
        setText('tfOrdRemLacs', fmtQty(totalRem));
        setText('tfOrdTotal', fmtCurrency(totalVal));

        setText('footLacsOrders', fmtQty(totalLacs));
        setText('footNosOrders', fmtNum(totalNos));
        setText('footRemOrders', fmtQty(totalRem));
        setText('footAmtOrders', fmtCurrency(totalVal));

        showEl('tableWrapOrders');
      })
      .catch(function (err) {
        hideEl('loadingOrders');
        showEl('emptyOrders');
        console.error('Error loading Sales Orders:', err);
      });
  }

  function loadSales(params) {
    showEl('loadingSales');
    hideEl('emptySales');
    hideEl('tableWrapSales');

    fetch(qs('/dashboard/api/sales-summary/', params))
      .then(function (r) { return r.json(); })
      .then(function (res) {
        hideEl('loadingSales');
        var data = res.data || [];
        DATA_STORE.sales = data;
        setText('badgeSales', fmtNum(res.total_records));
        setText('footCountSales', fmtNum(res.total_records));

        if (!data.length) {
          showEl('emptySales');
          setText('footTaxableSales', '₹ 0.00');
          setText('footGstSales', '₹ 0.00');
          setText('footAmtSales', '₹ 0.00');
          setText('tfSlsTaxable', '₹ 0.00');
          setText('tfSlsCgst', '₹ 0.00');
          setText('tfSlsSgst', '₹ 0.00');
          setText('tfSlsIgst', '₹ 0.00');
          setText('tfSlsTotal', '₹ 0.00');
          setText('tfSlsItems', '0');
          return;
        }

        var tbody = document.getElementById('tbodySales');
        var totalTaxable = 0;
        var totalCgst = 0;
        var totalSgst = 0;
        var totalIgst = 0;
        var totalRevenue = 0;
        var totalItems = 0;
        var html = '';

        data.forEach(function (row) {
          totalTaxable += Number(row.taxable_val || 0);
          totalCgst += Number(row.cgst_amt || 0);
          totalSgst += Number(row.sgst_amt || 0);
          totalIgst += Number(row.igst_amt || 0);
          totalRevenue += Number(row.total_amt || 0);
          totalItems += Number(row.line_count || 0);

          html += '<tr>' +
            '<td><strong>' + esc(row.invoice_no) + '</strong></td>' +
            '<td data-date="' + esc(row.invoice_dt) + '"><strong>' + fmtDate(row.invoice_dt) + '</strong></td>' +
            '<td><strong>' + esc(row.customer_name) + '</strong></td>' +
            '<td>' + esc(row.ref_po_no || '—') + '</td>' +
            '<td>' + esc(row.transporter_name) + '</td>' +
            '<td>' + esc(row.delivery_add) + '</td>' +
            '<td class="text-right" data-num="' + Number(row.taxable_val || 0) + '">' + fmtCurrency(row.taxable_val) + '</td>' +
            '<td class="text-right" data-num="' + Number(row.cgst_amt || 0) + '">' + fmtCurrency(row.cgst_amt) + '</td>' +
            '<td class="text-right" data-num="' + Number(row.sgst_amt || 0) + '">' + fmtCurrency(row.sgst_amt) + '</td>' +
            '<td class="text-right" data-num="' + Number(row.igst_amt || 0) + '">' + fmtCurrency(row.igst_amt) + '</td>' +
            '<td class="text-right font-weight-bold" data-num="' + Number(row.total_amt || 0) + '">' + fmtCurrency(row.total_amt) + '</td>' +
            '<td class="text-right" data-num="' + Number(row.line_count || 0) + '">' + fmtNum(row.line_count) + '</td>' +
            '</tr>';
        });

        tbody.innerHTML = html;

        setText('tfSlsTaxable', fmtCurrency(totalTaxable));
        setText('tfSlsCgst', fmtCurrency(totalCgst));
        setText('tfSlsSgst', fmtCurrency(totalSgst));
        setText('tfSlsIgst', fmtCurrency(totalIgst));
        setText('tfSlsTotal', fmtCurrency(totalRevenue));
        setText('tfSlsItems', fmtNum(totalItems));

        setText('footTaxableSales', fmtCurrency(totalTaxable));
        setText('footGstSales', fmtCurrency(totalCgst + totalSgst + totalIgst));
        setText('footAmtSales', fmtCurrency(totalRevenue));

        showEl('tableWrapSales');
      })
      .catch(function (err) {
        hideEl('loadingSales');
        showEl('emptySales');
        console.error('Error loading Sales Invoices:', err);
      });
  }

  var currentStockCategory = 'ALL';

  function getStockPeriodParams(dashParams) {
    var select = document.getElementById('stockPeriodSelect');
    var mode = select ? select.value : 'sync';
    var today = new Date();
    var fromDt = new Date();
    var toDt = new Date();

    if (mode === 'live') {
      setText('footStockScopeText', 'Live As of Today (Cumulative Ledger)');
      return { live: '1' };
    }
    if (mode === 'all') {
      setText('footStockScopeText', 'All Time (Complete History)');
      return { all: '1' };
    }
    if (mode === 'month') {
      fromDt.setDate(1);
      setText('footStockScopeText', 'This Month (' + fmtDate(formatLocalISO(fromDt)) + ' – Today)');
      return { from_date: formatLocalISO(fromDt), to_date: formatLocalISO(toDt) };
    }
    if (mode === 'last_month') {
      fromDt = new Date(today.getFullYear(), today.getMonth() - 1, 1);
      toDt = new Date(today.getFullYear(), today.getMonth(), 0);
      setText('footStockScopeText', 'Last Month (' + fmtDate(formatLocalISO(fromDt)) + ' – ' + fmtDate(formatLocalISO(toDt)) + ')');
      return { from_date: formatLocalISO(fromDt), to_date: formatLocalISO(toDt) };
    }
    if (mode === 'quarter') {
      var currentQ = Math.floor(today.getMonth() / 3);
      fromDt = new Date(today.getFullYear(), currentQ * 3, 1);
      setText('footStockScopeText', 'This Quarter (' + fmtDate(formatLocalISO(fromDt)) + ' – Today)');
      return { from_date: formatLocalISO(fromDt), to_date: formatLocalISO(toDt) };
    }
    if (mode === 'year') {
      var fyStartYear = today.getMonth() >= 3 ? today.getFullYear() : today.getFullYear() - 1;
      fromDt = new Date(fyStartYear, 3, 1);
      toDt = new Date(fyStartYear + 1, 2, 31);
      if (toDt > today) toDt = today;
      setText('footStockScopeText', 'Financial Year (' + fyStartYear + '–' + (fyStartYear + 1) + ')');
      return { from_date: formatLocalISO(fromDt), to_date: formatLocalISO(toDt) };
    }

    // mode === 'sync'
    var range = dashParams || getRange();
    if (range.all) {
      setText('footStockScopeText', 'Sync with Dashboard (All Time)');
    } else if (range.from_date && range.to_date) {
      setText('footStockScopeText', 'Sync (' + fmtDate(range.from_date) + ' – ' + fmtDate(range.to_date) + ')');
    } else {
      setText('footStockScopeText', 'Sync with Dashboard Period');
    }
    return range;
  }

  function loadStock(params) {
    showEl('loadingStock');
    hideEl('emptyStock');
    hideEl('tableWrapStock');

    var queryParams = getStockPeriodParams(params);

    fetch(qs('/dashboard/api/stock-overview/', queryParams))
      .then(function (r) { return r.json(); })
      .then(function (res) {
        hideEl('loadingStock');
        var data = res.data || [];
        DATA_STORE.stock = data;

        var totals = res.totals || {};
        var allTotals = totals.ALL || {};
        var rmTotals = totals.RM || {};
        var pmTotals = totals.PM || {};
        var fgTotals = totals.FG || {};

        setText('badgeStock', fmtNum(res.total_records));
        setText('footCountStock', fmtNum(res.total_records));

        // Category Tab Badges
        setText('tabCountStockAll', fmtNum(allTotals.count !== undefined ? allTotals.count : res.total_records));
        setText('tabCountStockRm', fmtNum(rmTotals.count || 0));
        setText('tabCountStockPm', fmtNum(pmTotals.count || 0));
        setText('tabCountStockFg', fmtNum(fgTotals.count || 0));

        // Category Balances in Footer Strip
        setText('footBalStockRm', fmtQty(rmTotals.closing || 0));
        setText('footBalStockPm', fmtNum(pmTotals.closing || 0));
        setText('footBalStockFg', fmtNum(fgTotals.closing || 0));

        if (!data.length) {
          showEl('emptyStock');
          setText('footOpnStock', '0.00');
          setText('footRcptStock', '+0.00');
          setText('footIssueStock', '-0.00');
          setText('footBalStock', '0.00');
          setText('tfStkOpn', '0.00');
          setText('tfStkRcpt', '+0.00');
          setText('tfStkIssue', '-0.00');
          setText('tfStkBal', '0.00');
          return;
        }

        var tbody = document.getElementById('tbodyStock');
        var html = '';

        data.forEach(function (row) {
          var catCode = String(row.category_code || 'RM').toUpperCase();
          var catBadge = '<span class="dd-badge-cat">' + esc(row.category) + '</span>';
          if (catCode === 'RM') {
            catBadge = '<span class="dd-badge-cat dd-badge-rm">RM</span>';
          } else if (catCode === 'PM') {
            catBadge = '<span class="dd-badge-cat dd-badge-pm">PM</span>';
          } else if (catCode === 'FG') {
            catBadge = '<span class="dd-badge-cat dd-badge-fg">FG</span>';
          }

          var uomBadge = '<span class="dd-uom-pill">' + esc(row.uom || '—') + '</span>';
          var isRm = (catCode === 'RM');
          var opnDisp = isRm ? fmtQty(row.opn_qty) : fmtNum(row.opn_qty);
          var rcptDisp = '+' + (isRm ? fmtQty(row.rcpt_qty) : fmtNum(row.rcpt_qty));
          var issueDisp = '-' + (isRm ? fmtQty(row.issue_qty) : fmtNum(row.issue_qty));
          var balDisp = isRm ? fmtQty(row.closing_qty) : fmtNum(row.closing_qty);
          var balanceClass = Number(row.closing_qty) > 0 ? 'text-success font-weight-bold' : 'text-danger font-weight-bold';

          html += '<tr data-cat="' + esc(catCode) + '">' +
            '<td><strong>' + esc(row.customer_name) + '</strong></td>' +
            '<td class="text-center">' + catBadge + '</td>' +
            '<td><strong>' + esc(row.sku_name) + '</strong></td>' +
            '<td class="text-center">' + uomBadge + '</td>' +
            '<td>' + esc(row.batch_no || '—') + '</td>' +
            '<td data-date="' + esc(row.mfg_date) + '">' + fmtDate(row.mfg_date) + '</td>' +
            '<td data-date="' + esc(row.exp_date) + '">' + fmtDate(row.exp_date) + '</td>' +
            '<td class="text-right" data-num="' + Number(row.opn_qty || 0) + '">' + opnDisp + '</td>' +
            '<td class="text-right text-success" data-num="' + Number(row.rcpt_qty || 0) + '">' + rcptDisp + '</td>' +
            '<td class="text-right text-danger" data-num="' + Number(row.issue_qty || 0) + '">' + issueDisp + '</td>' +
            '<td class="text-right ' + balanceClass + '" data-num="' + Number(row.closing_qty || 0) + '">' + balDisp + '</td>' +
            '<td data-date="' + esc(row.last_trn_date) + '">' + fmtDate(row.last_trn_date) + '</td>' +
            '</tr>';
        });

        tbody.innerHTML = html;
        showEl('tableWrapStock');

        filterStockTable();
      })
      .catch(function (err) {
        hideEl('loadingStock');
        showEl('emptyStock');
        console.error('Error loading Stock Overview:', err);
      });
  }

  function setStockCategory(cat) {
    currentStockCategory = (cat || 'ALL').toUpperCase();
    var tabs = document.querySelectorAll('.dd-stock-tab');
    tabs.forEach(function (t) {
      if ((t.getAttribute('data-cat') || '').toUpperCase() === currentStockCategory) {
        t.classList.add('active');
      } else {
        t.classList.remove('active');
      }
    });
    filterStockTable();
  }

  function onStockPeriodSelect(mode) {
    loadStock();
  }

  function filterStockTable(query) {
    var searchInput = document.querySelector('#sectionStock input[type="text"]');
    var q = (query !== undefined ? query : (searchInput ? searchInput.value : '')).toLowerCase().trim();
    var tbody = document.getElementById('tbodyStock');
    if (!tbody) return;
    var rows = tbody.getElementsByTagName('tr');

    var visibleCount = 0;
    var totOpn = 0;
    var totRcpt = 0;
    var totIssue = 0;
    var totBal = 0;

    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      var rowCat = (r.getAttribute('data-cat') || '').toUpperCase();
      var matchesCat = (currentStockCategory === 'ALL' || rowCat === currentStockCategory);
      var rowText = (r.textContent || r.innerText).toLowerCase();
      var matchesQuery = (q === '' || rowText.indexOf(q) > -1);

      if (matchesCat && matchesQuery) {
        r.style.display = '';
        visibleCount++;
        var cells = r.querySelectorAll('td');
        if (cells[7] && cells[7].hasAttribute('data-num')) totOpn += parseFloat(cells[7].getAttribute('data-num')) || 0;
        if (cells[8] && cells[8].hasAttribute('data-num')) totRcpt += parseFloat(cells[8].getAttribute('data-num')) || 0;
        if (cells[9] && cells[9].hasAttribute('data-num')) totIssue += parseFloat(cells[9].getAttribute('data-num')) || 0;
        if (cells[10] && cells[10].hasAttribute('data-num')) totBal += parseFloat(cells[10].getAttribute('data-num')) || 0;
      } else {
        r.style.display = 'none';
      }
    }

    setText('footCountStock', fmtNum(visibleCount));

    var isAllInt = (currentStockCategory === 'PM' || currentStockCategory === 'FG');
    var fmtFn = isAllInt ? fmtNum : fmtQty;

    setText('tfStkOpn', fmtFn(totOpn));
    setText('tfStkRcpt', '+' + fmtFn(totRcpt));
    setText('tfStkIssue', '-' + fmtFn(totIssue));
    setText('tfStkBal', fmtFn(totBal));
  }

  // ── Master Loader ──
  function loadAll(cb) {
    var params = getRange();

    // Trigger subtle spin on refresh button if present
    var refreshBtn = document.querySelector('.dd-btn-refresh i');
    if (refreshBtn) {
      refreshBtn.style.animation = 'dd-spin 0.6s linear';
      setTimeout(function () {
        refreshBtn.style.animation = '';
      }, 600);
    }

    loadKPIs(params);
    loadInward(params);
    loadLogsheet(params);
    loadDispensing(params);
    loadDPR(params);
    loadPacking(params);
    loadOrders(params);
    loadSales(params);
    loadStock(params);

    if (typeof cb === 'function') {
      setTimeout(cb, 350);
    }
  }

  // ── Live In-Table Filter with DYNAMIC TOTALS RECALCULATION ──
  function filterTable(tbodyId, query, tfootId) {
    var tbody = document.getElementById(tbodyId);
    if (!tbody) return;
    var filter = query ? query.toLowerCase().trim() : '';
    var rows = tbody.getElementsByTagName('tr');

    var visibleCount = 0;
    var colSums = {}; // colIndex -> sum

    for (var i = 0; i < rows.length; i++) {
      var rowText = rows[i].textContent || rows[i].innerText;
      var isVisible = (filter === '' || rowText.toLowerCase().indexOf(filter) > -1);

      if (isVisible) {
        rows[i].style.display = '';
        visibleCount++;

        // Add to colSums for cells with data-num
        var cells = rows[i].querySelectorAll('td');
        for (var j = 0; j < cells.length; j++) {
          if (cells[j].hasAttribute('data-num')) {
            var val = parseFloat(cells[j].getAttribute('data-num')) || 0;
            colSums[j] = (colSums[j] || 0) + val;
          }
        }
      } else {
        rows[i].style.display = 'none';
      }
    }

    // Special handling for Inward table to dynamically recalculate RM and PM separately
    if (tbodyId === 'tbodyInward') {
      var visibleRmQty = 0;
      var visiblePmQty = 0;
      var visibleRmLines = 0;
      var visiblePmLines = 0;
      var visibleRmCount = 0;
      var visiblePmCount = 0;

      for (var k = 0; k < rows.length; k++) {
        if (rows[k].style.display !== 'none') {
          var rowCat = (rows[k].getAttribute('data-cat') || '').toUpperCase();
          var rowQty = parseFloat(rows[k].getAttribute('data-qty')) || 0;
          var rowLines = parseInt(rows[k].getAttribute('data-lines')) || 0;
          if (rowCat === 'RM') {
            visibleRmQty += rowQty;
            visibleRmLines += rowLines;
            visibleRmCount++;
          } else if (rowCat === 'PM') {
            visiblePmQty += rowQty;
            visiblePmLines += rowLines;
            visiblePmCount++;
          }
        }
      }

      setText('tfInwardRmQty', fmtQty(visibleRmQty));
      setText('tfInwardPmQty', fmtNum(visiblePmQty));
      setText('tfInwardLines', fmtNum(visibleRmLines + visiblePmLines));
      setText('tfInwardQty', fmtQty(visibleRmQty + visiblePmQty));

      setText('footCountInward', fmtNum(visibleCount));
      setText('footCountInwardRm', fmtNum(visibleRmCount));
      setText('footCountInwardPm', fmtNum(visiblePmCount));
      setText('footLinesInward', fmtNum(visibleRmLines + visiblePmLines));
      setText('footRmQtyInward', fmtQty(visibleRmQty));
      setText('footPmQtyInward', fmtNum(visiblePmQty));
      setText('footQtyInward', fmtQty(visibleRmQty + visiblePmQty));
    }

    // Update tfoot row if present (excluding tbodyInward which uses split RM/PM pills above)
    var tfoot = document.getElementById(tfootId);
    if (tfoot && tbodyId !== 'tbodyInward') {
      var footRow = tfoot.querySelector('tr');
      if (footRow) {
        var footCells = footRow.querySelectorAll('td');
        for (var c = 0; c < footCells.length; c++) {
          if (c in colSums) {
            var rawSum = colSums[c];
            var currentText = footCells[c].textContent || '';
            if (currentText.indexOf('₹') > -1) {
              footCells[c].textContent = fmtCurrency(rawSum);
            } else if (currentText.indexOf('+') > -1) {
              footCells[c].textContent = '+' + fmtQty(rawSum);
            } else if (currentText.indexOf('-') > -1) {
              footCells[c].textContent = '-' + fmtQty(rawSum);
            } else if (Number.isInteger(rawSum) && currentText.indexOf('.') === -1) {
              footCells[c].textContent = fmtNum(rawSum);
            } else {
              footCells[c].textContent = fmtQty(rawSum);
            }
          }
        }
      }
    }
  }

  // ── High-Grade Excel Workbook Export (.xls with Auto Column Widths & Bold Totals) ──
  // Microsoft Excel auto-fits columns in HTML/XML spreadsheets, avoiding '########' on dates!
  function exportTableToExcel(tableId, filename) {
    var table = document.getElementById(tableId);
    if (!table) return;

    var clone = table.cloneNode(true);

    // Remove hidden rows from the clone if filtered
    var rows = clone.querySelectorAll('tbody tr');
    rows.forEach(function (r) {
      if (r.style.display === 'none') {
        r.parentNode.removeChild(r);
      }
    });

    // Ensure all date cells have explicit min-width and mso-number-format to prevent '########'
    var allDateCells = clone.querySelectorAll('td[data-date], th');
    allDateCells.forEach(function (c) {
      c.setAttribute('style', (c.getAttribute('style') || '') + '; min-width: 120px; white-space: nowrap;');
    });

    var excelHTML = '<html xmlns:o="urn:schemas-microsoft-com:office:office" ' +
      'xmlns:x="urn:schemas-microsoft-com:office:excel" ' +
      'xmlns="http://www.w3.org/TR/REC-html40">' +
      '<head>' +
      '<meta http-equiv="Content-Type" content="application/vnd.ms-excel; charset=UTF-8">' +
      '<!--[if gte mso 9]><xml><x:ExcelWorkbook><x:ExcelWorksheets><x:ExcelWorksheet>' +
      '<x:Name>' + (filename ? filename.substring(0, 30) : 'Sheet1') + '</x:Name>' +
      '<x:WorksheetOptions><x:DisplayGridlines/></x:WorksheetOptions>' +
      '</x:ExcelWorksheet></x:ExcelWorksheets></x:ExcelWorkbook></xml><![endif]-->' +
      '<style>' +
      'table { border-collapse: collapse; width: 100%; font-family: Calibri, Arial, sans-serif; font-size: 11pt; } ' +
      'th { background-color: #0F172A; color: #FFFFFF; font-weight: bold; padding: 8px 14px; border: 1px solid #CBD5E1; text-align: left; } ' +
      'th.text-right { text-align: right; } ' +
      'th.text-center { text-align: center; } ' +
      'td { border: 1px solid #E2E8F0; padding: 6px 14px; color: #0F172A; white-space: nowrap; } ' +
      'td.text-right { text-align: right; mso-number-format: "#,##0.00"; } ' +
      'td.text-center { text-align: center; } ' +
      '.dd-total-row td { background-color: #F1F5F9; font-weight: bold; border-top: 2px solid #0F172A; border-bottom: 3px double #0F172A; } ' +
      '[data-date] { mso-number-format: "\\@"; white-space: nowrap; min-width: 120px; } ' +
      '</style>' +
      '</head>' +
      '<body>' +
      '<h2>' + (filename || 'Transaction Report').replace(/_/g, ' ') + '</h2>' +
      '<p>Exported from RenumedERP on ' + fmtDate(formatLocalISO(new Date())) + '</p>' +
      clone.outerHTML +
      '</body></html>';

    var blob = new Blob(['\uFEFF' + excelHTML], { type: 'application/vnd.ms-excel;charset=utf-8;' });
    var downloadLink = document.createElement('a');
    downloadLink.download = (filename || 'Report') + '_' + formatLocalISO(new Date()) + '.xls';
    downloadLink.href = window.URL.createObjectURL(blob);
    downloadLink.style.display = 'none';
    document.body.appendChild(downloadLink);
    downloadLink.click();
    document.body.removeChild(downloadLink);
  }

  // ── CSV Export (with text-escaped dates to avoid Excel auto-conversion to narrow '########') ──
  function exportTableToCSV(tableId, filename) {
    var table = document.getElementById(tableId);
    if (!table) return;

    var csv = [];
    var allRows = table.querySelectorAll('tr');

    for (var i = 0; i < allRows.length; i++) {
      if (allRows[i].style.display === 'none') continue;

      var row = [];
      var cols = allRows[i].querySelectorAll('td, th');
      for (var j = 0; j < cols.length; j++) {
        var cell = cols[j];
        var text = cell.innerText.replace(/(\r\n|\n|\r)/gm, ' ').replace(/\s+/g, ' ').trim();

        // If the cell contains a date, wrap as formula string ="DD-MMM-YYYY" so Excel does NOT show '########'
        if (cell.hasAttribute('data-date') || /^\d{1,2}-[A-Za-z]{3}-\d{2,4}$/.test(text)) {
          text = '="' + text + '"';
        } else {
          text = text.replace(/"/g, '""');
          text = '"' + text + '"';
        }
        row.push(text);
      }
      csv.push(row.join(','));
    }

    var csvFile = new Blob(['\uFEFF' + csv.join('\r\n')], { type: 'text/csv;charset=utf-8;' });
    var downloadLink = document.createElement('a');
    downloadLink.download = (filename || 'Report') + '_' + formatLocalISO(new Date()) + '.csv';
    downloadLink.href = window.URL.createObjectURL(csvFile);
    downloadLink.style.display = 'none';
    document.body.appendChild(downloadLink);
    downloadLink.click();
    document.body.removeChild(downloadLink);
  }

  // ── Section Scrolling, Printing & Full-Screen Maximize ──
  function scrollToSection(sectionId) {
    var el = document.getElementById(sectionId);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });

    el.classList.add('dd-section-highlight');
    setTimeout(function () {
      el.classList.remove('dd-section-highlight');
    }, 1200);
  }

  function printSection(sectionId) {
    var section = document.getElementById(sectionId);
    if (!section) return;
    window.print();
  }

  var expandedSectionId = null;

  function toggleExpand(sectionId) {
    var section = document.getElementById(sectionId);
    var container = document.getElementById('directorDashboard');
    if (!section) return;

    var isExpanded = section.classList.contains('dd-expanded');
    var btn = section.querySelector('.dd-expand-btn');
    var label = btn ? btn.querySelector('.dd-expand-label') : null;
    var icon = btn ? btn.querySelector('i') : null;

    if (isExpanded) {
      section.classList.remove('dd-expanded');
      if (container) container.classList.remove('dd-has-expanded');
      document.body.classList.remove('dd-body-lock');
      expandedSectionId = null;

      if (label) label.textContent = 'Maximize';
      if (icon) icon.className = 'bi bi-arrows-fullscreen';
    } else {
      if (expandedSectionId) {
        var oldSec = document.getElementById(expandedSectionId);
        if (oldSec) {
          oldSec.classList.remove('dd-expanded');
          var oldBtn = oldSec.querySelector('.dd-expand-btn');
          if (oldBtn) {
            var oldLbl = oldBtn.querySelector('.dd-expand-label');
            var oldIcn = oldBtn.querySelector('i');
            if (oldLbl) oldLbl.textContent = 'Maximize';
            if (oldIcn) oldIcn.className = 'bi bi-arrows-fullscreen';
          }
        }
      }

      section.classList.add('dd-expanded');
      if (container) container.classList.add('dd-has-expanded');
      document.body.classList.add('dd-body-lock');
      expandedSectionId = sectionId;

      if (label) label.textContent = 'Minimize';
      if (icon) icon.className = 'bi bi-fullscreen-exit';

      section.scrollTop = 0;
    }
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && expandedSectionId) {
      toggleExpand(expandedSectionId);
    }
  });

  // ── Initialization ──
  function init() {
    setQuickRange('month');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  return {
    applySelectedPeriod: applySelectedPeriod,
    setQuickRange: setQuickRange,
    resetToDefault: resetToDefault,
    loadAll: loadAll,
    onDateInputChanged: onDateInputChanged,
    scrollToSection: scrollToSection,
    filterTable: filterTable,
    filterStockTable: filterStockTable,
    setStockCategory: setStockCategory,
    onStockPeriodSelect: onStockPeriodSelect,
    exportTableToExcel: exportTableToExcel,
    exportTableToCSV: exportTableToCSV,
    printSection: printSection,
    toggleExpand: toggleExpand,
  };
})();
