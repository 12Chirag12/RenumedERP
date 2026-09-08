/**
 * Inventory stock browse — batch lifecycle modal.
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

  function renderEventsTable(events, uom, emptyMsg) {
    if (!events || !events.length) {
      return '<p class="inv-lc-empty">' + esc(emptyMsg) + '</p>';
    }
    var html =
      '<div class="inv-lc-table-wrap"><table class="inv-lc-table"><thead><tr>' +
      '<th>Date</th><th>Transaction</th><th>Document</th><th class="num">Change</th><th class="num">Balance</th>' +
      '</tr></thead><tbody>';
    events.forEach(function (ev) {
      var doc = ev.doc_display || '—';
      if (ev.doc_url) {
        doc = '<a href="' + esc(ev.doc_url) + '" class="inv-lc-doc-link">' + esc(ev.doc_display) + '</a>';
      }
      var detail = ev.detail ? ('<span class="inv-lc-detail">' + esc(ev.detail) + '</span>') : '';
      var n = parseFloat(ev.qty_delta);
      var deltaCls = n < 0 ? ' inv-lc-delta--neg' : (n > 0 ? ' inv-lc-delta--pos' : '');
      html +=
        '<tr><td>' + esc(ev.trn_date) + '</td>' +
        '<td><span class="inv-lc-type">' + esc(ev.label) + '</span>' + detail + '</td>' +
        '<td>' + doc + '</td>' +
        '<td class="num' + deltaCls + '">' + esc(fmtDelta(ev.qty_delta, uom)) + '</td>' +
        '<td class="num">' + esc(ev.balance_after ? ev.balance_after + (uom ? ' ' + uom : '') : '—') + '</td></tr>';
    });
    return html + '</tbody></table></div>';
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

    function closeModal() {
      if (modal) modal.style.display = 'none';
      document.body.classList.remove('inv-stk-modal-open');
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

    function renderPayload(data) {
      var uom = (data.uom || '').trim();
      var html =
        '<div class="inv-lc-summary">' +
        '<p><strong>Customer:</strong> ' + esc(data.customer_name) + '</p>' +
        '<p><strong>SKU:</strong> ' + esc(data.sku_name) +
        (uom ? ' <span class="inv-lc-uom">(' + esc(uom) + ')</span>' : '') + '</p>' +
        '<p><strong>Batch:</strong> ' + esc(data.batch_no) + '</p>' +
        '<p class="inv-lc-balances"><strong>Ledger (open):</strong> ' + esc(data.ledger_qty) +
        (uom ? ' ' + esc(uom) : '') +
        ' · <strong>Recomputed from history:</strong> ' + esc(data.computed_balance) +
        (uom ? ' ' + esc(uom) : '') +
        (data.balance_matches_ledger === false
          ? ' <span class="inv-lc-warn">(mismatch — check edits/reversals)</span>'
          : '') +
        '</p></div>';

      html += '<h4 class="inv-lc-section-title">Batch movements</h4>';
      html += renderEventsTable(data.events, uom, 'No posted movements for this batch.');

      if (data.item_level_events && data.item_level_events.length) {
        html += '<h4 class="inv-lc-section-title">Item-level issues (no batch)</h4>';
        if (data.note) {
          html += '<p class="inv-lc-note">' + esc(data.note) + '</p>';
        }
        html += renderEventsTable(data.item_level_events, uom, 'No item-level dispensing.');
      }

      html += renderEpisodes(data.ledger_episodes);
      return html;
    }

    page.addEventListener('click', function (e) {
      var btn = e.target.closest('.inv-stk-lifecycle-btn');
      if (!btn) return;
      var invId = btn.getAttribute('data-inv-id');
      if (!invId || !ajaxBase) return;

      if (modalTitle) modalTitle.textContent = 'Stock lifecycle';
      if (modalSub) modalSub.textContent = 'Loading…';
      if (modalBody) modalBody.innerHTML = '<p class="inv-lc-loading">Loading movement history…</p>';
      openModal();

      fetch(ajaxBase + '?inv_id=' + encodeURIComponent(invId), {
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
            modalSub.textContent = (data.sku_name || 'SKU') + ' · batch ' + (data.batch_no || '—');
          }
          if (modalBody) modalBody.innerHTML = renderPayload(data);
        })
        .catch(function (err) {
          if (modalSub) modalSub.textContent = '';
          if (modalBody) {
            modalBody.innerHTML = '<p class="inv-lc-error">' + esc(err.message || 'Could not load history.') + '</p>';
          }
        });
    });
  }

  window.initPage_inventory_stock = initPage_inventory_stock;
})();
