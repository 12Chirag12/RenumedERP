/**
 * Inventory stock browse — batch lifecycle & movement history modal
 * with dynamic time period filtering (presets & custom range).
 */
(function () {
  'use strict';

  function esc(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function fmtDelta(s, uom) {
    var n = parseFloat(String(s || '0'));
    if (!isFinite(n)) return '—';
    var txt = (n > 0 ? '+' : '') + n.toFixed(3);
    return uom ? txt + ' ' + uom : txt;
  }

  function formatLocalISO(d) {
    if (!d || isNaN(d.getTime())) return '';
    var year = d.getFullYear();
    var month = String(d.getMonth() + 1).padStart(2, '0');
    var day = String(d.getDate()).padStart(2, '0');
    return year + '-' + month + '-' + day;
  }

  function fmtDate(iso) {
    if (!iso || iso === '—' || iso === 'None') return '—';
    try {
      var s = String(iso).trim().split('T')[0];
      var parts = s.split('-');
      if (parts.length === 3) {
        var y = parseInt(parts[0], 10);
        var m = parseInt(parts[1], 10) - 1;
        var d = parseInt(parts[2], 10);
        var dt = new Date(y, m, d);
        if (!isNaN(dt.getTime())) {
          return dt.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
        }
      }
      return s;
    } catch (e) {
      return iso;
    }
  }

  function fmtDateTime(iso) {
    if (!iso || iso === '—' || iso === 'None') return '';
    try {
      var dt = new Date(iso);
      if (!isNaN(dt.getTime())) {
        return dt.toLocaleString('en-IN', {
          day: '2-digit',
          month: 'short',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: true,
        });
      }
      return String(iso).replace('T', ' ');
    } catch (e) {
      return String(iso);
    }
  }

  function getPresetDates(preset) {
    var today = new Date();
    var fromDt = new Date();
    var toDt = new Date();
    var label = 'Complete Lifetime History';

    switch (preset) {
      case 'month':
        fromDt.setDate(1);
        label = 'This Month (' + fmtDate(formatLocalISO(fromDt)) + ' – Today)';
        return { from: formatLocalISO(fromDt), to: formatLocalISO(toDt), label: label };
      case 'last_month':
        fromDt = new Date(today.getFullYear(), today.getMonth() - 1, 1);
        toDt = new Date(today.getFullYear(), today.getMonth(), 0);
        label = 'Last Month (' + fmtDate(formatLocalISO(fromDt)) + ' – ' + fmtDate(formatLocalISO(toDt)) + ')';
        return { from: formatLocalISO(fromDt), to: formatLocalISO(toDt), label: label };
      case 'quarter':
        var currentQ = Math.floor(today.getMonth() / 3);
        fromDt = new Date(today.getFullYear(), currentQ * 3, 1);
        label = 'This Quarter (' + fmtDate(formatLocalISO(fromDt)) + ' – Today)';
        return { from: formatLocalISO(fromDt), to: formatLocalISO(toDt), label: label };
      case 'year':
        var fyStartYear = today.getMonth() >= 3 ? today.getFullYear() : today.getFullYear() - 1;
        fromDt = new Date(fyStartYear, 3, 1);
        toDt = new Date(fyStartYear + 1, 2, 31);
        if (toDt > today) toDt = today;
        label = 'Financial Year (' + fyStartYear + '–' + (fyStartYear + 1) + ')';
        return { from: formatLocalISO(fromDt), to: formatLocalISO(toDt), label: label };
      case 'all':
      default:
        return { from: '', to: '', label: 'Complete Lifetime History' };
    }
  }

  function renderEventsTable(events, uom, isPeriodic, fromDate, periodOpeningBal) {
    var html =
      '<div class="inv-lc-table-wrap"><table class="inv-lc-table"><thead><tr>' +
      '<th style="min-width:105px;">Date</th><th>Transaction / Event</th><th>Document Ref</th><th class="num">Quantity Change</th><th class="num">Running Balance</th>' +
      '</tr></thead><tbody>';

    // Prepend periodic opening balance anchor row if period filter is active
    if (isPeriodic && fromDate) {
      html +=
        '<tr class="inv-lc-row-opening">' +
        '<td><strong>Before ' + esc(fmtDate(fromDate)) + '</strong></td>' +
        '<td><span class="inv-lc-type font-weight-bold"><i class="bi bi-box-arrow-in-right"></i> Period Opening Balance (Prior Movements)</span></td>' +
        '<td>—</td>' +
        '<td class="num font-weight-bold" style="color:#64748b;">Baseline</td>' +
        '<td class="num font-weight-bold">' + esc(periodOpeningBal || '0.000') + (uom ? ' ' + esc(uom) : '') + '</td>' +
        '</tr>';
    }

    if (!events || !events.length) {
      if (isPeriodic) {
        html +=
          '<tr><td colspan="5" class="text-center text-muted" style="padding: 20px 14px;">' +
          '<i class="bi bi-info-circle"></i> No movements recorded during this chosen period. ' +
          'Closing balance remained constant at <strong>' + esc(periodOpeningBal || '0.000') + (uom ? ' ' + esc(uom) : '') + '</strong>.' +
          '</td></tr>';
      } else {
        html += '<tr><td colspan="5" class="inv-lc-empty">No posted movements found for this batch.</td></tr>';
      }
      html += '</tbody></table></div>';
      return html;
    }

    events.forEach(function (ev) {
      var doc = ev.doc_display || '—';
      if (ev.doc_url) {
        doc = '<a href="' + esc(ev.doc_url) + '" class="inv-lc-doc-link">' + esc(ev.doc_display) + '</a>';
      }
      var detail = ev.detail ? ('<span class="inv-lc-detail">' + esc(ev.detail) + '</span>') : '';
      var n = parseFloat(ev.qty_delta);
      var deltaCls = n < 0 ? ' inv-lc-delta--neg' : (n > 0 ? ' inv-lc-delta--pos' : '');
      var dateCol = esc(fmtDate(ev.trn_date));
      if (ev.created_at) {
        dateCol += '<br><small class="text-muted" style="font-size:0.75rem;"><i class="bi bi-clock"></i> ' + esc(fmtDateTime(ev.created_at)) + '</small>';
      }
      html +=
        '<tr><td>' + dateCol + '</td>' +
        '<td><span class="inv-lc-type">' + esc(ev.label) + '</span>' + detail + '</td>' +
        '<td>' + doc + '</td>' +
        '<td class="num' + deltaCls + '">' + esc(fmtDelta(ev.qty_delta, uom)) + '</td>' +
        '<td class="num font-weight-bold">' + esc(ev.balance_after ? ev.balance_after + (uom ? ' ' + uom : '') : '—') + '</td></tr>';
    });

    html += '</tbody></table></div>';
    return html;
  }

  function renderPeriodSummary(data, uom) {
    if (!data.is_periodic) return '';

    return (
      '<div class="inv-lc-period-summary">' +
      '<div class="inv-lc-summary-card card-opening">' +
      '<span class="label">Opening Balance</span>' +
      '<span class="val">' + esc(data.period_opening_bal || '0.000') + (uom ? ' <small>' + esc(uom) + '</small>' : '') + '</span>' +
      '<span class="sub">As of ' + esc(fmtDate(data.from_date || 'Start')) + '</span>' +
      '</div>' +
      '<div class="inv-lc-summary-card card-rcpt">' +
      '<span class="label">Period Receipts (+)</span>' +
      '<span class="val">+' + esc(data.period_rcpt_qty || '0.000') + (uom ? ' <small>' + esc(uom) + '</small>' : '') + '</span>' +
      '<span class="sub">Inward / Return / DPR</span>' +
      '</div>' +
      '<div class="inv-lc-summary-card card-issue">' +
      '<span class="label">Period Issues (-)</span>' +
      '<span class="val">-' + esc(data.period_issue_qty || '0.000') + (uom ? ' <small>' + esc(uom) + '</small>' : '') + '</span>' +
      '<span class="sub">Dispensed / Invoiced</span>' +
      '</div>' +
      '<div class="inv-lc-summary-card card-closing">' +
      '<span class="label">Period Closing Balance</span>' +
      '<span class="val">' + esc(data.period_closing_bal || '0.000') + (uom ? ' <small>' + esc(uom) + '</small>' : '') + '</span>' +
      '<span class="sub">Net: ' + esc(data.period_net_change || '0.000') + '</span>' +
      '</div>' +
      '</div>'
    );
  }

  function renderEpisodes(rows) {
    if (!rows || !rows.length) return '';
    var html = '<div class="inv-lc-episodes"><h4>Ledger rows (episodes)</h4><ul>';
    rows.forEach(function (ep) {
      var st = ep.is_closed ? 'Closed' : 'Open';
      html += '<li><strong>#' + esc(ep.inv_id) + '</strong> — ' + esc(st) +
        ', qty ' + esc(ep.qty) +
        (ep.opened_fy ? (' · opened FY ' + esc(ep.opened_fy)) : '') +
        (ep.last_trn_date ? (' · last ' + esc(ep.last_trn_date) + ' ' + esc(ep.last_trn_type)) : '') +
        '</li>';
    });
    return html + '</ul></div>';
  }

  function initPage_inventory_stock() {
    var page = document.querySelector('.inv-stk-view-page');
    if (!page) return;

    var ajaxBase = page.getAttribute('data-lifecycle-url') || '';
    var modal = document.getElementById('invStkLifecycleModal');
    var modalBody = document.getElementById('invStkLifecycleBody');
    var modalTitle = document.getElementById('invStkLifecycleTitle');
    var modalSub = document.getElementById('invStkLifecycleSub');
    var closeBtn = document.getElementById('invStkLifecycleClose');

    // Period controls
    var presetBtns = document.querySelectorAll('.inv-lc-preset-btn');
    var customDatesWrap = document.getElementById('invLcCustomDates');
    var fromInput = document.getElementById('invLcFromDate');
    var toInput = document.getElementById('invLcToDate');
    var applyBtn = document.getElementById('invLcApplyBtn');
    var resetBtn = document.getElementById('invLcResetBtn');
    var scopeText = document.getElementById('invLcScopeText');

    var currentInvId = null;
    var currentPreset = 'all';
    var currentFromDate = '';
    var currentToDate = '';

    function closeModal() {
      if (modal) modal.style.display = 'none';
      document.body.classList.remove('inv-stk-modal-open');
      currentInvId = null;
    }

    function openModal() {
      if (modal) modal.style.display = 'flex';
      document.body.classList.add('inv-stk-modal-open');
    }

    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    if (modal) {
      modal.addEventListener('click', function (e) {
        if (e.target === modal) closeModal();
      });
    }
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && modal && modal.style.display === 'flex') closeModal();
    });

    function setPresetActive(preset) {
      currentPreset = preset;
      presetBtns.forEach(function (btn) {
        if (btn.getAttribute('data-preset') === preset) {
          btn.classList.add('active');
        } else {
          btn.classList.remove('active');
        }
      });
    }

    function loadLifecycleData() {
      if (!currentInvId || !ajaxBase) return;

      if (modalBody) {
        modalBody.innerHTML = '<div class="inv-lc-loading-wrap"><div class="inv-lc-spinner"></div><p>Retrieving movement history for period…</p></div>';
      }

      var url = ajaxBase + '?inv_id=' + encodeURIComponent(currentInvId);
      if (currentFromDate) url += '&from_date=' + encodeURIComponent(currentFromDate);
      if (currentToDate) url += '&to_date=' + encodeURIComponent(currentToDate);

      fetch(url, {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      })
        .then(function (r) {
          return r.json().then(function (j) {
            if (!r.ok) throw new Error(j.error || r.statusText);
            return j;
          });
        })
        .then(function (data) {
          if (modalSub) {
            modalSub.textContent = (data.sku_name || 'SKU') + ' · Batch: ' + (data.batch_no || '—') + ' · Customer: ' + (data.customer_name || '—');
          }
          if (modalBody) {
            modalBody.innerHTML = renderPayload(data);
          }
        })
        .catch(function (err) {
          if (modalBody) {
            modalBody.innerHTML = '<p class="inv-lc-error"><i class="bi bi-exclamation-triangle-fill"></i> ' + esc(err.message || 'Could not load history.') + '</p>';
          }
        });
    }

    function renderPayload(data) {
      var uom = (data.uom || '').trim();
      var html = '<div class="inv-lc-summary">';

      html +=
        '<div class="inv-lc-meta-grid">' +
        '<div><span class="inv-lc-meta-label">Customer:</span> <strong>' + esc(data.customer_name) + '</strong></div>' +
        '<div><span class="inv-lc-meta-label">Material / SKU:</span> <strong>' + esc(data.sku_name) + '</strong>' + (uom ? ' <span class="inv-lc-uom-pill">' + esc(uom) + '</span>' : '') + '</div>' +
        '<div><span class="inv-lc-meta-label">Batch No:</span> <strong class="inv-lc-batch-badge">' + esc(data.batch_no) + '</strong></div>' +
        '<div><span class="inv-lc-meta-label">Current Ledger Balance:</span> <strong class="text-primary">' + esc(data.ledger_qty) + '</strong> ' + esc(uom) + '</div>' +
        '</div>';

      html += '</div>';

      // 4-Card Periodic Financial Metrics
      html += renderPeriodSummary(data, uom);

      // Movements Table Heading with counter
      var countLabel = data.is_periodic
        ? 'Period Movements (' + (data.period_events_count || 0) + ' of ' + (data.all_time_events_count || 0) + ' lifetime)'
        : 'Lifetime Batch Movements (' + (data.all_time_events_count || (data.events ? data.events.length : 0)) + ' records)';

      html += '<div class="inv-lc-section-header">';
      html += '<h4 class="inv-lc-section-title"><i class="bi bi-arrow-left-right"></i> ' + esc(countLabel) + '</h4>';
      html += '</div>';

      html += renderEventsTable(data.events, uom, data.is_periodic, data.from_date, data.period_opening_bal);

      if (data.item_level_events && data.item_level_events.length) {
        html += '<h4 class="inv-lc-section-title">Item-level issues (no batch)</h4>';
        if (data.note) {
          html += '<p class="inv-lc-note">' + esc(data.note) + '</p>';
        }
        html += renderEventsTable(data.item_level_events, uom, false);
      }

      html += renderEpisodes(data.ledger_episodes);
      return html;
    }

    // Preset button click listeners
    presetBtns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var preset = btn.getAttribute('data-preset');
        setPresetActive(preset);

        if (preset === 'custom') {
          if (customDatesWrap) customDatesWrap.style.display = 'flex';
          if (fromInput) fromInput.focus();
        } else {
          if (customDatesWrap) customDatesWrap.style.display = 'none';
          var dates = getPresetDates(preset);
          currentFromDate = dates.from;
          currentToDate = dates.to;
          if (fromInput) fromInput.value = dates.from;
          if (toInput) toInput.value = dates.to;
          if (scopeText) scopeText.textContent = 'Scope: ' + dates.label;
          loadLifecycleData();
        }
      });
    });

    // Custom Apply listener
    if (applyBtn) {
      applyBtn.addEventListener('click', function () {
        var fv = fromInput ? fromInput.value.trim() : '';
        var tv = toInput ? toInput.value.trim() : '';

        if (!fv && !tv) {
          alert('Please select at least a From Date or To Date.');
          return;
        }
        if (fv && tv && fv > tv) {
          alert('From Date cannot be later than To Date.');
          return;
        }

        currentFromDate = fv;
        currentToDate = tv;
        var label = 'Custom Range (' + (fv ? fmtDate(fv) : 'Beginning') + ' – ' + (tv ? fmtDate(tv) : 'Today') + ')';
        if (scopeText) scopeText.textContent = 'Scope: ' + label;
        loadLifecycleData();
      });
    }

    // Reset listener
    if (resetBtn) {
      resetBtn.addEventListener('click', function () {
        setPresetActive('all');
        if (customDatesWrap) customDatesWrap.style.display = 'none';
        currentFromDate = '';
        currentToDate = '';
        if (fromInput) fromInput.value = '';
        if (toInput) toInput.value = '';
        if (scopeText) scopeText.textContent = 'Scope: Complete Lifetime History';
        loadLifecycleData();
      });
    }

    // Trigger open modal on History button click
    page.addEventListener('click', function (e) {
      var btn = e.target.closest('.inv-stk-lifecycle-btn');
      if (!btn) return;
      var invId = btn.getAttribute('data-inv-id');
      if (!invId || !ajaxBase) return;

      currentInvId = invId;

      // Reset filter toolbar to All Time on new modal open
      setPresetActive('all');
      if (customDatesWrap) customDatesWrap.style.display = 'none';
      currentFromDate = '';
      currentToDate = '';
      if (fromInput) fromInput.value = '';
      if (toInput) toInput.value = '';
      if (scopeText) scopeText.textContent = 'Scope: Complete Lifetime History';

      if (modalTitle) modalTitle.textContent = 'Stock Movement History & Lifecycle';
      if (modalSub) modalSub.textContent = 'Loading…';
      openModal();
      loadLifecycleData();
    });
  }

  window.initPage_inventory_stock = initPage_inventory_stock;
})();
