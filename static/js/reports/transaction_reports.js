/**
 * Transaction Reports — single page, config-driven preview and exports.
 * Exposes window.initPage_transaction_reports for HTMX partial loads.
 */

(function () {
  'use strict';

  var state = {
    config: null,
    slug: null,
    flatPage: 1,
    flatPerPage: 25,
    groupPage: 1,
    groupPerPage: 10,
    optionsCache: {},
  };

  var previewDebounceMs = 400;
  var previewTimer = null;
  var previewSeq = 0;

  var docTitleBeforePrint = '';
  var docTitleSwapActive = false;

  /** Short title for the browser print header (avoids default "… — PharmaERP" and avoids empty → URL). */
  function printTitleForBrowserHeader() {
    var pt = document.getElementById('trPrintTitle');
    var label = pt && pt.textContent ? pt.textContent.trim() : '';
    if (!label) {
      var rs = document.getElementById('trReportSelect');
      if (rs && rs.selectedOptions[0]) label = rs.selectedOptions[0].textContent.trim();
    }
    if (label) return label.slice(0, 120);
    var root = document.getElementById('transactionReportsRoot');
    if (root) {
      var ch = root.getAttribute('data-company-header');
      if (ch && ch.trim()) return ch.trim().slice(0, 120);
    }
    return 'Report';
  }

  function wirePrintDocumentTitleOnce() {
    if (window.__trPrintDocTitleHook) return;
    window.__trPrintDocTitleHook = true;
    window.addEventListener('beforeprint', function () {
      if (!document.getElementById('transactionReportsRoot')) return;
      docTitleBeforePrint = document.title;
      docTitleSwapActive = true;
      /* Browser print header uses <title>; use report label only (no page suffix, not blank → URL). */
      document.title = printTitleForBrowserHeader();
    });
    window.addEventListener('afterprint', function () {
      if (!docTitleSwapActive) return;
      docTitleSwapActive = false;
      document.title = docTitleBeforePrint;
    });
  }

  function getRoot() {
    return document.getElementById('transactionReportsRoot');
  }

  function getCsrfToken() {
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  function apiUrls() {
    var root = getRoot();
    if (!root) return {};
    return {
      options: root.getAttribute('data-api-options'),
      data: root.getAttribute('data-api-data'),
      excel: root.getAttribute('data-api-excel'),
    };
  }

  function showError(msg) {
    var el = document.getElementById('trError');
    if (!el) return;
    el.textContent = msg || '';
    el.hidden = !msg;
  }

  function setLoading(on) {
    var el = document.getElementById('trLoading');
    if (el) el.hidden = !on;
  }

  function setMeta(data) {
    var bar = document.getElementById('trMetaBar');
    var txt = document.getElementById('trMetaText');
    if (!bar || !txt) return;
    if (data && data.meta) {
      bar.hidden = false;
      txt.textContent =
        'Generated: ' +
        (data.meta.generated_at_display || '') +
        ' | User: ' +
        (data.meta.user_display || '');
    } else {
      bar.hidden = true;
    }
  }

  function getSlug() {
    var sel = document.getElementById('trReportSelect');
    return sel ? sel.value : '';
  }

  function getConfigUrl() {
    var sel = document.getElementById('trReportSelect');
    if (!sel || !sel.selectedOptions[0]) return '';
    return sel.selectedOptions[0].getAttribute('data-config-url') || '';
  }

  function fetchOptions(reportSlug, filterKey) {
    var cacheKey = reportSlug + ':' + filterKey;
    if (state.optionsCache[cacheKey]) {
      return Promise.resolve(state.optionsCache[cacheKey]);
    }
    var urls = apiUrls();
    var u = urls.options + '?report=' + encodeURIComponent(reportSlug) + '&filter=' + encodeURIComponent(filterKey);
    return fetch(u, { credentials: 'same-origin' })
      .then(readJsonBody)
      .then(function (x) {
        var opts = x.ok && x.j && x.j.options ? x.j.options : [];
        state.optionsCache[cacheKey] = opts;
        return state.optionsCache[cacheKey];
      });
  }

  function renderFilterOptions(key, options) {
    var host = document.getElementById('tr_opts_' + key);
    if (!host) return;
    host.innerHTML = '';
    options.forEach(function (opt) {
      var id = 'tr_f_' + key + '_' + opt.id;
      var lab = document.createElement('label');
      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.name = 'f_' + key + '_id';
      cb.value = String(opt.id);
      cb.id = id;
      lab.appendChild(cb);
      lab.appendChild(document.createTextNode(' ' + opt.label));
      host.appendChild(lab);
    });
  }

  function wireFilterMode(key) {
    var radios = document.querySelectorAll('input[name="f_' + key + '_mode"]');
    var scroll = document.getElementById('tr_opts_' + key);
    radios.forEach(function (r) {
      r.addEventListener('change', function () {
        var on = r.value === 'select';
        if (scroll) scroll.style.opacity = on ? '1' : '0.45';
        if (scroll) {
          scroll.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
            cb.disabled = !on;
          });
        }
      });
    });
    var checked = document.querySelector('input[name="f_' + key + '_mode"]:checked');
    if (checked) checked.dispatchEvent(new Event('change'));
  }

  function renderFilters(cfg) {
    var host = document.getElementById('trFiltersDynamic');
    if (!host) return;
    host.innerHTML = '';
    state.optionsCache = {};

    (cfg.filters || []).forEach(function (f) {
      if (f.kind === 'all_or_multiselect') {
        var block = document.createElement('div');
        block.className = 'tr-filter-block';
        block.innerHTML =
          '<div class="tr-filter-title">' +
          escapeHtml(f.label) +
          ' :</div>' +
          '<div class="tr-radio-row">' +
          '<label><input type="radio" name="f_' +
          f.key +
          '_mode" value="all" checked> All</label>' +
          '<label><input type="radio" name="f_' +
          f.key +
          '_mode" value="select"> Select</label>' +
          '</div>' +
          (f.list_label ? '<div class="tr-list-label">' + escapeHtml(f.list_label) + '</div>' : '') +
          '<div class="tr-check-scroll" id="tr_opts_' +
          f.key +
          '"></div>';
        host.appendChild(block);
        wireFilterMode(f.key);
        fetchOptions(cfg.slug, f.key).then(function (opts) {
          renderFilterOptions(f.key, opts);
          wireFilterMode(f.key);
        });
      } else if (f.kind === 'capsule_layout') {
        var b2 = document.createElement('div');
        b2.className = 'tr-filter-block';
        var opts = f.options || [];
        var radios = opts
          .map(function (o, i) {
            return (
              '<label><input type="radio" name="tr_capsule_layout" value="' +
              escapeHtml(o.value) +
              '"' +
              (i === 0 ? ' checked' : '') +
              '> ' +
              escapeHtml(o.label) +
              '</label>'
            );
          })
          .join(' ');
        b2.innerHTML =
          '<div class="tr-filter-title">' +
          escapeHtml(f.label) +
          ' :</div><div class="tr-radio-row">' +
          radios +
          '</div>';
        host.appendChild(b2);
      } else if (f.kind === 'radio_choice') {
        var b3 = document.createElement('div');
        b3.className = 'tr-filter-block';
        var iname = f.input_name || 'tr_radio_' + f.key;
        var ropts = f.options || [];
        var rhtml = ropts
          .map(function (o, i) {
            return (
              '<label><input type="radio" name="' +
              escapeHtml(iname) +
              '" value="' +
              escapeHtml(o.value) +
              '"' +
              (i === 0 ? ' checked' : '') +
              '> ' +
              escapeHtml(o.label) +
              '</label>'
            );
          })
          .join(' ');
        var rowCls =
          'tr-radio-row' + (f.radio_layout === 'vertical' ? ' tr-radio-col' : '');
        b3.innerHTML =
          '<div class="tr-filter-title">' +
          escapeHtml(f.label) +
          ' :</div><div class="' +
          rowCls +
          '">' +
          rhtml +
          '</div>';
        host.appendChild(b3);
      } else if (f.kind === 'date_range') {
        var dr = document.createElement('div');
        dr.className = 'tr-filter-block';
        var phf = escapeHtml(f.placeholder_from || 'From');
        var pht = escapeHtml(f.placeholder_to || 'To');
        dr.innerHTML =
          '<div class="tr-filter-title">' +
          escapeHtml(f.label) +
          ' :</div>' +
          '<div class="tr-date-range-row">' +
          '<input type="date" class="tr-date-input" id="tr_dr_' +
          escapeHtml(f.key) +
          '_from" aria-label="' +
          phf +
          '">' +
          '<span class="tr-date-sep">—</span>' +
          '<input type="date" class="tr-date-input" id="tr_dr_' +
          escapeHtml(f.key) +
          '_to" aria-label="' +
          pht +
          '">' +
          '</div>';
        host.appendChild(dr);
      } else if (f.kind === 'date_single') {
        var ds = document.createElement('div');
        ds.className = 'tr-filter-block';
        ds.innerHTML =
          '<div class="tr-filter-title">' +
          escapeHtml(f.label) +
          ' :</div>' +
          '<div class="tr-date-range-row">' +
          '<input type="date" class="tr-date-input" id="tr_ds_' +
          escapeHtml(f.key) +
          '" aria-label="' +
          escapeHtml(f.label) +
          '">' +
          '</div>';
        host.appendChild(ds);
        if (f.default_today) {
          var inpDs = document.getElementById('tr_ds_' + f.key);
          if (inpDs && !inpDs.value) {
            var now = new Date();
            var y = now.getFullYear();
            var mo = String(now.getMonth() + 1);
            if (mo.length === 1) mo = '0' + mo;
            var da = String(now.getDate());
            if (da.length === 1) da = '0' + da;
            inpDs.value = y + '-' + mo + '-' + da;
          }
        }
      } else if (f.kind === 'text_input') {
        var ti = document.createElement('div');
        ti.className = 'tr-filter-block';
        var p = f.placeholder ? escapeHtml(f.placeholder) : '';
        ti.innerHTML =
          '<div class="tr-filter-title">' +
          escapeHtml(f.label) +
          ' :</div>' +
          '<input type="text" class="tr-text-filter-input" id="tr_txt_' +
          escapeHtml(f.key) +
          '" placeholder="' +
          p +
          '" autocomplete="off">';
        host.appendChild(ti);
      } else if (f.kind === 'inward_grn_select') {
        var ig = document.createElement('div');
        ig.className = 'tr-filter-block';
        var ph = escapeHtml(f.placeholder_option || '— Select —');
        ig.innerHTML =
          '<div class="tr-filter-title">' +
          escapeHtml(f.label) +
          ' :</div>' +
          '<select class="tr-select" id="tr_sel_' +
          escapeHtml(f.key) +
          '" style="min-width:min(100%,28rem)">' +
          '<option value="">' +
          ph +
          '</option></select>';
        host.appendChild(ig);
        fetchOptions(cfg.slug, f.key).then(function (opts) {
          var el = document.getElementById('tr_sel_' + f.key);
          if (!el) return;
          var cur = el.value;
          opts.forEach(function (o) {
            var opt = document.createElement('option');
            opt.value = String(o.id);
            opt.textContent = o.label || String(o.id);
            el.appendChild(opt);
          });
          if (cur) el.value = cur;
        });
      }
    });

    if ((cfg.group_by_options || []).length > 1) {
      var gb = document.createElement('div');
      gb.className = 'tr-filter-block';
      var opts = (cfg.group_by_options || [])
        .map(function (o) {
          return (
            '<option value="' +
            escapeHtml(o.value) +
            '"' +
            (o.value === (cfg.default_group_by || 'none') ? ' selected' : '') +
            '>' +
            escapeHtml(o.label) +
            '</option>'
          );
        })
        .join('');
      gb.innerHTML =
        '<div class="tr-filter-title">Group by</div><select id="trGroupBy" class="tr-select" style="min-width:100%">' +
        opts +
        '</select>';
      host.appendChild(gb);
    }
  }

  function escapeHtml(s) {
    if (!s && s !== 0) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function getColumnDefs(cfg) {
    if (!cfg) return [];
    if (cfg.slug === 'customer_master') {
      var rc = document.querySelector('input[name="tr_customer_view"]:checked');
      if (rc && rc.value === 'customer_products' && cfg.columns_customer_products) {
        return cfg.columns_customer_products;
      }
    }
    if (cfg.slug === 'bom_master') {
      var rb = document.querySelector('input[name="tr_bom_row_mode"]:checked');
      if (rb && rb.value === 'spec_wise_items' && cfg.columns_bom_spec_groups) {
        return cfg.columns_bom_spec_groups;
      }
    }
    return cfg.columns || [];
  }

  function resolveDefaultSort(cfg) {
    if (!cfg) return {};
    if (cfg.slug === 'customer_master') {
      var rc = document.querySelector('input[name="tr_customer_view"]:checked');
      if (rc && rc.value === 'customer_products' && cfg.default_sort_customer_products) {
        return cfg.default_sort_customer_products;
      }
    }
    if (cfg.slug === 'bom_master') {
      var rb = document.querySelector('input[name="tr_bom_row_mode"]:checked');
      if (rb && rb.value === 'spec_wise_items' && cfg.default_sort_bom_spec_groups) {
        return cfg.default_sort_bom_spec_groups;
      }
    }
    return cfg.default_sort || {};
  }

  function renderColumns(cfg) {
    var block = document.getElementById('trColumnsBlock');
    var host = document.getElementById('trColumnsHost');
    if (!block || !host) return;
    var cols = getColumnDefs(cfg);
    if (!cols.length) {
      block.hidden = true;
      return;
    }
    block.hidden = false;
    host.innerHTML = '';
    cols.forEach(function (c) {
      var id = 'tr_col_' + c.key;
      var lab = document.createElement('label');
      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.name = 'tr_col';
      cb.value = c.key;
      cb.id = id;
      cb.checked = !!c.default;
      lab.appendChild(cb);
      lab.appendChild(document.createTextNode(' ' + c.label));
      host.appendChild(lab);
    });

    var modes = document.querySelectorAll('input[name="tr_col_mode"]');
    modes.forEach(function (r) {
      r.addEventListener('change', function () {
        var on = r.value === 'select';
        host.style.opacity = on ? '1' : '0.45';
        host.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
          cb.disabled = !on;
        });
        if (!on) {
          host.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
            cb.checked = true;
          });
        }
      });
    });
    var chk = document.querySelector('input[name="tr_col_mode"]:checked');
    if (chk) chk.dispatchEvent(new Event('change'));
  }

  function selectedColumns(cfg) {
    var defs = getColumnDefs(cfg);
    var colMode = document.querySelector('input[name="tr_col_mode"]:checked');
    if (!colMode || colMode.value === 'all') {
      return defs.map(function (c) {
        return c.key;
      });
    }
    return Array.prototype.slice
      .call(document.querySelectorAll('input[name="tr_col"]:checked'))
      .map(function (cb) {
        return cb.value;
      });
  }

  function readFilters(cfg) {
    var out = {};
    (cfg.filters || []).forEach(function (f) {
      if (f.kind === 'all_or_multiselect') {
        var modeEl = document.querySelector('input[name="f_' + f.key + '_mode"]:checked');
        var mode = modeEl ? modeEl.value : 'all';
        var ids = Array.prototype.slice
          .call(document.querySelectorAll('input[name="f_' + f.key + '_id"]:checked'))
          .map(function (cb) {
            return cb.value;
          });
        out[f.key] = { mode: mode, ids: ids };
      } else if (f.kind === 'capsule_layout') {
        var r = document.querySelector('input[name="tr_capsule_layout"]:checked');
        out[f.key] = { value: r ? r.value : 'flat' };
      } else if (f.kind === 'radio_choice') {
        var iname2 = f.input_name || 'tr_radio_' + f.key;
        var r2 = document.querySelector('input[name="' + iname2 + '"]:checked');
        var defv =
          f.options && f.options[0] && f.options[0].value != null ? String(f.options[0].value) : '';
        out[f.key] = { value: r2 ? r2.value : defv };
      } else if (f.kind === 'date_range') {
        var df = document.getElementById('tr_dr_' + f.key + '_from');
        var dt = document.getElementById('tr_dr_' + f.key + '_to');
        out[f.key] = {
          from: df && df.value ? df.value : '',
          to: dt && dt.value ? dt.value : '',
        };
      } else if (f.kind === 'date_single') {
        var dsel = document.getElementById('tr_ds_' + f.key);
        out[f.key] = dsel && dsel.value ? dsel.value : '';
      } else if (f.kind === 'text_input') {
        var tin = document.getElementById('tr_txt_' + f.key);
        out[f.key] = tin && tin.value ? tin.value.trim() : '';
      } else if (f.kind === 'inward_grn_select') {
        var si = document.getElementById('tr_sel_' + f.key);
        out[f.key] = si && si.value ? si.value.trim() : '';
      }
    });
    return out;
  }

  function inwardGrnFilterReady(cfg) {
    if (!cfg || !cfg.preview_requires_inward) return true;
    var key = cfg.inward_filter_key || 'inward_grn';
    var sel = document.getElementById('tr_sel_' + key);
    return !!(sel && sel.value && String(sel.value).trim());
  }

  function setGrnReceiptPageLayout(isGrn) {
    var root = getRoot();
    if (!root) return;
    var ph = document.getElementById('trPrintHeader');
    if (isGrn) {
      root.classList.add('tr-page--grn-receipt');
      if (ph) ph.hidden = true;
    } else {
      root.classList.remove('tr-page--grn-receipt');
      if (ph) ph.hidden = false;
    }
  }

  function showGrnPlaceholder() {
    var wrap = document.getElementById('trPreviewWrap');
    if (wrap) {
      wrap.innerHTML =
        '<div class="tr-grn-placeholder">Select a GRN from the list. The receipt appears here after you choose one.</div>';
    }
    var pag = document.getElementById('trPagination');
    if (pag) pag.hidden = true;
  }

  function readGroupBy(cfg) {
    var el = document.getElementById('trGroupBy');
    if (el) return el.value;
    return cfg.default_group_by || 'none';
  }

  /** Paged by group (spec / customer block) instead of flat rows */
  function useGroupPaging(cfg) {
    if (!cfg) return false;
    if (cfg.use_group_paging) {
      return true;
    }
    if (cfg.slug === 'bom_master') {
      var rb = document.querySelector('input[name="tr_bom_row_mode"]:checked');
      if (rb && rb.value === 'spec_wise_items') return true;
    }
    if (cfg.slug === 'customer_master') {
      var rc = document.querySelector('input[name="tr_customer_view"]:checked');
      if (rc && rc.value === 'customer_products') return true;
    }
    if (cfg.slug === 'product_master') {
      var g = readGroupBy(cfg);
      if (g && g !== 'none') return true;
    }
    if (cfg.slug === 'log_sheet_register') {
      var lg = readGroupBy(cfg);
      if (lg === 'customer') return true;
    }
    return false;
  }

  function buildPayload(includePaging) {
    var cfg = state.config;
    if (!cfg) return null;
    var slug = getSlug();
    var payload = {
      report: slug,
      filters: readFilters(cfg),
      group_by: readGroupBy(cfg),
      columns: selectedColumns(cfg),
      search: '',
      sort: resolveDefaultSort(cfg),
    };
    if (includePaging) {
      if (useGroupPaging(cfg)) {
        payload.group_page = state.groupPage;
        payload.group_per_page = state.groupPerPage;
      } else {
        payload.page = state.flatPage;
        payload.per_page = state.flatPerPage;
      }
    }
    return payload;
  }

  function postJson(url, body) {
    return fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken(),
      },
      body: JSON.stringify(body),
    });
  }

  /** Parse JSON from a fetch Response (never call r.json() on HTML login/error pages). */
  function readJsonBody(r) {
    return r.text().then(function (text) {
      var trimmed = (text || '').trim();
      try {
        return { ok: r.ok, j: JSON.parse(trimmed) };
      } catch (parseErr) {
        if (
          trimmed.indexOf('<!DOCTYPE') === 0 ||
          trimmed.indexOf('<!doctype') === 0 ||
          trimmed.indexOf('<html') === 0
        ) {
          throw new Error(
            'The server returned a web page instead of JSON (often login or access denied). ' +
              'Refresh the page or sign in again (HTTP ' +
              r.status +
              ').'
          );
        }
        throw new Error('Could not read JSON from the server (HTTP ' + r.status + ').');
      }
    });
  }

  function mergeProductNameColumns(colDefs) {
    var keys = colDefs.map(function (c) {
      return c.key;
    });
    var i = keys.indexOf('prod_name');
    if (i >= 0 && keys.indexOf('generic_name') === i + 1) {
      var copy = colDefs.slice();
      copy.splice(i, 2, { key: '__prod_combined', label: 'Product name' });
      return copy;
    }
    return colDefs;
  }

  function cellHtml(row, key) {
    if (key === '__prod_combined') {
      var g = row.generic_name ? '(' + escapeHtml(row.generic_name) + ')' : '';
      return (
        '<div class="prod-name-cell"><div class="p1">' +
        escapeHtml(row.prod_name || '') +
        '</div>' +
        (g ? '<div class="p2">' + g + '</div>' : '') +
        '</div>'
      );
    }
    return escapeHtml(row[key] != null ? row[key] : '');
  }

  function colgroupTwoColHtml() {
    return '<colgroup><col class="tr-col-sr"><col class="tr-col-val"></colgroup>';
  }

  /** Sr. No. column + N−1 flexible columns (grouped BOM / customer products, wide header tables). */
  function colgroupSrRestHtml(nCols) {
    if (nCols >= 3) {
      return (
        '<colgroup><col class="tr-col-sr"><col class="tr-col-rest" span="' +
        (nCols - 1) +
        '"></colgroup>'
      );
    }
    if (nCols === 2) {
      return colgroupTwoColHtml();
    }
    return '';
  }

  function renderTable(colDefs, rows) {
    var defs = mergeProductNameColumns(colDefs);
    var th = defs
      .map(function (c) {
        return '<th>' + escapeHtml(c.label) + '</th>';
      })
      .join('');
    var body = rows
      .map(function (row) {
        var tds = defs
          .map(function (c) {
            return '<td>' + cellHtml(row, c.key) + '</td>';
          })
          .join('');
        return '<tr>' + tds + '</tr>';
      })
      .join('');
    var cg = colgroupSrRestHtml(defs.length);
    return (
      '<table class="tr-table" data-col-count="' +
      defs.length +
      '">' +
      cg +
      '<thead><tr>' +
      th +
      '</tr></thead><tbody>' +
      body +
      '</tbody></table>'
    );
  }

  function renderGrouped(colDefs, groups) {
    var defs = mergeProductNameColumns(colDefs);
    var html = '<div class="tr-grouped-stack">';
    (groups || []).forEach(function (g) {
      html += '<div class="tr-table-slot"><table class="tr-table" data-col-count="' + defs.length + '">';
      html += colgroupSrRestHtml(defs.length);
      html += '<thead><tr><th class="tr-group-header" colspan="' + defs.length + '">';
      html += escapeHtml(g.header || '');
      html += '</th></tr><tr>';
      defs.forEach(function (c) {
        html += '<th>' + escapeHtml(c.label) + '</th>';
      });
      html += '</tr></thead><tbody>';
      (g.rows || []).forEach(function (row) {
        html += '<tr>';
        defs.forEach(function (c) {
          html += '<td>' + cellHtml(row, c.key) + '</td>';
        });
        html += '</tr>';
      });
      html += '</tbody></table></div>';
    });
    html += '</div>';
    return html;
  }

  /** DPR: one table — column headers, then per (section+machine) a banner row, details, total. */
  function renderDprSections(colDefs, groups) {
    var defs = mergeProductNameColumns(colDefs);
    var cg = colgroupSrRestHtml(defs.length);
    var th = defs
      .map(function (c) {
        return '<th>' + escapeHtml(c.label) + '</th>';
      })
      .join('');
    var body = '';
    (groups || []).forEach(function (g) {
      body += '<tr class="tr-dpr-group-banner">';
      defs.forEach(function (c) {
        var v = '';
        if (c.key === 'section') v = g.section_machine || '';
        else if (c.key === 'product_name') v = g.banner_shift || '';
        body += '<td class="tr-dpr-banner-cell">' + escapeHtml(v) + '</td>';
      });
      body += '</tr>';
      (g.rows || []).forEach(function (row) {
        body += '<tr>';
        defs.forEach(function (c) {
          body += '<td>' + cellHtml(row, c.key) + '</td>';
        });
        body += '</tr>';
      });
      if (g.footer) {
        body += '<tr class="tr-dpr-total-row">';
        defs.forEach(function (c) {
          body += '<td>' + cellHtml(g.footer, c.key) + '</td>';
        });
        body += '</tr>';
      }
    });
    return (
      '<table class="tr-table" data-col-count="' +
      defs.length +
      '">' +
      cg +
      '<thead><tr>' +
      th +
      '</tr></thead><tbody>' +
      body +
      '</tbody></table>'
    );
  }

  function renderGrnReceipt(r) {
    if (!r) return '<div class="tr-grn-placeholder">No receipt data.</div>';
    var lines = r.lines || [];
    var lb = r.left_block || {};
    var rb = r.right_block || {};
    var ft = r.footer || {};
    var addrLines = r.address_lines || [];
    var idate = rb.inward_date || '';
    var h =
      '<div class="grn-receipt-doc">' +
      '<header class="grn-receipt-head-outer">' +
      '<div class="grn-co-name">' +
      escapeHtml(r.company_name || '') +
      '</div>';
    addrLines.forEach(function (ln) {
      h += '<div class="grn-co-addr">' + escapeHtml(ln) + '</div>';
    });
    h +=
      '<div class="grn-doc-title">' +
      escapeHtml(r.document_title || 'Goods Receipt Note') +
      '</div>' +
      '<div class="grn-head-rule" aria-hidden="true"></div>' +
      '</header>' +
      '<div class="grn-receipt-main">' +
      '<div class="grn-meta-grid">' +
      '<div class="grn-meta-col grn-meta-left">' +
      '<div class="grn-meta-row grn-meta-single"><span class="grn-k">On A/C of :</span> <span class="grn-v">' +
      escapeHtml(r.on_account_of || '') +
      '</span></div>' +
      '<div class="grn-meta-row grn-meta-single"><span class="grn-k">M/s</span> <span class="grn-v">' +
      escapeHtml(r.supplier_name || '') +
      '</span></div>' +
      '<div class="grn-meta-row grn-block"><span class="grn-k">Address</span><div class="grn-v">' +
      escapeHtml(r.supplier_address || '') +
      '</div></div>' +
      '<div class="grn-meta-row grn-meta-single"><span class="grn-k">GSTIN :</span> <span class="grn-v">' +
      escapeHtml(r.supplier_gstin || '') +
      '</span></div>' +
      '<div class="grn-meta-row grn-meta-single"><span class="grn-k">Transporter :</span> <span class="grn-v">' +
      escapeHtml(lb.transporter || '') +
      '</span></div>' +
      '<div class="grn-meta-row grn-meta-single"><span class="grn-k">:</span> <span class="grn-v">' +
      escapeHtml(lb.vehicle_no || '') +
      '</span></div>' +
      '<div class="grn-meta-row grn-meta-pair-row">' +
      '<span class="grn-k">LR. No. :</span>' +
      '<span class="grn-v grn-meta-fill">' +
      escapeHtml(lb.lr_no || '') +
      '</span>' +
      '<span class="grn-k grn-date-k">Date :</span>' +
      '<span class="grn-v grn-date-v">' +
      escapeHtml(lb.lr_date || '') +
      '</span></div>' +
      '</div>' +
      '<div class="grn-meta-col grn-meta-right">' +
      '<div class="grn-meta-row grn-meta-single"><span class="grn-k">Type :</span> <span class="grn-v">' +
      escapeHtml(rb.grn_type || '') +
      '</span></div>' +
      '<div class="grn-meta-row grn-meta-pair-row">' +
      '<span class="grn-k">GRN No. :</span>' +
      '<span class="grn-v grn-meta-fill">' +
      escapeHtml(rb.grn_no || '') +
      '</span>' +
      '<span class="grn-k grn-date-k">Date :</span>' +
      '<span class="grn-v grn-date-v">' +
      escapeHtml(idate) +
      '</span></div>' +
      '<div class="grn-meta-row grn-meta-single"><span class="grn-k">Format No. :</span> <span class="grn-v">' +
      escapeHtml(rb.format_no || '') +
      '</span></div>' +
      '<div class="grn-meta-row grn-meta-pair-row">' +
      '<span class="grn-k">PO/Ref No. :</span>' +
      '<span class="grn-v grn-meta-fill">' +
      escapeHtml(rb.po_ref || '') +
      '</span>' +
      '<span class="grn-k grn-date-k">Date :</span>' +
      '<span class="grn-v grn-date-v">' +
      escapeHtml(rb.po_date || '') +
      '</span></div>' +
      '<div class="grn-meta-row grn-meta-pair-row">' +
      '<span class="grn-k">Invoice No. :</span>' +
      '<span class="grn-v grn-meta-fill">' +
      escapeHtml(rb.invoice_no || '') +
      '</span>' +
      '<span class="grn-k grn-date-k">Date :</span>' +
      '<span class="grn-v grn-date-v">' +
      escapeHtml(rb.invoice_date || '') +
      '</span></div>' +
      '<div class="grn-meta-row grn-meta-pair-row">' +
      '<span class="grn-k">Challan No. :</span>' +
      '<span class="grn-v grn-meta-fill">' +
      escapeHtml(rb.challan_no || '') +
      '</span>' +
      '<span class="grn-k grn-date-k">Date :</span>' +
      '<span class="grn-v grn-date-v">' +
      escapeHtml(rb.challan_date || '') +
      '</span></div>' +
      '<div class="grn-meta-row grn-meta-pair-row">' +
      '<span class="grn-k">Inward No. :</span>' +
      '<span class="grn-v grn-meta-fill">' +
      escapeHtml(rb.register_no || '') +
      '</span>' +
      '<span class="grn-k grn-date-k">Date :</span>' +
      '<span class="grn-v grn-date-v">' +
      escapeHtml(idate) +
      '</span></div>' +
      '</div></div>' +
      '<table class="grn-receipt-table">' +
      '<thead>' +
      '<tr>' +
      '<th><span class="grn-th-stacked">Material Code<br>HSN/SAC Code</span></th>' +
      '<th><span class="grn-th-stacked">Description<br>Manufacturer</span></th>' +
      '<th><span class="grn-th-stacked">Batch</span></th>' +
      '<th><span class="grn-th-stacked">Mfg. Dt.<br>Exp. Dt.<br>Reval Dt.</span></th>' +
      '<th><span class="grn-th-stacked">Control No.<br>AR No.<br>Storage Location</span></th>' +
      '<th>Qty/Pack</th>' +
      '<th colspan="3"><span class="grn-th-stacked">Challan Qty.<br>Rec. Qty.<br>Rej. Qty.</span></th>' +
      '<th colspan="2"><span class="grn-th-stacked">Acc. Qty.<br>Smp. Qty.</span></th>' +
      '<th><span class="grn-th-stacked">Rate<br>Amount</span></th>' +
      '<th>Tax</th>' +
      '<th>Tax %</th>' +
      '<th>Amount</th>' +
      '</tr></thead><tbody>';
    lines.forEach(function (row) {
      h += '<tr>';
      h +=
        '<td class="grn-td-stack"><span class="grn-muted">' +
        escapeHtml(row.material_code || '') +
        '</span>' +
        (row.hsn_code
          ? '<br><span>' + escapeHtml(row.hsn_code) + '</span>'
          : '') +
        '</td>';
      h +=
        '<td class="grn-td-stack"><span>' +
        escapeHtml(row.description || '') +
        '</span>' +
        (row.manufacturer
          ? '<br><span class="grn-muted">' + escapeHtml(row.manufacturer) + '</span>'
          : '') +
        '</td>';
      h += '<td class="grn-td-batch">' + escapeHtml(row.batch_no || '') + '</td>';
      h +=
        '<td class="grn-td-stack"><span>' +
        escapeHtml(row.mfg_exp || '') +
        '</span>' +
        (row.reval_dt
          ? '<br><span>' + escapeHtml(row.reval_dt) + '</span>'
          : '') +
        '</td>';
      h +=
        '<td class="grn-td-stack"><span>' +
        escapeHtml(row.control_no || '') +
        '</span><br><span>' +
        escapeHtml(row.ar_no || '') +
        '</span><br><span>' +
        escapeHtml(row.storage || '') +
        '</span></td>';
      h += '<td>' + escapeHtml(row.qty_pack || '') + '</td>';
      h += '<td>' + escapeHtml(row.challan_qty || '') + '</td>';
      h += '<td>' + escapeHtml(row.rec_qty || '') + '</td>';
      h += '<td>' + escapeHtml(row.rej_qty || '') + '</td>';
      h += '<td>' + escapeHtml(row.acc_qty || '') + '</td>';
      h += '<td>' + escapeHtml(row.smp_qty || '') + '</td>';
      h +=
        '<td class="grn-td-stack"><span>' +
        escapeHtml(row.rate || '') +
        '</span><br><span>' +
        escapeHtml(row.amount || '') +
        '</span></td>';
      h += '<td>' + escapeHtml(row.tax || '') + '</td>';
      h += '<td>' + escapeHtml(row.tax_pct || '') + '</td>';
      h += '<td>' + escapeHtml(row.amount_tax || '') + '</td>';
      h += '</tr>';
    });
    h += '</tbody></table>';
    h +=
      '<div class="grn-totals-strip">' +
      '<div class="grn-totals-left">' +
      '<div class="grn-exemption">Exemption Category : ' +
      escapeHtml(ft.exemption || '') +
      '</div></div>' +
      '<div class="grn-totals-right">' +
      '<div><span class="grn-k">Sub Total :</span> <span class="grn-v">' +
      escapeHtml(ft.sub_total || '') +
      '</span></div>' +
      '<div><span class="grn-k">GST Total Amount :</span> <span class="grn-v">' +
      escapeHtml(ft.gst_total || '') +
      '</span></div>' +
      '<div><span class="grn-k">TCS U/s 206C(1H) :</span> <span class="grn-v">' +
      escapeHtml(ft.tcs || '') +
      '</span></div>' +
      '<div><span class="grn-k">Net Amount :</span> <span class="grn-v">' +
      escapeHtml(ft.net_amount || '') +
      '</span></div>' +
      '</div></div>' +
      '</div>' +
      '<div class="grn-receipt-signatures">' +
      '<div class="grn-sign-top">' +
      '<span class="grn-prepared-by">Prepared By :</span>' +
      '<span class="grn-complies">Complies / Rejected</span>' +
      '</div>' +
      '<div class="grn-sign-bottom">' +
      '<span>Store</span><span>Approved By</span><span>Authorised By</span>' +
      '</div>' +
      '</div>' +
      '</div>';
    return h;
  }

  function renderMultiTable(data) {
    var html = '<div class="tr-multi-grid">';
    (data.sections || []).forEach(function (sec) {
      html += '<div class="tr-mini-table-wrap">';
      html += '<h4>' + escapeHtml(sec.title || '') + '</h4>';
      if (sec.layout === 'grouped') {
        html += renderGrouped(sec.column_defs || [], sec.groups || []);
      } else {
        html += renderTable(sec.column_defs || [], sec.rows || []);
      }
      html += '</div>';
    });
    html += '</div>';
    return html;
  }

  function renderPagination(data) {
    var host = document.getElementById('trPagination');
    if (!host) return;
    if (data.layout === 'multi_table') {
      host.hidden = true;
      return;
    }
    if (data.layout === 'dpr_sections') {
      host.hidden = true;
      return;
    }
    if (data.layout === 'grn_receipt') {
      host.hidden = true;
      return;
    }
    if (data.layout === 'grouped') {
      host.hidden = false;
      var tp = data.total_group_pages || 1;
      var gp = data.group_page || 1;
      host.innerHTML =
        '<span>Groups: page ' +
        gp +
        ' / ' +
        tp +
        '</span>' +
        '<button type="button" class="tr-btn" data-gp="prev">Prev</button>' +
        '<button type="button" class="tr-btn" data-gp="next">Next</button>';
      host.querySelector('[data-gp="prev"]').disabled = gp <= 1;
      host.querySelector('[data-gp="next"]').disabled = gp >= tp;
      host.onclick = function (e) {
        var t = e.target;
        if (t.getAttribute('data-gp') === 'prev' && gp > 1) {
          state.groupPage = gp - 1;
          runPreview();
        }
        if (t.getAttribute('data-gp') === 'next' && gp < tp) {
          state.groupPage = gp + 1;
          runPreview();
        }
      };
      return;
    }
    host.hidden = false;
    var pages = data.total_pages || 1;
    var p = data.page || 1;
    host.innerHTML =
      '<span>Rows: ' +
      (data.total_count || 0) +
      ' — page ' +
      p +
      ' / ' +
      pages +
      '</span>' +
      '<button type="button" class="tr-btn" data-p="prev">Prev</button>' +
      '<button type="button" class="tr-btn" data-p="next">Next</button>';
    host.querySelector('[data-p="prev"]').disabled = p <= 1;
    host.querySelector('[data-p="next"]').disabled = p >= pages;
    host.onclick = function (e) {
      var t = e.target;
      if (t.getAttribute('data-p') === 'prev' && p > 1) {
        state.flatPage = p - 1;
        runPreview();
      }
      if (t.getAttribute('data-p') === 'next' && p < pages) {
        state.flatPage = p + 1;
        runPreview();
      }
    };
  }

  function schedulePreview() {
    if (previewTimer) clearTimeout(previewTimer);
    previewTimer = setTimeout(function () {
      previewTimer = null;
      state.flatPage = 1;
      state.groupPage = 1;
      if (state.config && state.config.preview_requires_inward && !inwardGrnFilterReady(state.config)) {
        setLoading(false);
        showError('');
        setGrnReceiptPageLayout(state.config.slug === 'inward_grn_receipt');
        showGrnPlaceholder();
        return;
      }
      runPreview();
    }, previewDebounceMs);
  }

  function runPreview() {
    var urls = apiUrls();
    if (state.config && state.config.preview_requires_inward && !inwardGrnFilterReady(state.config)) {
      setLoading(false);
      showError('');
      setGrnReceiptPageLayout(state.config.slug === 'inward_grn_receipt');
      showGrnPlaceholder();
      return;
    }
    var payload = buildPayload(true);
    if (!payload) return;
    var seq = ++previewSeq;
    showError('');
    setLoading(true);
    postJson(urls.data, payload)
      .then(readJsonBody)
      .then(function (x) {
        if (seq !== previewSeq) return;
        setLoading(false);
        if (!x.ok) {
          showError((x.j && x.j.error) || 'Request failed.');
          return;
        }
        state.lastResult = x.j;
        setMeta(x.j);
        var wrap = document.getElementById('trPreviewWrap');
        var title = document.getElementById('trPrintTitle');
        if (title && state.config) {
          title.textContent = state.config.print_title || state.config.label || '';
        }
        var sub = document.getElementById('trPrintSubtitle');
        if (sub) {
          var st = x.j.meta && x.j.meta.report_subtitle ? String(x.j.meta.report_subtitle) : '';
          sub.textContent = st;
          sub.hidden = !st || x.j.layout === 'grn_receipt';
        }
        if (!wrap) return;
        if (x.j.layout === 'grn_receipt') {
          setGrnReceiptPageLayout(true);
          wrap.innerHTML = renderGrnReceipt(x.j.receipt);
        } else {
          setGrnReceiptPageLayout(false);
          if (x.j.layout === 'multi_table') {
            wrap.innerHTML = renderMultiTable(x.j);
          } else if (x.j.layout === 'dpr_sections') {
            wrap.innerHTML = renderDprSections(x.j.columns || [], x.j.groups || []);
          } else if (x.j.layout === 'grouped') {
            wrap.innerHTML = renderGrouped(x.j.columns || [], x.j.groups || []);
          } else {
            wrap.innerHTML = renderTable(x.j.columns || [], x.j.rows || []);
          }
        }
        renderPagination(x.j);
      })
      .catch(function (e) {
        if (seq !== previewSeq) return;
        setLoading(false);
        showError(e.message || 'Network error.');
      });
  }

  function runExportExcel() {
    var urls = apiUrls();
    var payload = buildPayload(false);
    if (!payload) return;
    var cfg = state.config;
    if (cfg && useGroupPaging(cfg)) {
      payload.group_page = 1;
      payload.group_per_page = 10000;
    }
    payload.export = true;
    postJson(urls.excel, payload)
      .then(function (r) {
        var ct = (r.headers.get('Content-Type') || '').toLowerCase();
        var isFile =
          r.ok &&
          (ct.indexOf('spreadsheetml') !== -1 ||
            ct.indexOf('officedocument') !== -1 ||
            ct.indexOf('octet-stream') !== -1);
        if (isFile) {
          return r.blob().then(function (blob) {
            return { blob: blob, cd: r.headers.get('Content-Disposition') };
          });
        }
        return readJsonBody(r).then(function (x) {
          throw new Error((x.j && x.j.error) || 'Export failed (HTTP ' + r.status + ').');
        });
      })
      .then(function (x) {
        var fname = 'export';
        var m = /filename="?([^";]+)"?/i.exec(x.cd || '');
        if (m) fname = m[1];
        var a = document.createElement('a');
        a.href = URL.createObjectURL(x.blob);
        a.download = fname;
        a.click();
        URL.revokeObjectURL(a.href);
      })
      .catch(function (e) {
        showError(e.message || 'Export failed.');
      });
  }

  function loadConfig() {
    var url = getConfigUrl();
    if (!url) return;
    showError('');
    setLoading(true);
    fetch(url, { credentials: 'same-origin' })
      .then(readJsonBody)
      .then(function (x) {
        setLoading(false);
        if (!x.ok) {
          showError((x.j && x.j.error) || 'Could not load report configuration.');
          return;
        }
        var cfg = x.j;
        state.config = cfg;
        state.slug = cfg.slug;
        state.flatPage = 1;
        state.groupPage = 1;
        var desc = document.getElementById('trReportDescription');
        if (desc) desc.textContent = cfg.description || '';
        var btnEx = document.getElementById('trBtnExcel');
        if (btnEx) btnEx.hidden = !!cfg.hide_excel;
        renderFilters(cfg);
        renderColumns(cfg);
        var ph = document.getElementById('trPrintTitle');
        if (ph) ph.textContent = cfg.print_title || cfg.label || '';
        var subEl = document.getElementById('trPrintSubtitle');
        if (subEl) {
          subEl.textContent = '';
          subEl.hidden = true;
        }
        setGrnReceiptPageLayout(cfg.slug === 'inward_grn_receipt');
        if (cfg.slug === 'inward_grn_receipt') {
          showGrnPlaceholder();
        }
        schedulePreview();
      })
      .catch(function (e) {
        setLoading(false);
        showError(e.message || 'Could not load report configuration.');
      });
  }

  function initPage_transaction_reports() {
    var root = getRoot();
    if (!root) return;
    if (root.dataset.trWired === '1') return;
    root.dataset.trWired = '1';

    var sel = document.getElementById('trReportSelect');
    if (sel) {
      sel.addEventListener('change', function () {
        state.optionsCache = {};
        loadConfig();
      });
    }

    var filterPanel = document.getElementById('trFilterPanel');
    function onFilterPanelInteraction(ev) {
      var t = ev.target;
      if (
        state.config &&
        t &&
        t.matches &&
        (t.matches('input[name="tr_customer_view"]') ||
          t.matches('input[name="tr_bom_row_mode"]'))
      ) {
        renderColumns(state.config);
      }
      schedulePreview();
    }
    if (filterPanel) {
      filterPanel.addEventListener('change', onFilterPanelInteraction);
      filterPanel.addEventListener('input', onFilterPanelInteraction);
    }

    var btnP = document.getElementById('trBtnPreview');
    if (btnP) {
      btnP.addEventListener('click', function () {
        if (previewTimer) clearTimeout(previewTimer);
        previewTimer = null;
        state.flatPage = 1;
        state.groupPage = 1;
        runPreview();
      });
    }
    var btnE = document.getElementById('trBtnExcel');
    if (btnE) btnE.addEventListener('click', function () { runExportExcel(); });
    var btnPr = document.getElementById('trBtnPrint');
    if (btnPr) btnPr.addEventListener('click', function () { window.print(); });

    wirePrintDocumentTitleOnce();

    loadConfig();
  }

  window.initPage_transaction_reports = initPage_transaction_reports;
})();
