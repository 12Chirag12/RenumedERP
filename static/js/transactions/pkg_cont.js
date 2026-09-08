/**
 * Daily packing (contractors) — customer → product → log sheet batch → packing style → save.
 * Reuses DPR logsheet AJAX for batch rows (same cust + prod filter).
 */
(function () {
  'use strict';

  function readJsonObject(id) {
    var el = document.getElementById(id);
    if (!el) return {};
    var raw = (el.textContent || '').trim();
    if (!raw) return {};
    try {
      var o = JSON.parse(raw);
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

  function initPage_pkg_cont() {
    var form = document.getElementById('pcForm');
    if (!form) return;

    var urls = readJsonObject('pcAjaxUrls');
    var gridDefaults = readJsonObject('pcGridDefaults');
    var editBase = form && form.action ? form.action.split('?')[0] : ((window.location.pathname || '').split('?')[0]);
    var customer = document.getElementById('pcCustomer');
    var product = document.getElementById('pcProduct');
    var batchSelect = document.getElementById('pcBatchSelect');
    var batchHidden = document.getElementById('pcLogsheetId');
    var pkgStyle = document.getElementById('pcPkgStyle');
    var listBody = document.getElementById('pcListBody');
    var listCount = document.getElementById('pcListCount');
    var gridStart = document.getElementById('pcGridStart');
    var gridEnd = document.getElementById('pcGridEnd');
    var gridErr = document.getElementById('pcGridErr');
    var btnShowGrid = document.getElementById('pcShowGrid');

    var fetchOpts = { credentials: 'same-origin', headers: { Accept: 'application/json' } };

    var isEdit = !!(form.querySelector('input[name="edit_pk"]'));
    var editBootstrapDone = false;

    if (typeof initSearchableDropdowns === 'function') {
      initSearchableDropdowns(form);
    }

    function setGridErr(msg) {
      if (gridErr) gridErr.textContent = msg || '';
    }

    function resetBatchUI(preserveHidden) {
      if (batchSelect) {
        batchSelect.innerHTML = '<option value="">— Select batch —</option>';
        batchSelect.value = '';
      }
      if (batchHidden && !preserveHidden) batchHidden.value = '';
      rebuildSelect2(batchSelect);
    }

    function resetStyleUI() {
      if (!pkgStyle) return;
      pkgStyle.innerHTML = '<option value="">— Select packing style —</option>';
      pkgStyle.value = '';
      rebuildSelect2(pkgStyle);
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
    }

    function setStyleOptions(rows, savedStyleId) {
      if (!pkgStyle) return;
      var cur = '';
      if (savedStyleId != null && String(savedStyleId).trim() !== '') {
        cur = String(savedStyleId).trim();
      } else if (pkgStyle.value) {
        cur = String(pkgStyle.value).trim();
      }
      pkgStyle.innerHTML = '<option value="">— Select packing style —</option>';
      (rows || []).forEach(function (r) {
        var o = document.createElement('option');
        o.value = String(r.pkg_style_id);
        o.textContent = r.pkg_style_name || ('Style ' + r.pkg_style_id);
        pkgStyle.appendChild(o);
      });
      if (cur && [].some.call(pkgStyle.options, function (op) { return op.value === cur; })) {
        pkgStyle.value = cur;
      }
      rebuildSelect2(pkgStyle);
      if (window.jQuery && pkgStyle.classList.contains('searchable-dropdown') && cur) {
        try {
          window.jQuery(pkgStyle).val(cur).trigger('change');
        } catch (e) { /* ignore */ }
      }
    }

    function setBatchOptions(rows, savedLogsheetId) {
      if (!batchSelect) return;
      var cur = '';
      if (savedLogsheetId != null && String(savedLogsheetId).trim() !== '') {
        cur = String(savedLogsheetId).trim();
      } else if (batchHidden && batchHidden.value) {
        cur = String(batchHidden.value).trim();
      } else if (batchSelect.value) {
        cur = String(batchSelect.value).trim();
      }
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
      }
      applySelectedBatch();
      rebuildSelect2(batchSelect);
      if (window.jQuery && batchSelect.classList.contains('searchable-dropdown') && cur) {
        try {
          window.jQuery(batchSelect).val(cur).trigger('change');
        } catch (e) { /* ignore */ }
      }
    }

    function applySelectedBatch() {
      if (!batchSelect || !batchHidden) return;
      batchHidden.value = batchSelect.value || '';
    }

    function fetchCustomerProducts(opts) {
      opts = opts || {};
      resetBatchUI(!!opts.preserveHidden);
      if (!opts.preservePkgStyle) {
        resetStyleUI();
      }
      if (!customer || !customer.value) {
        setProductOptions([]);
        return;
      }
      if (!urls.products) return;
      fetch(urls.products + '?cust_id=' + encodeURIComponent(customer.value), fetchOpts)
        .then(function (r) { return r.json(); })
        .then(function (d) {
          setProductOptions(d.products || []);
          if (isEdit && product && product.value && !editBootstrapDone) {
            editBootstrapDone = true;
            fetchLogsheetsAndStyles({ preserveHidden: !!opts.preserveHidden });
          } else if (product && product.value) {
            fetchLogsheetsAndStyles({ preserveHidden: !!opts.preserveHidden });
          }
        })
        .catch(function () { setProductOptions([]); });
    }

    function fetchStyles(savedStyleId) {
      if (!urls.styles || !product || !product.value) {
        setStyleOptions([], savedStyleId);
        return;
      }
      fetch(urls.styles + '?prod_id=' + encodeURIComponent(product.value), fetchOpts)
        .then(function (r) { return r.json(); })
        .then(function (d) {
          setStyleOptions(d.styles || [], savedStyleId);
        })
        .catch(function () {
          setStyleOptions([], savedStyleId);
        });
    }

    function fetchLogsheetsAndStyles(opts) {
      opts = opts || {};
      var savedLogsheet = (batchHidden && batchHidden.value) ? batchHidden.value : '';
      var savedStyle = (pkgStyle && pkgStyle.value) ? pkgStyle.value : '';
      resetBatchUI(!!opts.preserveHidden);
      fetchStyles(savedStyle);
      if (!customer || !customer.value || !product || !product.value) return;
      if (!urls.logsheets) return;
      var q = '?cust_id=' + encodeURIComponent(customer.value) + '&prod_id=' + encodeURIComponent(product.value);
      fetch(urls.logsheets + q, fetchOpts)
        .then(function (r) { return r.json(); })
        .then(function (d) {
          setBatchOptions(d.logsheets || [], savedLogsheet);
        })
        .catch(function () {
          setBatchOptions([], savedLogsheet);
        });
    }

    function renderListRows(rows) {
      if (!listBody) return;
      listBody.innerHTML = '';
      if (!rows || !rows.length) {
        listBody.innerHTML = '<tr><td colspan="12" class="empty-row">No entries in this range.</td></tr>';
        if (listCount) listCount.textContent = '(0)';
        return;
      }
      if (listCount) listCount.textContent = '(' + String(rows.length) + ')';
      rows.forEach(function (r) {
        var tr = document.createElement('tr');
        var editHref = editBase + '?edit_pk=' + encodeURIComponent(r.pkgcont_id);
        tr.innerHTML =
          '<td class="col-idx">' + esc(r.pkgcont_id) + '</td>' +
          '<td>' + esc(r.pkgcont_dt || '') + '</td>' +
          '<td>' + esc(r.contractor || '') + '</td>' +
          '<td>' + esc(r.product || '') + '</td>' +
          '<td>' + esc(r.batch || '') + '</td>' +
          '<td>' + esc(r.pkg_style || '') + '</td>' +
          '<td class="cu-num">' + esc(r.no_of_girls !== '' && r.no_of_girls != null ? r.no_of_girls : '—') + '</td>' +
          '<td class="cu-num">' + esc(r.shipper_no) + '</td>' +
          '<td class="cu-num">' + esc(r.qty_nos) + '</td>' +
          '<td class="cu-num">' + esc(r.qty_loose || '—') + '</td>' +
          '<td>' + esc(r.remarks || '') + '</td>' +
          '<td class="col-actions">' +
          '<a href="' + esc(editHref) + '" class="btn-action btn-edit" title="Edit"><i class="bi bi-pencil"></i></a>' +
          '<button type="button" class="btn-action btn-delete" data-delete-url="' + esc(r.delete_url) + '" data-delete-name="Entry ' + esc(r.pkgcont_id) + '" onclick="openDeleteModal(this.dataset.deleteUrl, this.dataset.deleteName)"><i class="bi bi-trash"></i></button>' +
          '</td>';
        listBody.appendChild(tr);
      });
    }

    /**
     * Same contract as DPR loadGrid: only start/end query params, require both dates,
     * parse body as text then JSON so HTML error pages do not throw before we can show a message.
     */
    function loadGrid() {
      if (!urls.listRows || !listBody) return;
      var s = gridStart && gridStart.value;
      var e = gridEnd && gridEnd.value;
      setGridErr('');
      if (!s || !e) {
        setGridErr('Choose start and end dates.');
        return;
      }
      var url = urls.listRows + '?start=' + encodeURIComponent(s) + '&end=' + encodeURIComponent(e);
      fetch(url, fetchOpts)
        .then(function (r) {
          return r.text().then(function (text) {
            var data = {};
            if (text) {
              try {
                data = JSON.parse(text);
              } catch (parseErr) {
                setGridErr('Could not load list (server did not return JSON).');
                listBody.innerHTML =
                  '<tr><td colspan="12" class="empty-row">Could not load list (server did not return JSON).</td></tr>';
                if (listCount) listCount.textContent = '';
                return;
              }
            }
            if (data.error) {
              setGridErr(data.error);
              listBody.innerHTML =
                '<tr><td colspan="12" class="empty-row">' + esc(data.error) + '</td></tr>';
              if (listCount) listCount.textContent = '';
              return;
            }
            if (!r.ok) {
              setGridErr('Could not load list (HTTP ' + r.status + ').');
              listBody.innerHTML =
                '<tr><td colspan="12" class="empty-row">Could not load list (HTTP ' + esc(String(r.status)) + ').</td></tr>';
              if (listCount) listCount.textContent = '';
              return;
            }
            setGridErr('');
            renderListRows(data.rows || []);
          });
        })
        .catch(function () {
          setGridErr('Could not load list.');
          listBody.innerHTML = '<tr><td colspan="12" class="empty-row">Could not load list.</td></tr>';
          if (listCount) listCount.textContent = '';
        });
    }

    function applyGridDefaults() {
      if (gridStart && gridDefaults.start) gridStart.value = gridDefaults.start;
      if (gridEnd && gridDefaults.end) gridEnd.value = gridDefaults.end;
    }

    if (customer) {
      customer.addEventListener('change', function () {
        editBootstrapDone = true;
        fetchCustomerProducts();
      });
    }
    if (product) {
      product.addEventListener('change', function () {
        editBootstrapDone = true;
        fetchLogsheetsAndStyles();
      });
    }
    if (batchSelect) batchSelect.addEventListener('change', applySelectedBatch);
    if (btnShowGrid) {
      btnShowGrid.addEventListener('click', loadGrid);
    }

    form.addEventListener('submit', function (e) {
      var sh = document.getElementById('pcShipper');
      var qn = document.getElementById('pcQtyNos');
      if (sh && sh.value) {
        var sn = parseInt(String(sh.value), 10);
        if (!isFinite(sn) || sn < 1) {
          e.preventDefault();
          return;
        }
      }
      if (qn && qn.value) {
        var qv = parseFloat(String(qn.value).replace(',', '.'));
        if (!isFinite(qv) || qv < 1) {
          e.preventDefault();
          return;
        }
      }
    });

    applyGridDefaults();
    if (isEdit) {
      if (customer && customer.value) {
        fetchCustomerProducts({ preserveHidden: true, preservePkgStyle: true });
      } else if (product && product.value) {
        fetchLogsheetsAndStyles({ preserveHidden: true });
      }
    } else {
      if (customer && customer.value) fetchCustomerProducts();
      if (customer && customer.value && product && product.value) fetchLogsheetsAndStyles();
    }
    if (urls.listRows && gridStart && gridEnd && gridStart.value && gridEnd.value) {
      loadGrid();
    }
  }

  window.initPage_pkg_cont = initPage_pkg_cont;
})();
