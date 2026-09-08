# PharmaERP Models Overview

## Quick Summary

**Total Models Documented**: 41  
**Database**: MySQL 8.0+  
**ORM**: Django 3.2+

### Model Count by App
| App | Count | Models |
|-----|-------|--------|
| **Masters** | 28 | Department, Section, Machine, Operator, OperatorSection, UOM, State, Transport, PdnStage, Expenses, Color, Shape, CoatType, Capsule, ProdCat, ItemType, PkgStyle, Product, Item, Customer, Supplier, CustomerProduct, BomRmHed, BomRmDtl, BomPmHed, BomPmDtl, FinancialYear |
| **Transactions** | 13 | TrnInwHed, TrnInwDtl1, TrnInwDtl2, TrnSlsOrdHed, TrnSlsOrdDtl1, TrnSlsOrdDtl2, TrnBatchHed, TrnBatchDtl, TrnLogSheet, TrnPkgCont, TrnSlsHed, TrnSlsDtl1, TrnSlsDtl2 |
| **Inventory** | 5 | InvCustMonthlyStock, InventoryStock, TrnStkAdjHed, TrnStkAdjDtl1, TrnStkAdjDtl2 |
| **Reports** | 1 | ReportAccess (metadata-only) |

## Table of Contents
1. [Masters Models](#masters-models)
2. [Transaction Models](#transaction-models)
3. [Inventory Models](#inventory-models)
4. [Relationships Diagram](#relationships-diagram)
5. [Database Constraints](#database-constraints)

---

## Masters Models

### Core Organization Structure

#### `MstDepartment`
Master list of organizational departments.
- **Table**: `MstDepartment`
- **Primary Key**: `dept_id` (AutoField)
- **Columns**:
  - `dept_id`: PK (AUTO_INCREMENT)
  - `dept_name`: CharField(150), UNIQUE

**Related Models**:
- ← `MstSection` (dept_id)

---

#### `MstSection`
Sections belonging to a department.
- **Table**: `MstSection`
- **Primary Key**: `section_id` (AutoField)
- **Columns**:
  - `section_id`: PK (AUTO_INCREMENT)
  - `section_name`: CharField(150), UNIQUE
  - `dept_id` (FK): → `MstDepartment`

**Constraints**:
- UNIQUE(section_name)
- UNIQUE(section_name, dept_id)

**Related Models**:
- → `MstDepartment` (dept_id)
- ← `MstMachine` (section_id)
- ← `MstOperatorSection` (section_id)
- ← `TrnLogSheet` (section_id)

---

#### `MstMachine`
Machines linked to sections.
- **Table**: `MstMachine`
- **Primary Key**: `machine_id` (AutoField)
- **Columns**:
  - `machine_id`: PK (AUTO_INCREMENT)
  - `machine_name`: CharField(200), UNIQUE
  - `section_id` (FK): → `MstSection`
  - `make`: CharField(150), nullable
  - `model_no`: CharField(100), nullable
  - `machine_no`: CharField(100), nullable
  - `capacity`: CharField(100), nullable
  - `installed_date`: DateField, nullable
  - `remarks`: TextField, nullable

**Related Models**:
- → `MstSection` (section_id)

---

#### `MstOperator`
Operator/staff master.
- **Table**: `mstoperator`
- **Primary Key**: `Opt_id` (AutoField)
- **Columns**:
  - `Opt_id`: PK (AUTO_INCREMENT)
  - `Opt_name`: CharField(30), UNIQUE
  - `Designation`: CharField(200), nullable

**Related Models**:
- ← `MstOperatorSection` (Opt_id)

---

#### `MstOperatorSection`
Many-to-many linking operators to sections.
- **Table**: `MstOperatorSection`
- **Primary Key**: Composite (Opt_id, section_id)
- **Columns**:
  - `Opt_id` (FK): → `MstOperator`
  - `section_id` (FK): → `MstSection`

**Constraints**:
- UNIQUE(Opt_id, section_id)

**Related Models**:
- → `MstOperator` (Opt_id)
- → `MstSection` (section_id)

---

### Units & Logistics

#### `MstUom`
Unit of Measurement master.
- **Table**: `MstUom`
- **Primary Key**: `uom_id` (AutoField)
- **Columns**:
  - `uom_id`: PK (AUTO_INCREMENT)
  - `uom_name`: CharField(150), UNIQUE
  - `short_name`: CharField(3), UNIQUE

**Related Models**:
- ← `MstProd` (uom_id)
- ← `MstItem` (uom_id)
- ← `TrnInwDtl1` (uom_id)
- ← `MstBomRmDtl` (uom_id)
- ← `MstBomPmDtl` (uom_id)

---

#### `MstState`
Indian states with GST codes.
- **Table**: `MstState`
- **Primary Key**: `state_id` (AutoField)
- **Columns**:
  - `state_id`: PK (AUTO_INCREMENT)
  - `state_name`: CharField(150), UNIQUE
  - `gst_code`: CharField(10), UNIQUE

**Related Models**:
- ← `MstCust` (state_id)
- ← `MstSupplier` (state_id)

---

#### `MstTransport`
Transporter/carrier master.
- **Table**: `MstTransport`
- **Primary Key**: `transport_id` (AutoField)
- **Columns**:
  - `transport_id`: PK (AUTO_INCREMENT)
  - `transport_name`: CharField(200), UNIQUE

**Related Models**:
- ← `TrnInwHed` (transport_id)

---

#### `MstPdnStage`
Production/manufacturing stages.
- **Table**: `MstPdnStage`
- **Primary Key**: `stage_id` (AutoField)
- **Columns**:
  - `stage_id`: PK (AUTO_INCREMENT)
  - `stage_name`: CharField(150), UNIQUE

**Related Models**:
- ← `MstBomRmDtl` (stage_id)
- ← `MstBomPmDtl` (stage_id)

---

#### `MstExpenses`
Expense categories master.
- **Table**: `MstExpenses`
- **Primary Key**: `exp_id` (AutoField)
- **Columns**:
  - `exp_id`: PK (AUTO_INCREMENT)
  - `exp_name`: CharField(200), UNIQUE

---

### Product Attributes

#### `MstColor`
Color/colour options for products.
- **Table**: `MstColor`
- **Primary Key**: `color_id` (AutoField)
- **Columns**:
  - `color_id`: PK (AUTO_INCREMENT)
  - `color_name`: CharField(150), UNIQUE

**Related Models**:
- ← `MstProd` (first_color_id, second_color_id)
- ← `MstBomRmHed` (color_id)

---

#### `MstShape`
Product shape types.
- **Table**: `MstShape`
- **Primary Key**: `shape_id` (AutoField)
- **Columns**:
  - `shape_id`: PK (AUTO_INCREMENT)
  - `shape_name`: CharField(150), UNIQUE

**Related Models**:
- ← `MstBomRmHed` (shape_id)

---

#### `MstCoatType`
Coating type options.
- **Table**: `MstCoatType`
- **Primary Key**: `coating_id` (AutoField)
- **Columns**:
  - `coating_id`: PK (AUTO_INCREMENT)
  - `coating_name`: CharField(150), UNIQUE

**Related Models**:
- ← `MstBomRmHed` (coating_id)

---

#### `MstCapsule`
Capsule types (size + color combinations).
- **Table**: `MstCapsule`
- **Primary Key**: `capsule_id` (AutoField)
- **Columns**:
  - `capsule_id`: PK (AUTO_INCREMENT)
  - `capsule_name`: CharField(200), UNIQUE (auto-derived)
  - `capsule_size`: CharField(100)
  - `capsule_color`: CharField(100)

**Constraints**:
- UNIQUE(capsule_size, capsule_color)

**Related Models**:
- ← `MstBomRmHed` (capsule_id)

---

### Product Categories & Types

#### `MstProdCat`
Product categories (RM = Raw Material, PM = Packing Material).
- **Table**: `MstProdCat`
- **Primary Key**: `prod_cat_id` (CharField(2))
- **Columns**:
  - `prod_cat_id`: PK (CharField(2), e.g., "RM", "PM")
  - `prod_cat_name`: CharField(150), UNIQUE

**Related Models**:
- ← `MstItemType` (prod_cat_id)
- ← `MstProd` (prod_cat_id)
- ← `MstItem` (item_cat_id)
- ← `TrnInwHed` (grn_prod_cat_id)

---

#### `MstItemType`
Item/product type classification.
- **Table**: `MstItemType`
- **Primary Key**: `item_type_id` (AutoField)
- **Columns**:
  - `item_type_id`: PK (AUTO_INCREMENT)
  - `prod_cat_id` (FK): → `MstProdCat`
  - `item_type_name`: CharField(150), UNIQUE

**Related Models**:
- → `MstProdCat` (prod_cat_id)
- ← `MstProd` (item_type_id)
- ← `MstItem` (item_type_id)
- ← `MstPkgStyle` (pkg_type_id)

---

#### `MstPkgStyle`
Packing styles (e.g., Carton, Shipper, Box).
- **Table**: `MstPkgStyle`
- **Primary Key**: `pkg_style_id` (AutoField)
- **Columns**:
  - `pkg_style_id`: PK (AUTO_INCREMENT)
  - `pkg_style_name`: CharField(150)
  - `pkg_style_value`: PositiveIntegerField (> 0)
  - `pkg_type_id` (FK): → `MstItemType`

**Constraints**:
- UNIQUE(pkg_style_name, pkg_type_id)

**Related Models**:
- → `MstItemType` (pkg_type_id)
- ← `TrnSlsOrdDtl1` (pkg_style_id)
- ← `MstBomPmHed` (pkg_style_id)

---

### Products & Items

#### `MstProd`
Master product register.
- **Table**: `MstProd`
- **Primary Key**: `prod_id` (AutoField)
- **Columns**:
  - `prod_id`: PK (AUTO_INCREMENT)
  - `prod_name`: CharField(200), UNIQUE
  - `generic_name`: TextField
  - `item_type_id` (FK): → `MstItemType`
  - `prod_cat_id` (FK): → `MstProdCat`
  - `uom_id` (FK): → `MstUom`
  - `hsn_code`: CharField(50), nullable
  - `tablet_layer`: CharField(10), choices: ['Single', 'Double']
  - `first_color_id` (FK): → `MstColor`, nullable
  - `second_color_id` (FK): → `MstColor`, nullable
  - `image_path`: CharField(500), nullable (relative to MEDIA_ROOT)

**Business Rules**:
- Only Single or Double layer allowed
- first_color & second_color only valid when tablet_layer = Double
- first_color ≠ second_color when both set

**Related Models**:
- → `MstItemType` (item_type_id)
- → `MstProdCat` (prod_cat_id)
- → `MstUom` (uom_id)
- → `MstColor` (first_color_id, second_color_id)
- ← `MstCustProd` (prod_id)
- ← `TrnSlsOrdDtl1` (prod_id)
- ← `TrnSlsOrdDtl2` (prod_id)
- ← `TrnBatchHed` (prod_id)
- ← `TrnLogSheet` (prod_id)
- ← `TrnInwDtl2` (prod_id)
- ← `MstBomRmHed` (prod_id)
- ← `MstBomPmHed` (prod_id)

---

#### `MstItem`
Raw Material / Packing Material item master.
- **Table**: `MstItem`
- **Primary Key**: `item_id` (AutoField)
- **Columns**:
  - `item_id`: PK (AUTO_INCREMENT)
  - `item_name`: CharField(200), UNIQUE
  - `item_type_id` (FK): → `MstItemType`
  - `item_cat_id` (FK): → `MstProdCat` (derived from item_type)
  - `uom_id` (FK): → `MstUom`
  - `hsn_code`: CharField(50), nullable
  - `min_level`: DecimalField(10, 3), nullable (minimum stock level)
  - `max_level`: DecimalField(10, 3), nullable (maximum stock level)
  - `maintain_batch`: CharField(1), choices: ['Y', 'N'], default='N'
  - `mfg_date`: CharField(1), choices: ['Y', 'N'], default='N' (track mfg date)
  - `exp_date`: CharField(1), choices: ['Y', 'N'], default='N' (track expiry)
  - `last_purchase_rate`: DecimalField(12, 2), default=0
  - `sample_qty`: DecimalField(10, 3), default=0 (deducted from inwards)

**Business Rules**:
- mfg_date can only be 'Y' when maintain_batch = 'Y'
- exp_date can only be 'Y' when mfg_date = 'Y'
- max_level ≥ min_level

**Related Models**:
- → `MstItemType` (item_type_id)
- → `MstProdCat` (item_cat_id)
- → `MstUom` (uom_id)
- ← `TrnInwDtl1` (item_id)
- ← `TrnInwDtl2` (item_id)
- ← `MstBomRmDtl` (item_id)
- ← `MstBomPmDtl` (item_id)

---

### Customer & Supplier

#### `MstCust`
Customer master.
- **Table**: `MstCust`
- **Primary Key**: `cust_id` (AutoField)
- **Columns**:
  - `cust_id`: PK (AUTO_INCREMENT)
  - `cust_name`: CharField(200), UNIQUE
  - `short_name`: CharField(10), UNIQUE
  - `address`: TextField
  - `state_id` (FK): → `MstState`
  - `pin_code`: CharField(6), nullable
  - `landline_no`: CharField(20), nullable
  - `mobile_no`: CharField(10), nullable
  - `email`: CharField(50), nullable
  - `pan_no`: CharField(10), nullable
  - `gst_no`: CharField(15), nullable
  - `udyam_cert`: CharField(30), nullable

**Business Rules**:
- short_name becomes immutable once used in transactions
- Mandatory: address, state

**Related Models**:
- → `MstState` (state_id)
- ← `MstCustProd` (cust_id)
- ← `TrnInwHed` (cust_id)
- ← `TrnSlsOrdHed` (cust_id)
- ← `TrnBatchHed` (cust_id)
- ← `TrnLogSheet` (cust_id)
- ← `MstBomRmHed` (cust_id)
- ← `MstBomPmHed` (cust_id)

---

#### `MstSupplier`
Supplier/vendor master.
- **Table**: `mstSupplier`
- **Primary Key**: `supl_id` (AutoField)
- **Columns**:
  - `supl_id`: PK (AUTO_INCREMENT)
  - `supl_name`: CharField(200), UNIQUE
  - `short_name`: CharField(10), UNIQUE, nullable
  - `address`: TextField
  - `state_id` (FK): → `MstState`
  - `pin_code`: CharField(6)
  - `landline_no`: CharField(10), nullable
  - `mobile_no`: CharField(10), nullable
  - `email`: CharField(150), nullable
  - `pan_no`: CharField(10), nullable
  - `gst_no`: CharField(15), nullable
  - `udyam_cert`: CharField(30), nullable

**Related Models**:
- → `MstState` (state_id)
- ← `TrnInwHed` (supl_id)

---

#### `MstCustProd`
Products ordered by a customer (many-to-many).
- **Table**: `MstCustProd`
- **Primary Key**: `cust_prod_id` (AutoField)
- **Columns**:
  - `cust_prod_id`: PK (AUTO_INCREMENT)
  - `cust_id` (FK): → `MstCust` (CASCADE)
  - `prod_id` (FK): → `MstProd` (PROTECT)
  - `adv_license`: CharField(1), choices: ['Y', 'N'], default='N'
  - `license_details`: CharField(300), nullable (mandatory if adv_license='Y')
  - `batch_abbr`: CharField(3), mandatory (exactly 3 chars, uppercase)

**Constraints**:
- UNIQUE(cust_id, prod_id)

**Related Models**:
- → `MstCust` (cust_id)
- → `MstProd` (prod_id)

---

### Bill of Materials (BOM)

#### `MstBomRmHed`
BOM Raw Materials - Header.
- **Table**: `MstBomRmHed`
- **Primary Key**: `spec_id` (AutoField)
- **Columns**:
  - `spec_id`: PK (AUTO_INCREMENT)
  - `spec_name`: CharField(300)
  - `cust_id` (FK): → `MstCust`
  - `prod_id` (FK): → `MstProd`
  - `shape_id` (FK): → `MstShape`, nullable
  - `color_id` (FK): → `MstColor`, nullable
  - `coating_id` (FK): → `MstCoatType`, nullable
  - `capsule_id` (FK): → `MstCapsule`, nullable
  - `avg_wt`: PositiveIntegerField, nullable
  - `batch_size`: DecimalField(10, 2) (in lakh)
  - `batch_nos`: PositiveBigIntegerField (derived: batch_size × 100,000)
  - `is_locked`: BooleanField, default=False

**Constraints**:
- UNIQUE(spec_name, prod_id)

**Related Models**:
- → `MstCust` (cust_id)
- → `MstProd` (prod_id)
- → `MstShape` (shape_id)
- → `MstColor` (color_id)
- → `MstCoatType` (coating_id)
- → `MstCapsule` (capsule_id)
- ← `MstBomRmDtl` (spec_id)

---

#### `MstBomRmDtl`
BOM Raw Materials - Detail Lines.
- **Table**: `MstBomRmDtl`
- **Primary Key**: `dtl_id` (AutoField)
- **Columns**:
  - `dtl_id`: PK (AUTO_INCREMENT)
  - `spec_id` (FK): → `MstBomRmHed` (CASCADE)
  - `stage_id` (FK): → `MstPdnStage`
  - `item_id` (FK): → `MstItem`
  - `qty`: DecimalField(12, 3)
  - `uom_id` (FK): → `MstUom`

**Constraints**:
- UNIQUE(spec_id, stage_id, item_id)

**Related Models**:
- → `MstBomRmHed` (spec_id)
- → `MstPdnStage` (stage_id)
- → `MstItem` (item_id)
- → `MstUom` (uom_id)

---

#### `MstBomPmHed`
BOM Packing Materials - Header.
- **Table**: `MstBomPmHed`
- **Primary Key**: `spec_id` (AutoField)
- **Columns**:
  - `spec_id`: PK (AUTO_INCREMENT)
  - `spec_name`: CharField(300)
  - `cust_id` (FK): → `MstCust`
  - `prod_id` (FK): → `MstProd`
  - `pkg_style_id` (FK): → `MstPkgStyle`
  - `batch_size`: DecimalField(10, 2) (in lakh)
  - `batch_nos`: PositiveBigIntegerField (derived: batch_size × 100,000)
  - `is_locked`: BooleanField, default=False

**Constraints**:
- UNIQUE(cust_id, prod_id, pkg_style_id)
- UNIQUE(spec_name, prod_id)

**Related Models**:
- → `MstCust` (cust_id)
- → `MstProd` (prod_id)
- → `MstPkgStyle` (pkg_style_id)
- ← `MstBomPmDtl` (spec_id)

---

#### `MstBomPmDtl`
BOM Packing Materials - Detail Lines.
- **Table**: `MstBomPmDtl`
- **Primary Key**: `dtl_id` (AutoField)
- **Columns**:
  - `dtl_id`: PK (AUTO_INCREMENT)
  - `spec_id` (FK): → `MstBomPmHed` (CASCADE)
  - `stage_id` (FK): → `MstPdnStage`
  - `item_id` (FK): → `MstItem`
  - `qty`: DecimalField(12, 3)
  - `uom_id` (FK): → `MstUom`

**Constraints**:
- UNIQUE(spec_id, stage_id, item_id)

**Related Models**:
- → `MstBomPmHed` (spec_id)
- → `MstPdnStage` (stage_id)
- → `MstItem` (item_id)
- → `MstUom` (uom_id)

---

### Financial Year (Backend Only)

#### `FinancialYear`
Financial year master (Apr 1 → Mar 31).
- **Table**: `MstFinYr`
- **Primary Key**: `fy_id` (AutoField)
- **Columns**:
  - `fy_id`: PK (AUTO_INCREMENT)
  - `fy_start_year`: PositiveIntegerField, UNIQUE (e.g., 2025)
  - `fy_end_year`: PositiveIntegerField (e.g., 2026)
  - `fy_display`: CharField(9) (format: "2025-26")
  - `start_date`: DateField (1-Apr of start_year)
  - `end_date`: DateField (31-Mar of end_year)
  - `is_current`: BooleanField, default=False
  - `is_open`: BooleanField, default=True
  - `is_closed`: BooleanField, default=False
  - `remarks`: TextField, nullable
  - `created_at`: DateTimeField (auto_now_add)
  - `updated_at`: DateTimeField (auto_now)

**Constraints**:
- CHECK: fy_end_year = fy_start_year + 1
- CHECK: start_date is 1-Apr
- CHECK: end_date is 31-Mar
- CHECK: start_date ≤ end_date
- CHECK: NOT (is_current AND is_closed)
- UNIQUE(fy_start_year)

**Business Rules**:
- Only one current FY at a time
- Current FY cannot be closed
- FY assignment is backend-only (users don't enter FY fields)

**Related Models**:
- ← `TrnInwHed` (fy_id)
- ← `TrnSlsOrdHed` (fy_id)

---

## Transaction Models

### Inward (GRN - Goods Receipt Note)

#### `TrnInwHed`
Inward transaction header (one purchase receipt).
- **Table**: `TrnInwHed`
- **Primary Key**: `inward_id` (AutoField)
- **Columns**:
  - `inward_id`: PK (AUTO_INCREMENT)
  - `inward_dt`: DateField
  - `fy_id` (FK): → `FinancialYear` (backend-only)
  - `working_year`: CharField(9), db_indexed (e.g., "2025-26")
  - `cust_id` (FK): → `MstCust`
  - `register_no`: CharField(20), UNIQUE (format: R-00001, R-100000, etc.)
  - `grn_prod_cat_id` (FK): → `MstProdCat` (RM or PM)
  - `grn_no`: CharField(50) (format: RM-00001 or PM-00001)
  - `supl_id` (FK): → `MstSupplier`
  - `inv_no`: CharField(100) (supplier invoice number)
  - `inv_dt`: DateField (supplier invoice date)
  - `transport_id` (FK): → `MstTransport`
  - `vehicle_no`: CharField(50)
  - `driver_name`: CharField(150), nullable
  - `driver_no`: CharField(30), nullable (driver contact)
  - `remarks`: TextField, nullable
  - `documents`: CharField(500), nullable (path to uploaded file)

**Constraints**:
- UNIQUE(grn_no, fy_id)
- CHECK: inv_dt ≤ inward_dt
- CHECK: grn_category_id in GRN_CATEGORY_IDS (RM or PM)
- register_no format: R-plus-digits

**Business Rules**:
- invoice_date must not be after inward_date
- GRN number prefix must match category (RM or PM)

**Related Models**:
- → `FinancialYear` (fy_id)
- → `MstCust` (cust_id)
- → `MstProdCat` (grn_prod_cat_id)
- → `MstSupplier` (supl_id)
- → `MstTransport` (transport_id)
- ← `TrnInwDtl1` (inward_id)
- ← `TrnInwDtl2` (inward_id)

---

#### `TrnInwDtl1`
Inward detail line (one item per inward).
- **Table**: `TrnInwDtl1`
- **Primary Key**: `dtl1_id` (AutoField)
- **Columns**:
  - `dtl1_id`: PK (AUTO_INCREMENT)
  - `inward_id` (FK): → `TrnInwHed` (CASCADE)
  - `item_id` (FK): → `MstItem`
  - `quantity`: DecimalField(14, QTY_DECIMAL_PLACES)
  - `uom_id` (FK): → `MstUom`
  - `rate`: DecimalField(12, 2), default=0

**Constraints**:
- UNIQUE(inward_id, item_id)
- CHECK: quantity > 0
- CHECK: rate ≥ 0

**Business Rules**:
- UOM must match item master UOM
- Each item can appear only once per inward

**Related Models**:
- → `TrnInwHed` (inward_id)
- → `MstItem` (item_id)
- → `MstUom` (uom_id)
- ← `TrnInwDtl2` (inward_id, item_id)

---

#### `TrnInwDtl2`
Inward batch detail (only when item.maintain_batch = 'Y').
- **Table**: `TrnInwDtl2`
- **Primary Key**: `dtl2_id` (AutoField)
- **Columns**:
  - `dtl2_id`: PK (AUTO_INCREMENT)
  - `inward_id` (FK): → `TrnInwHed` (CASCADE)
  - `item_id` (FK): → `MstItem`
  - `batch_no`: CharField(100)
  - `arn_no`: CharField(20), nullable (ARN = Acceptance/Rejection Note)
  - `pkg_style_id`: CharField(30) (free-text packing style)
  - `mfg_dt`: DateField, nullable
  - `exp_dt`: DateField, nullable
  - `batch_qty`: DecimalField(14, QTY_DECIMAL_PLACES)
  - `prod_id` (FK): → `MstProd`, nullable

**Constraints**:
- UNIQUE(inward_id, item_id, batch_no)
- CHECK: exp_dt > mfg_dt (when both present)
- CHECK: batch_qty > 0

**Business Rules**:
- Batch lines only allowed when item.maintain_batch = 'Y'
- Each batch line must have corresponding TrnInwDtl1 line
- expiry_date must be after manufacturing_date

**Related Models**:
- → `TrnInwHed` (inward_id)
- → `MstItem` (item_id)
- → `MstProd` (prod_id)

---

### Sales Order

#### `TrnSlsOrdHed`
Sales order header.
- **Table**: `TrnSlsOrdHed`
- **Primary Key**: `order_id` (AutoField)
- **Columns**:
  - `order_id`: PK (AUTO_INCREMENT)
  - `ord_rec_dt`: DateField (order received/record date)
  - `cust_id` (FK): → `MstCust`
  - `cust_ord_id`: CharField(20) (customer's PO number)
  - `cust_ord_date`: DateField (customer PO date)
  - `delivery_add`: CharField(200), nullable
  - `taxable_val`: DecimalField(12, 2), default=0
  - `pkg_fwd_amt`: DecimalField(12, 2), default=0 (packing/forwarding)
  - `frieght_amt`: DecimalField(12, 2), default=0 (freight)
  - `oth_charges`: DecimalField(12, 2), default=0
  - `cgst_amt`: DecimalField(12, 2), default=0 (Central GST)
  - `sgst_amt`: DecimalField(12, 2), default=0 (State GST)
  - `igst_amt`: DecimalField(12, 2), default=0 (Integrated GST)
  - `round_off`: DecimalField(6, 2), default=0 (range: -1 to +1)
  - `total_amt`: DecimalField(12, 2), default=0
  - `terms_cond`: CharField(1000), nullable
  - `remarks`: CharField(500), nullable
  - `fy_id` (FK): → `FinancialYear` (backend-only)
  - `working_year`: CharField(9), db_indexed (e.g., "2025-26")
  - `document_path`: CharField(150), nullable

**Constraints**:
- UNIQUE(cust_id, cust_ord_id)
- CHECK: taxable_val ≥ 0
- CHECK: pkg_fwd_amt ≥ 0
- CHECK: frieght_amt ≥ 0
- CHECK: oth_charges ≥ 0
- CHECK: cgst_amt ≥ 0
- CHECK: sgst_amt ≥ 0
- CHECK: igst_amt ≥ 0
- CHECK: total_amt ≥ 0
- CHECK: -1 ≤ round_off ≤ 1
- CHECK: cust_ord_date ≤ ord_rec_dt

**Business Rules**:
- Customer order date must not be after order record date
- Order date must fall within financial year

**Related Models**:
- → `MstCust` (cust_id)
- → `FinancialYear` (fy_id)
- ← `TrnSlsOrdDtl1` (order_id)
- ← `TrnSlsOrdDtl2` (order_id)
- ← `TrnBatchHed` (order_id)

---

#### `TrnSlsOrdDtl1`
Sales order line (one product + packing style per line).
- **Table**: `TrnSlsOrdDtl1`
- **Primary Key**: `dtl1_id` (AutoField)
- **Columns**:
  - `dtl1_id`: PK (AUTO_INCREMENT)
  - `order_id` (FK): → `TrnSlsOrdHed` (CASCADE)
  - `prod_id` (FK): → `MstProd`
  - `hsn_no`: CharField(50)
  - `pkg_style_id` (FK): → `MstPkgStyle`
  - `order_qty`: DecimalField(10, SO_QTY_DECIMAL_PLACES) (in Lakhs)
  - `remaining_qty`: DecimalField(10, SO_QTY_DECIMAL_PLACES), default=0
  - `is_completed`: BooleanField, default=False (True when remaining_qty = 0)
  - `ord_qty_nos`: DecimalField(12, 0), default=0 (Order qty in numbers)
  - `rate`: DecimalField(5, 2) (price per unit)
  - `taxable_amt`: DecimalField(12, 2), default=0
  - `gst_type`: CharField(20), choices: [CGST_SGST, IGST, EXEMPTED]
  - `gst_per`: DecimalField(5, 2) (GST percentage: 0-100)
  - `cgst_amt`: DecimalField(12, 2), default=0
  - `sgst_amt`: DecimalField(12, 2), default=0
  - `igst_amt`: DecimalField(12, 2), default=0
  - `prod_amt`: DecimalField(12, 2), default=0
  - `export_type`: CharField(100)

**Constraints**:
- UNIQUE(order_id, prod_id, pkg_style_id, rate)
- CHECK: order_qty > 0
- CHECK: rate > 0
- CHECK: taxable_amt ≥ 0
- CHECK: ord_qty_nos ≥ 0
- CHECK: remaining_qty ≥ 0
- CHECK: 0 ≤ gst_per ≤ 100
- CHECK: gst_type in GST_TYPE_IDS

**Business Rules**:
- Packing style must belong to product type
- remaining_qty decreases as batches are allocated
- is_completed set to True when remaining_qty reaches 0

**Related Models**:
- → `TrnSlsOrdHed` (order_id)
- → `MstProd` (prod_id)
- → `MstPkgStyle` (pkg_style_id)
- ← `TrnBatchHed` (order_dtl1_id)

---

#### `TrnSlsOrdDtl2`
Sales order dispatch schedule line.
- **Table**: `TrnSlsOrdDtl2`
- **Primary Key**: `dtl2_id` (AutoField)
- **Columns**:
  - `dtl2_id`: PK (AUTO_INCREMENT)
  - `order_id` (FK): → `TrnSlsOrdHed` (CASCADE)
  - `prod_id` (FK): → `MstProd`
  - `disp_sche_dt`: DateField (dispatch schedule date)
  - `disp_qty`: DecimalField(10, SO_QTY_DECIMAL_PLACES) (dispatch qty in Lakhs)
  - `remarks`: CharField(20), nullable

**Constraints**:
- UNIQUE(order_id, prod_id, disp_sche_dt)
- CHECK: disp_qty > 0

**Related Models**:
- → `TrnSlsOrdHed` (order_id)
- → `MstProd` (prod_id)

---

### Batch Allocation

#### `TrnBatchHed`
Batch allocation header (one run per order line).
- **Table**: `TrnBatchHed`
- **Primary Key**: `batch_id` (AutoField)
- **Columns**:
  - `batch_id`: PK (AUTO_INCREMENT)
  - `cust_id` (FK): → `MstCust`
  - `order_id` (FK): → `TrnSlsOrdHed` (CASCADE)
  - `order_dtl1_id` (FK): → `TrnSlsOrdDtl1` (CASCADE)
  - `prod_id` (FK): → `MstProd`
  - `batch_size_l`: DecimalField(12, 5) (in Lacs)
  - `batch_size_n`: DecimalField(12, 0) (in Numbers)
  - `partial_yn`: CharField(1), choices: ['Y', 'N'], default='N'
  - `partial_qty_l`: DecimalField(12, 5), nullable
  - `partial_qty_n`: DecimalField(12, 0), nullable
  - `batch_abbr`: CharField(3) (batch abbreviation from customer product)
  - `batch_from`: IntegerField (batch range start)
  - `batch_to`: IntegerField (batch range end)

**Constraints**:
- CHECK: batch_from ≤ batch_to
- CHECK: partial_yn in ['Y', 'N']

**Related Models**:
- → `MstCust` (cust_id)
- → `TrnSlsOrdHed` (order_id)
- → `TrnSlsOrdDtl1` (order_dtl1_id)
- → `MstProd` (prod_id)
- ← `TrnBatchDtl` (batch_id)
- ← `TrnLogSheet` (batch_id via TrnBatchDtl)

---

#### `TrnBatchDtl`
Batch allocation detail (one physical batch number).
- **Table**: `TrnBatchDtl`
- **Primary Key**: `dtl_id` (AutoField)
- **Columns**:
  - `dtl_id`: PK (AUTO_INCREMENT)
  - `batch_id` (FK): → `TrnBatchHed` (CASCADE)
  - `batch_no`: CharField(15), UNIQUE
  - `batch_qty_l`: DecimalField(12, 5) (qty in Lacs)
  - `batch_qty_n`: DecimalField(12, 0) (qty in Numbers)
  - `mfg_dt`: CharField(8) (format: MMM-YYYY, e.g., "JAN-2026")
  - `exp_dt`: CharField(8) (format: MMM-YYYY, e.g., "DEC-2028")
  - `log_sheet_flg`: CharField(1), choices: ['Y', 'N'], default='N'

**Constraints**:
- CHECK: batch_qty_l > 0
- CHECK: batch_qty_n ≥ 0
- CHECK: log_sheet_flg in ['Y', 'N']

**Related Models**:
- → `TrnBatchHed` (batch_id)
- ← `TrnLogSheet` (batch_id)

---

### Log Sheet (Production Log)

#### `TrnLogSheet`
Granulation/production log sheet (one per batch for single-layer, two for double-layer).
- **Table**: `Trn_LogSheet`
- **Primary Key**: `logsheet_id` (AutoField)
- **Columns**:
  - `logsheet_id`: PK (AUTO_INCREMENT)
  - `section_id` (FK): → `MstSection`
  - `gran_dt`: DateField (granulation date)
  - `cust_id` (FK): → `MstCust`
  - `shift_id`: CharField(5), choices: ['Day', 'Night']
  - `prod_id` (FK): → `MstProd`
  - `batch_id` (FK): → `TrnBatchDtl` (PROTECT)
  - `blend_dt`: DateField, nullable (blending date)
  - `dpr_flg`: CharField(1), choices: ['Y', 'N'], default='N' (Daily Production Report)
  - `rm_disp_flg`: CharField(1), choices: ['Y', 'N'], default='N' (RM dispensing completed)
  - `layer_slot`: CharField(1), choices: ['S', '1', '2'], default='S'
    - 'S' = Single-layer batch
    - '1' = First colour (double-layer)
    - '2' = Second colour (double-layer)

**Constraints**:
- UNIQUE(batch_id, layer_slot)
- CHECK: shift_id in ['Day', 'Night']
- CHECK: dpr_flg in ['Y', 'N']
- CHECK: rm_disp_flg in ['Y', 'N']
- CHECK: layer_slot in ['S', '1', '2']

**Business Rules**:
- Single-layer products: only layer_slot = 'S'
- Double-layer products: layer_slot must be '1' or '2'
- Two log sheet rows created for double-layer batches (one per slot)
- mfg_dt (from batch_id) must be before exp_dt

**Related Models**:
- → `MstSection` (section_id)
- → `MstCust` (cust_id)
- → `MstProd` (prod_id)
- → `TrnBatchDtl` (batch_id)
- ← `TrnPkgCont` (logsheet_id)
- ← `TrnSlsDtl2` (logsheet_id)

---

### Daily Packing (Contractor)

#### `TrnPkgCont`
Daily packing records for contractor operations.
- **Table**: `TrnPkgCont`
- **Primary Key**: `pkgcont_id` (AutoField)
- **Columns**:
  - `pkgcont_id`: PK (AUTO_INCREMENT)
  - `pkgcont_date`: DateField
  - `contractor_id` (FK): → `MstOperator` (must have designation = 'CONTRACTOR')
  - `logsheet_id` (FK): → `TrnLogSheet` (PROTECT)
  - `pkg_style_id` (FK): → `MstPkgStyle` (PROTECT)
  - `no_of_girls`: PositiveSmallIntegerField, nullable (packing manpower)
  - `shipper_no`: PositiveIntegerField (range: 1–999999)
  - `qty_nos`: DecimalField(12, 0) (qty in numbers)
  - `qty_loose`: DecimalField(12, 0), nullable (loose qty)
  - `remarks`: TextField, nullable

**Constraints**:
- UNIQUE(pkgcont_date, logsheet_id, contractor_id, pkg_style_id)
- CHECK: 1 ≤ shipper_no ≤ 999999
- CHECK: qty_nos ≥ 1
- CHECK: no_of_girls ≤ 9999 (if not null)
- CHECK: qty_loose ≥ 0 (if not null)

**Business Rules**:
- Contractor must have designation = 'CONTRACTOR'
- Packing style must belong to the log sheet product's type
- One record per (date, log sheet, contractor, packing style) combination

**Related Models**:
- → `MstOperator` (contractor_id)
- → `TrnLogSheet` (logsheet_id)
- → `MstPkgStyle` (pkg_style_id)

---

### Sales Invoice (Outward)

#### `TrnSlsHed`
Sales invoice header (outward/dispatch invoice).
- **Table**: `TrnSlsHed`
- **Primary Key**: `invoice_id` (AutoField)
- **Columns**:
  - `invoice_id`: PK (AUTO_INCREMENT)
  - `invoice_no`: CharField(15), UNIQUE per FY (format: SI-00001, SI-100000, etc.)
  - `invoice_dt`: DateField
  - `fy_id` (FK): → `FinancialYear` (backend-only)
  - `working_year`: CharField(9), db_indexed (e.g., "2025-26")
  - `cust_id` (FK): → `MstCust`
  - `transport_id` (FK): → `MstTransport`
  - `ref_order_id` (FK): → `TrnSlsOrdHed`, nullable (reference sales order)
  - `delivery_add`: TextField (delivery address)
  - `taxable_val`: DecimalField(12, 2), default=0
  - `pkg_fwd_amt`: DecimalField(12, 2), default=0 (packing/forwarding)
  - `freight_amt`: DecimalField(12, 2), default=0
  - `oth_charges`: DecimalField(12, 2), default=0
  - `cgst_amt`: DecimalField(12, 2), default=0
  - `sgst_amt`: DecimalField(12, 2), default=0
  - `igst_amt`: DecimalField(12, 2), default=0
  - `round_off`: DecimalField(6, 2), default=0 (range: -1 to +1)
  - `total_amt`: DecimalField(12, 2), default=0
  - `remarks`: TextField, nullable
  - `created_at`: DateTimeField (auto_now_add)
  - `updated_at`: DateTimeField (auto_now)
  - `created_by_id` (FK): → `User`, nullable
  - `updated_by_id` (FK): → `User`, nullable

**Constraints**:
- UNIQUE(invoice_no, fy_id)
- CHECK: taxable_val ≥ 0
- CHECK: pkg_fwd_amt ≥ 0
- CHECK: freight_amt ≥ 0
- CHECK: oth_charges ≥ 0
- CHECK: cgst_amt ≥ 0
- CHECK: sgst_amt ≥ 0
- CHECK: igst_amt ≥ 0
- CHECK: total_amt ≥ 0
- CHECK: -1 ≤ round_off ≤ 1

**Business Rules**:
- Invoice date must fall within financial year
- invoice_no format: SI- plus digits (auto-incremented per FY)

**Related Models**:
- → `FinancialYear` (fy_id)
- → `MstCust` (cust_id)
- → `MstTransport` (transport_id)
- → `TrnSlsOrdHed` (ref_order_id)
- → `User` (created_by_id, updated_by_id)
- ← `TrnSlsDtl1` (invoice_id)

---

#### `TrnSlsDtl1`
Sales invoice detail line (one product per line).
- **Table**: `TrnSlsDtl1`
- **Primary Key**: `dtl1_id` (AutoField)
- **Columns**:
  - `dtl1_id`: PK (AUTO_INCREMENT)
  - `invoice_id` (FK): → `TrnSlsHed` (CASCADE)
  - `order_dtl1_id` (FK): → `TrnSlsOrdDtl1`, nullable (ref to sales order line)
  - `prod_id` (FK): → `MstProd`
  - `pkg_style_id` (FK): → `MstPkgStyle`
  - `quantity`: DecimalField(14, QTY_DECIMAL_PLACES) (qty in Lacs)
  - `rate`: DecimalField(12, 4) (price per unit)
  - `taxable_amt`: DecimalField(12, 2), default=0
  - `gst_type`: CharField(20), choices: [CGST_SGST, IGST, EXEMPTED]
  - `gst_per`: DecimalField(5, 2) (GST percentage: 0-100)
  - `cgst_amt`: DecimalField(12, 2), default=0
  - `sgst_amt`: DecimalField(12, 2), default=0
  - `igst_amt`: DecimalField(12, 2), default=0
  - `prod_amt`: DecimalField(12, 2), default=0

**Constraints**:
- UNIQUE(invoice_id, order_dtl1_id) when order_dtl1_id NOT NULL
- UNIQUE(invoice_id, prod_id, pkg_style_id) when order_dtl1_id IS NULL
- CHECK: quantity > 0
- CHECK: rate > 0
- CHECK: taxable_amt ≥ 0
- CHECK: 0 ≤ gst_per ≤ 100
- CHECK: gst_type in GST_TYPE_IDS

**Business Rules**:
- Packing style must belong to product type
- If linked to sales order line (order_dtl1_id):
  - Product must match sales order line product
  - Packing style must match sales order line packing style
  - Customer must be same as invoice customer
- GST validation:
  - IGST lines: no CGST or SGST
  - CGST+SGST lines: no IGST
  - Exempted lines: zero GST amounts

**Related Models**:
- → `TrnSlsHed` (invoice_id)
- → `TrnSlsOrdDtl1` (order_dtl1_id)
- → `MstProd` (prod_id)
- → `MstPkgStyle` (pkg_style_id)
- ← `TrnSlsDtl2` (invoice_dtl1_id)

---

#### `TrnSlsDtl2`
Sales invoice batch allocation line (links to log sheet).
- **Table**: `TrnSlsDtl2`
- **Primary Key**: `dtl2_id` (AutoField)
- **Columns**:
  - `dtl2_id`: PK (AUTO_INCREMENT)
  - `invoice_dtl1_id` (FK): → `TrnSlsDtl1` (CASCADE)
  - `logsheet_id` (FK): → `TrnLogSheet` (PROTECT)
  - `batch_qty`: DecimalField(14, QTY_DECIMAL_PLACES) (qty in Lacs)

**Constraints**:
- UNIQUE(invoice_dtl1_id, logsheet_id)
- CHECK: batch_qty > 0

**Business Rules**:
- Log sheet product must match invoice line product
- Log sheet customer must match invoice customer
- Links invoice lines to specific production batches for traceability

**Related Models**:
- → `TrnSlsDtl1` (invoice_dtl1_id)
- → `TrnLogSheet` (logsheet_id)

---

## Inventory Models

### Customer Monthly Inventory (Legacy)

#### `InvCustMonthlyStock`
Monthly snapshot of customer inventory (opening/receipt/issue).
- **Table**: `InvCustMonthlyStock`
- **Primary Key**: `inv_mth_id` (AutoField)
- **Columns**:
  - `inv_mth_id`: PK (AUTO_INCREMENT)
  - `cust_prod_id` (FK): → `MstCustProd` (CASCADE)
  - `year`: PositiveSmallIntegerField
  - `month`: PositiveSmallIntegerField (1-12)
  - `opening_qty_lac`: DecimalField(12, 2), default=0 (opening qty in Lacs)
  - `receipt_qty_lac`: DecimalField(12, 2), default=0 (stock supplied during month)
  - `issue_qty_lac`: DecimalField(12, 2), default=0 (stock consumed during month)
  - `remarks`: CharField(300), nullable

**Constraints**:
- UNIQUE(cust_prod_id, year, month)
- CHECK: 1 ≤ month ≤ 12
- CHECK: opening_qty_lac ≥ 0
- CHECK: receipt_qty_lac ≥ 0
- CHECK: issue_qty_lac ≥ 0
- Business Rule: opening_qty + receipt_qty ≥ issue_qty

**Business Rules**:
- No longer edited from main app UI; retained in Django admin for historical reference
- Closing qty calculated: opening + receipt - issue
- Operational batch balances maintained in `InventoryStock`

**Related Models**:
- → `MstCustProd` (cust_prod_id)

---

### Batch-Level Stock Ledger

#### `InventoryStock`
Centralized batch-level stock ledger (customer × product/item × batch).
- **Table**: `InventoryStock`
- **Primary Key**: `inv_id` (AutoField)
- **Columns**:
  - `inv_id`: PK (AUTO_INCREMENT)
  - `cust_id` (FK): → `MstCust` (PROTECT)
  - `prod_id` (FK): → `MstProd`, nullable (exactly one of product/item set)
  - `item_id` (FK): → `MstItem`, nullable (exactly one of product/item set)
  - `item_type_id` (FK): → `MstProdCat` (FG/RM/PM)
  - `batch_no`: CharField(100), default='' (batch identifier)
  - `mfg_date`: DateField, nullable
  - `exp_date`: DateField, nullable
  - `qty`: DecimalField(12, 3), default=0 (available quantity)
  - `reserved_qty`: DecimalField(12, 3), default=0 (reserved for allocation, not yet decremented)
  - `last_trn_date`: DateField, nullable (last transaction date)
  - `last_trn_type`: CharField(30), blank=True (type of last transaction)
  - `ref_doc_id`: PositiveIntegerField, nullable (reference document ID)
  - `ref_doc_type`: CharField(30), blank=True (reference document type)
  - `is_closed`: BooleanField, default=False, db_indexed (True when qty = 0 or year-end closed)
  - `opened_in_fy` (FK): → `FinancialYear`, nullable (FY when first posted)

**Constraints**:
- CHECK: (product NOT NULL AND item IS NULL) OR (product IS NULL AND item NOT NULL)

**Business Rules**:
- Exactly one of product or item must be set (product for FG, item for RM/PM)
- Multiple rows can share same customer + SKU + batch when older lines are closed
- At most one **open** row per (customer, product/item, batch) combination
- **Closing**: When qty reaches zero (operational close) OR at year-end FY close
- Year-end close: Rows opened in that FY are finalized (marked as_closed)
- New inward/opening stock creates new open row if only closed rows exist for batch
- reserved_qty reserved for future allocation but not yet decremented from available qty

**Related Models**:
- → `MstCust` (cust_id)
- → `MstProd` (prod_id)
- → `MstItem` (item_id)
- → `MstProdCat` (item_type_id)
- → `FinancialYear` (opened_in_fy)

---

### Stock Adjustment/Opening

#### `TrnStkAdjHed`
Stock adjustment or opening balance document header.
- **Table**: `TrnStkAdjHed`
- **Primary Key**: `stk_adj_id` (AutoField)
- **Columns**:
  - `stk_adj_id`: PK (AUTO_INCREMENT)
  - `stk_adj_dt`: DateField
  - `cust_id` (FK): → `MstCust` (PROTECT)
  - `stk_adj_type`: CharField(1), choices: ['O' (Opening), 'A' (Adjustment)]
  - `item_type_id` (FK): → `MstItemType`
  - `remarks`: TextField, nullable

**Related Models**:
- → `MstCust` (cust_id)
- → `MstItemType` (item_type_id)
- ← `TrnStkAdjDtl1` (stk_adj_id)

---

#### `TrnStkAdjDtl1`
Stock adjustment detail line (one product or item).
- **Table**: `TrnStkAdjDtl1`
- **Primary Key**: `dtl1_id` (AutoField)
- **Columns**:
  - `dtl1_id`: PK (AUTO_INCREMENT)
  - `stk_adj_id` (FK): → `TrnStkAdjHed` (CASCADE)
  - `prod_id` (FK): → `MstProd`, nullable (exactly one of product/item set)
  - `item_id` (FK): → `MstItem`, nullable (exactly one of product/item set)
  - `quantity`: DecimalField(12, 3), default=0 (total of batch quantities)
  - `remarks`: CharField(20), nullable

**Constraints**:
- CHECK: (product NOT NULL AND item IS NULL) OR (product IS NULL AND item NOT NULL)
- UNIQUE(header, product) when product set
- UNIQUE(header, item) when item set

**Related Models**:
- → `TrnStkAdjHed` (stk_adj_id)
- → `MstProd` (prod_id)
- → `MstItem` (item_id)
- ← `TrnStkAdjDtl2` (stk_adj_dtl1_id)

---

#### `TrnStkAdjDtl2`
Stock adjustment batch detail (batch-level quantities).
- **Table**: `TrnStkAdjDtl2`
- **Primary Key**: `dtl2_id` (AutoField)
- **Columns**:
  - `dtl2_id`: PK (AUTO_INCREMENT)
  - `stk_adj_dtl1_id` (FK): → `TrnStkAdjDtl1` (CASCADE)
  - `batch_no`: CharField(100)
  - `mfg_date`: DateField, nullable
  - `exp_date`: DateField, nullable
  - `batch_qty`: DecimalField(12, 3) (quantity for this batch)

**Related Models**:
- → `TrnStkAdjDtl1` (stk_adj_dtl1_id)

---

## Relationships Diagram

```
MASTERS HIERARCHY:
═════════════════

Department
    └── Section
            ├── Machine
            └── OperatorSection (M2M via Operator)

State
    ├── Customer
    │   ├── CustomerProduct
    │   ├── BomRmHed
    │   ├── BomPmHed
    │   ├── InventoryStock (via cust_id)
    │   └── StockAdjustment (via cust_id)
    └── Supplier

ProductCategory
    ├── ItemType
    │   ├── Product
    │   ├── Item
    │   ├── PkgStyle
    │   └── StockAdjustment (via item_type_id)
    ├── Product
    ├── Item
    └── InventoryStock (via item_type_id)

Product
    ├── Color (first, second)
    ├── ItemType
    ├── UOM
    └── InventoryStock (via prod_id)

Item
    ├── ItemType
    ├── UOM
    └── InventoryStock (via item_id)

UOM
    ├── Product
    ├── Item
    └── BomDetail (RM/PM)

BomRmHed
    ├── Customer
    ├── Product
    ├── Shape
    ├── Color
    ├── CoatType
    ├── Capsule
    └── BomRmDtl
        ├── PdnStage
        ├── Item
        └── UOM

BomPmHed
    ├── Customer
    ├── Product
    ├── PkgStyle
    └── BomPmDtl
        ├── PdnStage
        ├── Item
        └── UOM

FinancialYear
    ├── Inward (TrnInwHed)
    ├── SalesOrder (TrnSlsOrdHed)
    ├── SalesInvoice (TrnSlsHed)
    └── InventoryStock (via opened_in_fy)


TRANSACTION HIERARCHY:
═════════════════════

Inward (TrnInwHed)
    ├── FinancialYear
    ├── Customer
    ├── Supplier
    ├── Transport
    ├── InwardDetail1 (TrnInwDtl1)
    │   ├── Item
    │   └── UOM
    └── InwardDetail2 (TrnInwDtl2) [only if item.maintain_batch = Y]
        ├── Item
        └── Product

SalesOrder (TrnSlsOrdHed)
    ├── FinancialYear
    ├── Customer
    ├── SalesOrderDetail1 (TrnSlsOrdDtl1)
    │   ├── Product
    │   └── PkgStyle
    ├── SalesOrderDetail2 (TrnSlsOrdDtl2)
    │   └── Product
    └── BatchHed (TrnBatchHed)
        ├── Product
        └── BatchDtl (TrnBatchDtl)
            └── LogSheet (TrnLogSheet)
                ├── Section
                ├── Customer
                ├── Product
                ├── PkgCont (TrnPkgCont)
                │   ├── Operator (Contractor)
                │   └── PkgStyle
                └── SalesInvoiceBatch (TrnSlsDtl2)
                    └── SalesInvoiceLine (TrnSlsDtl1)

SalesInvoice (TrnSlsHed)
    ├── FinancialYear
    ├── Customer
    ├── Transporter
    ├── SalesOrder [Reference - optional]
    ├── User (CreatedBy, UpdatedBy)
    ├── SalesInvoiceLine (TrnSlsDtl1)
    │   ├── Product
    │   ├── PkgStyle
    │   └── SalesOrderLine [Reference - optional]
    └── SalesInvoiceBatch (TrnSlsDtl2)
        └── LogSheet (TrnLogSheet)


INVENTORY HIERARCHY:
════════════════════

MonthlyStock (InvCustMonthlyStock)
    ├── CustomerProduct (legacy reference only)
    └── [Now superseded by InventoryStock]

InventoryStock (Batch-level ledger)
    ├── Customer
    ├── Product [XOR Item]
    ├── Item [XOR Product]
    ├── ProductCategory
    ├── FinancialYear (opened_in_fy)
    └── [Tracks all stock movements]

StockAdjustment (TrnStkAdjHed)
    ├── Customer
    ├── ItemType
    └── StockAdjustmentLine (TrnStkAdjDtl1)
        ├── Product [XOR Item]
        ├── Item [XOR Product]
        └── StockAdjustmentBatch (TrnStkAdjDtl2)
            └── [Batch-level quantities]
```

---

## Database Constraints

### Data Type Standards
- **Quantities**: `DecimalField(14, 3)` for items, `DecimalField(10, 2)` for Lacs
- **Prices/Amounts**: `DecimalField(12, 2)`
- **Percentages**: `DecimalField(5, 2)` (0-100%)
- **Batch Codes**: 3-char uppercase (e.g., "ABC")
- **Register/GRN**: Format R-xxxxx or RM-xxxxx / PM-xxxxx

### Key Immutability Rules
- `MstCust.short_name` → immutable after use in transactions
- `MstProd.prod_name` → UNIQUE, immutable after use
- `MstItem.item_name` → UNIQUE, immutable after use
- `TrnInwHed.register_no` → UNIQUE, immutable after creation

### Business Rule Enforcement
1. **Batch Tracking**: Only enforced when `MstItem.maintain_batch = 'Y'`
2. **Manufacturing/Expiry Dates**: Cascade depends on item flags
3. **Financial Year Assignment**: Automatic backend assignment on save
4. **GST Calculation**: CGST+SGST for domestic (state), IGST for other states or exempted

### Cascading Deletes
- `MstCust` → `MstCustProd` (CASCADE)
- `TrnSlsOrdHed` → `TrnSlsOrdDtl1`, `TrnSlsOrdDtl2`, `TrnBatchHed` (CASCADE)
- `TrnBatchHed` → `TrnBatchDtl` (CASCADE)
- `TrnInwHed` → `TrnInwDtl1`, `TrnInwDtl2` (CASCADE)
- `TrnSlsHed` → `TrnSlsDtl1` (CASCADE)
- `TrnSlsDtl1` → `TrnSlsDtl2` (CASCADE)
- `MstBomRmHed` → `MstBomRmDtl` (CASCADE)
- `MstBomPmHed` → `MstBomPmDtl` (CASCADE)

### Protecting Constraints
- Most FK relationships use `on_delete=models.PROTECT` to prevent orphaning
- Exceptions: Customer products and transaction details (CASCADE for parent transactions)

---

## Key Business Workflows

### Inward Receipt Workflow
1. Create `TrnInwHed` with supplier, GRN number, invoice details
2. Create `TrnInwDtl1` lines for each item
3. If `item.maintain_batch = 'Y'`, create `TrnInwDtl2` batch lines
4. FY automatically assigned; register_no auto-generated or provided

### Sales Order Workflow
1. Create `TrnSlsOrdHed` with customer order details
2. Create `TrnSlsOrdDtl1` lines (product + packing style)
3. Create `TrnSlsOrdDtl2` for dispatch schedule (optional)
4. Create `TrnBatchHed` and `TrnBatchDtl` for batch allocation
5. Create `TrnLogSheet` for production tracking
   - Single-layer: 1 log sheet per batch
   - Double-layer: 2 log sheets per batch (one per color slot)

### BOM Management Workflow
1. Create `MstBomRmHed` (RM spec) or `MstBomPmHed` (PM spec)
2. Add detail lines via `MstBomRmDtl` or `MstBomPmDtl`
3. Each line references a production stage and item
4. BOM can be locked (`is_locked = True`) to prevent modification

---

**Document Version**: 1.0  
**Last Updated**: May 14, 2026  
**Database**: MySQL 8.0+  
**ORM**: Django ORM
