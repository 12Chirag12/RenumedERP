/**
 * Shared document serial input helpers (inward register / GRN, sales invoice SI-, etc.).
 * Mirrors Python transactions.numbering.format_serial_suffix padding rules.
 */
(function (global) {
  'use strict';

  var PAD_THRESHOLD = 100000;

  function formatSerialSuffix(n) {
    var v = parseInt(n, 10);
    if (isNaN(v) || v < 1) return '';
    if (v < PAD_THRESHOLD) return String(v).padStart(5, '0');
    return String(v);
  }

  function normalizeNumericSuffixInput(inputEl, prefix) {
    if (!inputEl) return;
    var raw = String(inputEl.value || '').toUpperCase();
    var p = String(prefix || '').toUpperCase();
    if (p && raw.indexOf(p) !== 0) {
      var digitsOnly = raw.replace(/\D+/g, '');
      raw = p + digitsOnly;
    }
    var suffix = raw.slice(p.length).replace(/\D+/g, '');
    inputEl.value = p + suffix;
  }

  function isDigitKey(e) {
    var k = e.key;
    if (k >= '0' && k <= '9') return true;
    if (k === 'Backspace' || k === 'Delete' || k === 'Tab' || k === 'Enter') return true;
    if (k === 'ArrowLeft' || k === 'ArrowRight' || k === 'Home' || k === 'End') return true;
    if (e.ctrlKey || e.metaKey) return true;
    return false;
  }

  /**
   * Lock fixed prefix (e.g. R-, SI-, RM-); user may edit digits after prefix only.
   * getPrefixFn can return '' to skip enforcement until a prefix is known (e.g. GRN type).
   */
  function lockPrefixAndDigitsOnly(inputEl, getPrefixFn) {
    if (!inputEl) return;
    function getPrefix() {
      return String(getPrefixFn ? getPrefixFn() : '').toUpperCase();
    }

    function ensurePrefixPresent(placeCaretAtEnd) {
      var prefix = getPrefix();
      if (!prefix) return;
      var v = String(inputEl.value || '').toUpperCase();
      if (v.indexOf(prefix) !== 0) {
        inputEl.value = prefix + v.replace(/\D+/g, '');
      }
      if (placeCaretAtEnd) {
        try {
          inputEl.setSelectionRange(inputEl.value.length, inputEl.value.length);
        } catch (e) { /* ignore */ }
      }
    }

    inputEl.addEventListener('focus', function () { ensurePrefixPresent(false); });

    inputEl.addEventListener('keydown', function (e) {
      var prefix = getPrefix();
      var pos = typeof inputEl.selectionStart === 'number' ? inputEl.selectionStart : 0;
      var selEnd = typeof inputEl.selectionEnd === 'number' ? inputEl.selectionEnd : pos;

      if (prefix && pos <= prefix.length && !(e.key === 'Backspace' || e.key === 'Delete')) {
        if (!isDigitKey(e)) {
          e.preventDefault();
          return;
        }
        if (e.key >= '0' && e.key <= '9') {
          e.preventDefault();
          ensurePrefixPresent(false);
          var cur = String(inputEl.value || '').toUpperCase();
          var suffix = cur.indexOf(prefix) === 0 ? cur.slice(prefix.length) : cur.replace(/\D+/g, '');
          if (pos === 0 && selEnd === cur.length) suffix = '';
          inputEl.value = prefix + suffix + e.key;
          try { inputEl.setSelectionRange(inputEl.value.length, inputEl.value.length); } catch (ex) {}
          return;
        }
      }

      if (!isDigitKey(e)) {
        e.preventDefault();
      }
    });

    inputEl.addEventListener('input', function () {
      var prefix = getPrefix();
      normalizeNumericSuffixInput(inputEl, prefix);
    });

    inputEl.addEventListener('paste', function () {
      setTimeout(function () {
        var prefix = getPrefix();
        normalizeNumericSuffixInput(inputEl, prefix);
      }, 0);
    });
  }

  global.prefixedSerialNoFormatSuffix = formatSerialSuffix;
  global.prefixedSerialNoNormalize = normalizeNumericSuffixInput;
  global.prefixedSerialNoBindLock = lockPrefixAndDigitsOnly;
})(typeof window !== 'undefined' ? window : this);
