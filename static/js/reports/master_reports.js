/**
 * Master Reports — single page, config-driven preview and exports.
 * Exposes window.initPage_master_reports for HTMX partial loads.
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
    var pt = document.getElementById('mrPrintTitle');
    var label = pt && pt.textContent ? pt.textContent.trim() : '';
    if (!label) {
      var rs = document.getElementById('mrReportSelect');
      if (rs && rs.selectedOptions[0]) label = rs.selectedOptions[0].textContent.trim();
    }
    if (label) return label.slice(0, 120);
    var root = document.getElementById('masterReportsRoot');
    if (root) {
      var ch = root.getAttribute('data-company-header');
      if (ch && ch.trim()) return ch.trim().slice(0, 120);
    }
    return 'Report';
  }

  function wirePrintDocumentTitleOnce() {
    if (window.__mrPrintDocTitleHook) return;
    window.__mrPrintDocTitleHook = true;
    window.addEventListener('beforeprint', function () {
      if (!document.getElementById('masterReportsRoot')) return;
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
    return document.getElementById('masterReportsRoot');
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
    var el = document.getElementById('mrError');
    if (!el) return;
    el.textContent = msg || '';
    el.hidden = !msg;
  }

  function setLoading(on) {
    var el = document.getElementById('mrLoading');
    if (el) el.hidden = !on;
  }

  function setMeta(data) {
    var bar = document.getElementById('mrMetaBar');
    var txt = document.getElementById('mrMetaText');
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
    var sel = document.getElementById('mrReportSelect');
    return sel ? sel.value : '';
  }

  function getConfigUrl() {
    var sel = document.getElementById('mrReportSelect');
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
    var host = document.getElementById('mr_opts_' + key);
    if (!host) return;
    host.innerHTML = '';
    options.forEach(function (opt) {
      var id = 'mr_f_' + key + '_' + opt.id;
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
    var scroll = document.getElementById('mr_opts_' + key);
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
    var host = document.getElementById('mrFiltersDynamic');
    if (!host) return;
    host.innerHTML = '';
    state.optionsCache = {};

    (cfg.filters || []).forEach(function (f) {
      if (f.kind === 'all_or_multiselect') {
        var block = document.createElement('div');
        block.className = 'mr-filter-block';
        block.innerHTML =
          '<div class="mr-filter-title">' +
          escapeHtml(f.label) +
          ' :</div>' +
          '<div class="mr-radio-row">' +
          '<label><input type="radio" name="f_' +
          f.key +
          '_mode" value="all" checked> All</label>' +
          '<label><input type="radio" name="f_' +
          f.key +
          '_mode" value="select"> Select</label>' +
          '</div>' +
          (f.list_label ? '<div class="mr-list-label">' + escapeHtml(f.list_label) + '</div>' : '') +
          '<div class="mr-check-scroll" id="mr_opts_' +
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
        b2.className = 'mr-filter-block';
        var opts = f.options || [];
        var radios = opts
          .map(function (o, i) {
            return (
              '<label><input type="radio" name="mr_capsule_layout" value="' +
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
          '<div class="mr-filter-title">' +
          escapeHtml(f.label) +
          ' :</div><div class="mr-radio-row">' +
          radios +
          '</div>';
        host.appendChild(b2);
      } else if (f.kind === 'radio_choice') {
        var b3 = document.createElement('div');
        b3.className = 'mr-filter-block';
        var iname = f.input_name || 'mr_radio_' + f.key;
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
          'mr-radio-row' + (f.radio_layout === 'vertical' ? ' mr-radio-col' : '');
        b3.innerHTML =
          '<div class="mr-filter-title">' +
          escapeHtml(f.label) +
          ' :</div><div class="' +
          rowCls +
          '">' +
          rhtml +
          '</div>';
        host.appendChild(b3);
      }
    });

    if ((cfg.group_by_options || []).length > 1) {
      var gb = document.createElement('div');
      gb.className = 'mr-filter-block';
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
        '<div class="mr-filter-title">Group by</div><select id="mrGroupBy" class="mr-select" style="min-width:100%">' +
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
      var rc = document.querySelector('input[name="mr_customer_view"]:checked');
      if (rc && rc.value === 'customer_products' && cfg.columns_customer_products) {
        return cfg.columns_customer_products;
      }
    }
    if (cfg.slug === 'bom_master') {
      var rb = document.querySelector('input[name="mr_bom_row_mode"]:checked');
      if (rb && rb.value === 'spec_wise_items' && cfg.columns_bom_spec_groups) {
        return cfg.columns_bom_spec_groups;
      }
    }
    return cfg.columns || [];
  }

  function resolveDefaultSort(cfg) {
    if (!cfg) return {};
    if (cfg.slug === 'customer_master') {
      var rc = document.querySelector('input[name="mr_customer_view"]:checked');
      if (rc && rc.value === 'customer_products' && cfg.default_sort_customer_products) {
        return cfg.default_sort_customer_products;
      }
    }
    if (cfg.slug === 'bom_master') {
      var rb = document.querySelector('input[name="mr_bom_row_mode"]:checked');
      if (rb && rb.value === 'spec_wise_items' && cfg.default_sort_bom_spec_groups) {
        return cfg.default_sort_bom_spec_groups;
      }
    }
    return cfg.default_sort || {};
  }

  function renderColumns(cfg) {
    var block = document.getElementById('mrColumnsBlock');
    var host = document.getElementById('mrColumnsHost');
    if (!block || !host) return;
    var cols = getColumnDefs(cfg);
    if (!cols.length) {
      block.hidden = true;
      return;
    }
    block.hidden = false;
    host.innerHTML = '';
    cols.forEach(function (c) {
      var id = 'mr_col_' + c.key;
      var lab = document.createElement('label');
      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.name = 'mr_col';
      cb.value = c.key;
      cb.id = id;
      cb.checked = !!c.default;
      lab.appendChild(cb);
      lab.appendChild(document.createTextNode(' ' + c.label));
      host.appendChild(lab);
    });

    var modes = document.querySelectorAll('input[name="mr_col_mode"]');
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
    var chk = document.querySelector('input[name="mr_col_mode"]:checked');
    if (chk) chk.dispatchEvent(new Event('change'));
  }

  function selectedColumns(cfg) {
    var defs = getColumnDefs(cfg);
    var colMode = document.querySelector('input[name="mr_col_mode"]:checked');
    if (!colMode || colMode.value === 'all') {
      return defs.map(function (c) {
        return c.key;
      });
    }
    return Array.prototype.slice
      .call(document.querySelectorAll('input[name="mr_col"]:checked'))
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
        var r = document.querySelector('input[name="mr_capsule_layout"]:checked');
        out[f.key] = { value: r ? r.value : 'flat' };
      } else if (f.kind === 'radio_choice') {
        var iname2 = f.input_name || 'mr_radio_' + f.key;
        var r2 = document.querySelector('input[name="' + iname2 + '"]:checked');
        var defv =
          f.options && f.options[0] && f.options[0].value != null ? String(f.options[0].value) : '';
        out[f.key] = { value: r2 ? r2.value : defv };
      }
    });
    return out;
  }

  function readGroupBy(cfg) {
    var el = document.getElementById('mrGroupBy');
    if (el) return el.value;
    return cfg.default_group_by || 'none';
  }

  /** Paged by group (spec / customer block) instead of flat rows */
  function useGroupPaging(cfg) {
    if (!cfg) return false;
    if (cfg.slug === 'bom_master') {
      var rb = document.querySelector('input[name="mr_bom_row_mode"]:checked');
      if (rb && rb.value === 'spec_wise_items') return true;
    }
    if (cfg.slug === 'customer_master') {
      var rc = document.querySelector('input[name="mr_customer_view"]:checked');
      if (rc && rc.value === 'customer_products') return true;
    }
    if (cfg.slug === 'product_master') {
      var g = readGroupBy(cfg);
      if (g && g !== 'none') return true;
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
    return '<colgroup><col class="mr-col-sr"><col class="mr-col-val"></colgroup>';
  }

  /** Sr. No. column + N−1 flexible columns (grouped BOM / customer products, wide header tables). */
  function colgroupSrRestHtml(nCols) {
    if (nCols >= 3) {
      return (
        '<colgroup><col class="mr-col-sr"><col class="mr-col-rest" span="' +
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
      '<table class="mr-table" data-col-count="' +
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
    var html = '<div class="mr-grouped-stack">';
    (groups || []).forEach(function (g) {
      html += '<div class="mr-table-slot"><table class="mr-table" data-col-count="' + defs.length + '">';
      html += colgroupSrRestHtml(defs.length);
      html += '<thead><tr><th class="mr-group-header" colspan="' + defs.length + '">';
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

  function renderMultiTable(data) {
    var html = '<div class="mr-multi-grid">';
    (data.sections || []).forEach(function (sec) {
      html += '<div class="mr-mini-table-wrap">';
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
    var host = document.getElementById('mrPagination');
    if (!host) return;
    if (data.layout === 'multi_table') {
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
        '<button type="button" class="mr-btn" data-gp="prev">Prev</button>' +
        '<button type="button" class="mr-btn" data-gp="next">Next</button>';
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
      '<button type="button" class="mr-btn" data-p="prev">Prev</button>' +
      '<button type="button" class="mr-btn" data-p="next">Next</button>';
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
      runPreview();
    }, previewDebounceMs);
  }

  function runPreview() {
    var urls = apiUrls();
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
        var wrap = document.getElementById('mrPreviewWrap');
        var title = document.getElementById('mrPrintTitle');
        if (title && state.config) title.textContent = state.config.label || '';
        if (!wrap) return;
        if (x.j.layout === 'multi_table') {
          wrap.innerHTML = renderMultiTable(x.j);
        } else if (x.j.layout === 'grouped') {
          wrap.innerHTML = renderGrouped(x.j.columns || [], x.j.groups || []);
        } else {
          wrap.innerHTML = renderTable(x.j.columns || [], x.j.rows || []);
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
    if (cfg && (useGroupPaging(cfg) || (state.lastResult && state.lastResult.layout === 'grouped'))) {
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
        var desc = document.getElementById('mrReportDescription');
        if (desc) desc.textContent = cfg.description || '';
        renderFilters(cfg);
        renderColumns(cfg);
        var ph = document.getElementById('mrPrintTitle');
        if (ph) ph.textContent = cfg.label || '';
        schedulePreview();
      })
      .catch(function (e) {
        setLoading(false);
        showError(e.message || 'Could not load report configuration.');
      });
  }

  function initPage_master_reports() {
    var root = getRoot();
    if (!root) return;
    if (root.dataset.mrWired === '1') return;
    root.dataset.mrWired = '1';

    var sel = document.getElementById('mrReportSelect');
    if (sel) {
      sel.addEventListener('change', function () {
        state.optionsCache = {};
        loadConfig();
      });
    }

    var filterPanel = document.getElementById('mrFilterPanel');
    if (filterPanel) {
      filterPanel.addEventListener('change', function (ev) {
        var t = ev.target;
        if (
          state.config &&
          t &&
          t.matches &&
          (t.matches('input[name="mr_customer_view"]') ||
            t.matches('input[name="mr_bom_row_mode"]'))
        ) {
          renderColumns(state.config);
        }
        schedulePreview();
      });
    }

    var btnP = document.getElementById('mrBtnPreview');
    if (btnP) {
      btnP.addEventListener('click', function () {
        if (previewTimer) clearTimeout(previewTimer);
        previewTimer = null;
        state.flatPage = 1;
        state.groupPage = 1;
        runPreview();
      });
    }
    var btnE = document.getElementById('mrBtnExcel');
    if (btnE) btnE.addEventListener('click', function () { runExportExcel(); });
    var btnPr = document.getElementById('mrBtnPrint');
    if (btnPr) btnPr.addEventListener('click', function () { window.print(); });

    wirePrintDocumentTitleOnce();

    loadConfig();
  }

  window.initPage_master_reports = initPage_master_reports;
})();
