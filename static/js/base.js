/**
 * base.js
 * ────────────────────────────────────────────────────────────────────────────
 * Global JS for PharmaERP.
 *
 * What changed from the original:
 *   1. Active-nav highlight is now URL-based (updateActiveNav) instead of
 *      being driven by Django template blocks.  This means it works both on
 *      full page loads AND after every HTMX partial swap.
 *
 *   2. initPageContent() encapsulates everything that must run after the
 *      #mainContent innerHTML is replaced.  It is called:
 *        • on DOMContentLoaded  (full page load)
 *        • from the inline <script> at the bottom of base_partial.html
 *          (after each HTMX swap)
 *
 *   3. htmx:afterSettle listener updates the active nav and open submenu
 *      after every navigation so the sidebar always reflects the current URL.
 * ────────────────────────────────────────────────────────────────────────────
 */

// ════════════════════════════════════════════════════════════════════
// SIDEBAR TOGGLE
// ════════════════════════════════════════════════════════════════════

function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  const main    = document.getElementById('mainContent');
  sidebar.classList.toggle('collapsed');
  main.classList.toggle('collapsed');
  localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
}


// ════════════════════════════════════════════════════════════════════
// ACCORDION MENU
// ════════════════════════════════════════════════════════════════════

function toggleMenu(id) {
  const submenu = document.getElementById('submenu-' + id);
  const parent  = document.getElementById('parent-'  + id);
  const isOpen  = submenu.classList.contains('open');

  // Close all
  document.querySelectorAll('.submenu').forEach(el  => el.classList.remove('open'));
  document.querySelectorAll('.menu-parent').forEach(el => el.classList.remove('open'));

  // Open the clicked one (if it was closed)
  if (!isOpen) {
    submenu.classList.add('open');
    parent.classList.add('open');
    localStorage.setItem('openMenu', id);
  } else {
    localStorage.removeItem('openMenu');
  }
}


// ════════════════════════════════════════════════════════════════════
// ACTIVE NAV — URL-based (replaces Django block nav_* approach)
// ════════════════════════════════════════════════════════════════════

/**
 * updateActiveNav()
 *
 * Marks the sidebar link whose href best matches the current pathname.
 * Also opens the parent submenu that contains the active link.
 *
 * Strategy:
 *   1. Strip query strings — compare only the path portion.
 *   2. Longest-prefix match wins (so /masters/section/ beats /masters/).
 *   3. Exact match for the Dashboard direct-link.
 */
function updateActiveNav() {
  const currentPath = window.location.pathname;

  // Clear existing active state
  document.querySelectorAll('.submenu-item.active, .menu-direct.active')
    .forEach(el => el.classList.remove('active'));

  let bestMatch = null;
  let bestLen   = 0;

  document.querySelectorAll('.submenu-item[href], .menu-direct[href]').forEach(link => {
    const href = link.getAttribute('href');
    if (!href || href === '#') return;

    // Exact or startsWith match; prefer longer matches
    if (currentPath === href || currentPath.startsWith(href)) {
      if (href.length > bestLen) {
        bestLen   = href.length;
        bestMatch = link;
      }
    }
  });

  if (bestMatch) {
    bestMatch.classList.add('active');

    // Open the submenu that contains this link
    const parentSubmenu = bestMatch.closest('.submenu');
    if (parentSubmenu) {
      const menuId = parentSubmenu.id.replace('submenu-', '');
      const sub    = document.getElementById('submenu-' + menuId);
      const par    = document.getElementById('parent-'  + menuId);
      if (sub) sub.classList.add('open');
      if (par) par.classList.add('open');
      localStorage.setItem('openMenu', menuId);
    }
  }
}


// ════════════════════════════════════════════════════════════════════
// REUSABLE DELETE MODAL
// ════════════════════════════════════════════════════════════════════

window.openDeleteModal = function(deleteUrl, itemName) {
  document.getElementById('deleteModalItemName').textContent = itemName;
  var form = document.getElementById('globalDeleteForm');
  // Set hx-post so HTMX sends the delete as a boosted POST to the correct URL.
  // htmx.process() is required so HTMX re-evaluates the changed attribute.
  form.setAttribute('hx-post', deleteUrl);
  if (window.htmx) htmx.process(form);
  document.getElementById('globalDeleteModal').style.display = 'flex';
};

window.closeDeleteModal = function() {
  document.getElementById('globalDeleteModal').style.display = 'none';
};


// ════════════════════════════════════════════════════════════════════
// MASTER FORMS — clear validation UI (server + client) on "Clear"
// ════════════════════════════════════════════════════════════════════

/**
 * Remove Django-rendered field errors, non-field banners, and reset client error state.
 * Keeps persistent placeholders such as .js-err and #prodGridError (customer grid).
 *
 * @param {HTMLFormElement} formEl — the master form element
 */
window.clearMasterFormValidationUI = function (formEl) {
  if (!formEl || typeof formEl.closest !== 'function') return;
  var root = formEl.closest('.cu-card-body') || formEl.parentElement;
  if (!root) return;

  root.querySelectorAll('.field-error:not(.js-err)').forEach(function (el) {
    el.remove();
  });

  root.querySelectorAll('.cu-error-banner').forEach(function (el) {
    if (el.id === 'prodGridError') return;
    el.remove();
  });

  root.querySelectorAll('.js-err').forEach(function (el) {
    el.textContent = '';
  });

  root.querySelectorAll('.input-error').forEach(function (el) {
    el.classList.remove('input-error');
  });
  root.querySelectorAll('[aria-invalid="true"]').forEach(function (el) {
    el.removeAttribute('aria-invalid');
  });
  root.querySelectorAll('.cell-error').forEach(function (el) {
    el.classList.remove('cell-error');
  });
  root.querySelectorAll('.cell-err-msg').forEach(function (el) {
    el.remove();
  });
};


// ════════════════════════════════════════════════════════════════════
// AUTO-DISMISS ALERTS
// ════════════════════════════════════════════════════════════════════

function initAlerts() {
  document.querySelectorAll('.alert').forEach(alert => {
    // Avoid double-registering on the same element
    if (alert.dataset.timerSet) return;
    alert.dataset.timerSet = 'true';

    setTimeout(() => {
      alert.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
      alert.style.opacity    = '0';
      alert.style.transform  = 'translateX(24px)';
      setTimeout(() => alert.remove(), 300);
    }, 4000);
  });
}


// ════════════════════════════════════════════════════════════════════
// PAGE CONTENT INIT
// Called on DOMContentLoaded AND after every HTMX swap (from partial).
// ════════════════════════════════════════════════════════════════════

window.initPageContent = function() {
  initAlerts();
  updateActiveNav();
  if (typeof initSearchableDropdowns === 'function') {
    initSearchableDropdowns(document);
  }
};


// ════════════════════════════════════════════════════════════════════
// INITIAL PAGE LOAD
// ════════════════════════════════════════════════════════════════════

window.addEventListener('DOMContentLoaded', () => {

  // Restore sidebar collapsed state
  if (localStorage.getItem('sidebarCollapsed') === 'true') {
    document.getElementById('sidebar').classList.add('collapsed');
    document.getElementById('mainContent').classList.add('collapsed');
  }

  // Initialise alerts + active nav
  initPageContent();

  var el = document.querySelector('#mainContent [data-page-init]')
    || document.querySelector('[data-page-init]');
  if (el) {
    var fn = window['initPage_' + el.dataset.pageInit];
    if (typeof fn === 'function') fn();
  }

  // Delete modal: close on backdrop click or Escape
  const modal = document.getElementById('globalDeleteModal');
  if (modal) {
    modal.addEventListener('click', e => { if (e.target === modal) closeDeleteModal(); });
  }
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDeleteModal(); });
});


// ════════════════════════════════════════════════════════════════════
// HTMX EVENTS
// ════════════════════════════════════════════════════════════════════

document.addEventListener('htmx:afterSettle', () => {
  updateActiveNav();
  closeDeleteModal();
});

/**
 * htmx:afterSwap fires immediately after the DOM swap (before settle).
 * Re-init alerts here so they start their 4-second countdown right away.
 */
document.addEventListener('htmx:afterSwap', () => {
  initAlerts();
});
