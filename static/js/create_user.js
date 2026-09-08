/**
 * create_user.js
 * Department → Sub-Department → Role cascading dropdowns.
 * Exposes window.initPage_create_user() so base_partial.html can call it after HTMX swap.
 */

var DEPT_HIERARCHY = {
  "Administration Department": {
    "Management": ["Lab Director","Operations Manager"],
    "Human Resources (HR)": ["HR Manager","HR Executive"],
    "Finance & Accounts": ["Finance Manager","Accountant","Billing Officer"],
    "IT / ERP Management": ["IT Administrator","ERP Administrator","System Support Engineer"],
    "Compliance & Documentation": ["Compliance Officer","Document Controller"]
  },
  "Production Department": {
    "Formulation Unit": ["Production Manager","Formulation Scientist","Production Chemist"],
    "Compounding Unit": ["Compounding Supervisor","Compounding Operator"],
    "Batch Manufacturing": ["Batch Manufacturing Officer","Production Technician"],
    "Packaging Unit": ["Packaging Supervisor","Packaging Operator"],
    "Equipment & Maintenance": ["Maintenance Engineer","Equipment Technician"]
  },
  "Quality Control (QC) Department": {
    "QC Laboratory": ["QC Manager","QC Analyst","QC Technician"],
    "Microbiological Testing": ["Microbiologist","Microbiology Analyst"],
    "Documentation & Compliance": ["QC Documentation Officer","Regulatory Affairs Officer"]
  },
  "Quality Assurance (QA) Department": {
    "QA Oversight": ["QA Manager","QA Officer"],
    "GMP & Audits": ["GMP Compliance Officer","Internal Auditor"],
    "Validation": ["Validation Engineer","Validation Officer"]
  },
  "Research & Development (R&D) Department": {
    "Formulation Development": ["R&D Manager","Senior Formulation Scientist","Junior Formulation Scientist"],
    "Analytical Development": ["Analytical Development Scientist","HPLC Analyst"],
    "Clinical & Regulatory": ["Clinical Research Associate","Regulatory Submissions Officer"]
  },
  "Procurement & Stores Department": {
    "Procurement": ["Procurement Manager","Purchase Officer","Vendor Coordinator"],
    "Stores & Inventory": ["Store Manager","Inventory Controller","Material Handler"],
    "Import / Export": ["Import Export Executive","Customs Coordinator"]
  },
  "Marketing & Sales Department": {
    "Domestic Sales": ["Sales Manager","Medical Representative","Area Sales Manager"],
    "Export Sales": ["Export Manager","International Sales Executive"],
    "Marketing": ["Marketing Manager","Brand Manager","Product Manager"]
  },
  "Engineering & Maintenance Department": {
    "Mechanical Maintenance": ["Maintenance Manager","Mechanical Engineer","Maintenance Technician"],
    "Electrical & Instrumentation": ["Electrical Engineer","Instrument Technician"],
    "Utilities & Facilities": ["Utilities Manager","Facilities Engineer"]
  },
  "Warehouse & Logistics Department": {
    "Finished Goods Warehouse": ["Warehouse Manager","Warehouse Supervisor","Warehouse Associate"],
    "Dispatch & Logistics": ["Logistics Manager","Dispatch Officer","Delivery Coordinator"]
  }
};

function initPage_create_user() {
  var deptSel   = document.getElementById('deptSelect');
  var subSel    = document.getElementById('subDeptSelect');
  var roleSel   = document.getElementById('roleSelect');
  if (!deptSel) return; // not on this page

  function setOptions(selectEl, options, placeholder) {
    if (typeof destroySearchableDropdownsIn === 'function') destroySearchableDropdownsIn(selectEl);
    selectEl.innerHTML = '';
    var ph = document.createElement('option');
    ph.value = ''; ph.textContent = placeholder; ph.disabled = true; ph.selected = true;
    selectEl.appendChild(ph);
    for (var i = 0; i < options.length; i++) {
      var el = document.createElement('option');
      el.value = options[i]; el.textContent = options[i];
      selectEl.appendChild(el);
    }
    if (typeof initSearchableDropdowns === 'function') initSearchableDropdowns(selectEl);
  }

  deptSel.addEventListener('change', function () {
    var dept = this.value;
    if (!dept || !DEPT_HIERARCHY[dept]) {
      setOptions(subSel, [], '\u2014 Select Department first \u2014');
      setOptions(roleSel, [], '\u2014 Select Sub-Dept first \u2014');
      subSel.disabled = true; roleSel.disabled = true;
      return;
    }
    var subDepts = Object.keys(DEPT_HIERARCHY[dept]);
    setOptions(subSel, subDepts, '\u2014 Select Sub-Department \u2014');
    setOptions(roleSel, [], '\u2014 Select Sub-Dept first \u2014');
    subSel.disabled = false; roleSel.disabled = true;
  });

  subSel.addEventListener('change', function () {
    var dept = deptSel.value;
    var subDept = this.value;
    if (!subDept || !DEPT_HIERARCHY[dept] || !DEPT_HIERARCHY[dept][subDept]) {
      setOptions(roleSel, [], '\u2014 Select Sub-Dept first \u2014');
      roleSel.disabled = true; return;
    }
    setOptions(roleSel, DEPT_HIERARCHY[dept][subDept], '\u2014 Select Role \u2014');
    roleSel.disabled = false;
  });

  // Password confirmation
  var form  = document.getElementById('createUserForm');
  var pwd   = document.getElementById('passwordInput');
  var cpwd  = document.getElementById('confirmPasswordInput');
  var cpErr = document.getElementById('confirmPasswordError');

  if (form && pwd && cpwd && cpErr) {
    function validateConfirm() {
      if (cpwd.value && pwd.value !== cpwd.value) {
        cpErr.style.display = 'block';
        cpwd.style.borderColor = '#dc2626';
        cpwd.style.boxShadow = '0 0 0 3px rgba(220,38,38,.12)';
      } else {
        cpErr.style.display = 'none';
        cpwd.style.borderColor = '';
        cpwd.style.boxShadow = '';
      }
    }
    cpwd.addEventListener('input', validateConfirm);
    pwd.addEventListener('input',  validateConfirm);
    form.addEventListener('submit', function (e) {
      validateConfirm();
      if (pwd.value !== cpwd.value) { e.preventDefault(); cpwd.focus(); }
    });
  }
}

window.initPage_create_user = initPage_create_user;
initPage_create_user();
