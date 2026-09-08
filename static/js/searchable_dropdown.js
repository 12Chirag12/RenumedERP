/**
 * Select2 init for <select class="... searchable-dropdown">.
 * Case-insensitive substring match via String.prototype.includes().
 * Destroy before re-init (HTMX swaps, dynamic rows, option rebuilds).
 */
(function (global) {
  if (!global.jQuery) return;

  var $ = global.jQuery;
  if (!$.fn || typeof $.fn.select2 !== 'function') {
    if (global.console && typeof global.console.warn === 'function') {
      global.console.warn('Searchable dropdowns: Select2 not loaded (jquery.fn.select2 missing).');
    }
    return;
  }

  function matchContains(params, data) {
    var term = (params.term || '').trim();
    if (!term) {
      return data;
    }
    if (data.children && data.children.length) {
      var matched = [];
      for (var i = 0; i < data.children.length; i++) {
        var child = data.children[i];
        var m = matchContains(params, child);
        if (m) matched.push(m);
      }
      if (matched.length) {
        var copy = $.extend({}, data);
        copy.children = matched;
        return copy;
      }
      return null;
    }
    var text = data.text == null ? '' : String(data.text);
    var t = term.toLowerCase();
    if (text.toLowerCase().includes(t)) {
      return data;
    }
    return null;
  }

  function destroyIn(root) {
    if (!root) {
      destroyIn(document);
      return;
    }
    function one($el) {
      if ($el.hasClass('select2-hidden-accessible')) {
        try {
          $el.select2('destroy');
        } catch (e) { /* ignore */ }
      }
    }
    if (root.nodeType === 1 && root.tagName === 'SELECT' &&
        root.classList && root.classList.contains('searchable-dropdown')) {
      one($(root));
      return;
    }
    $(root).find('select.searchable-dropdown').each(function () {
      one($(this));
    });
  }

  function bindOne($el) {
    if ($el.hasClass('select2-hidden-accessible')) {
      try {
        $el.select2('destroy');
      } catch (e) { /* ignore */ }
    }
    $el.select2({
      width: '100%',
      dropdownParent: $(document.body),
      matcher: matchContains,
    });

    // Bridge Select2's jQuery events to native DOM change events.
    // Many pages bind using addEventListener('change', ...); Select2 emits jQuery
    // change/select events that do not reach native listeners consistently.
    $el.off('.cuNativeChangeBridge');
    $el.on('select2:select.cuNativeChangeBridge select2:unselect.cuNativeChangeBridge select2:clear.cuNativeChangeBridge', function () {
      try {
        this.dispatchEvent(new Event('change', { bubbles: true }));
      } catch (e) { /* ignore */ }
    });
  }

  function initIn(root) {
    if (!root) {
      initIn(document);
      return;
    }
    if (root.nodeType === 1 && root.tagName === 'SELECT' &&
        root.classList && root.classList.contains('searchable-dropdown')) {
      bindOne($(root));
      return;
    }
    $(root).find('select.searchable-dropdown').each(function () {
      bindOne($(this));
    });
  }

  global.destroySearchableDropdownsIn = destroyIn;
  global.initSearchableDropdowns = initIn;
})(typeof window !== 'undefined' ? window : this);
