"""
masters/models.py

Models for the Masters module.

MstDepartment:
    Department master table. Single source of truth for all departments.
    Populated once via: python manage.py seed_departments

MstSection:
    Stores sections belonging to a department.
    department FK → MstDepartment.
"""

from datetime import date

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class MstDepartment(models.Model):
    """
    Table: MstDepartment
    Master list of all departments in the organisation.
    """

    dept_id = models.AutoField(primary_key=True)

    dept_name = models.CharField(
        max_length=150,
        unique=True,
        verbose_name='Department Name'
    )

    class Meta:
        db_table            = 'MstDepartment'
        verbose_name        = 'Department'
        verbose_name_plural = 'Departments'
        ordering            = ['dept_name']

    def __str__(self):
        return self.dept_name


class MstSection(models.Model):
    """
    Table: MstSection
    Stores sections belonging to a department.

    Constraints:
        - section_name alone must be unique.
        - The combination of (section_name, department) must be unique.
    """

    section_id = models.AutoField(primary_key=True)

    section_name = models.CharField(
        max_length=150,
        unique=True,
        verbose_name='Section Name'
    )

    department = models.ForeignKey(
        MstDepartment,
        on_delete=models.PROTECT,
        db_column='dept_id',
        verbose_name='Department'
    )

    class Meta:
        db_table     = 'MstSection'
        verbose_name = 'Section'
        verbose_name_plural = 'Sections'
        constraints  = [
            models.UniqueConstraint(
                fields=['section_name', 'department'],
                name='unique_section_per_department'
            )
        ]
        ordering = ['department', 'section_name']

    def __str__(self):
        return f"{self.section_name} ({self.department.dept_name})"


class MstMachine(models.Model):
    """
    Table: MstMachine
    Stores machine records linked to a section (and indirectly a department).
    """

    machine_id = models.AutoField(primary_key=True)

    machine_name = models.CharField(
        max_length=200,
        unique=True,
        verbose_name='Machine Name'
    )

    section = models.ForeignKey(
        MstSection,
        on_delete=models.PROTECT,
        db_column='section_id',
        verbose_name='Section'
    )

    make = models.CharField(max_length=150, blank=True, null=True, verbose_name='Make')
    model_no = models.CharField(max_length=100, blank=True, null=True, verbose_name='Model No.')
    machine_no = models.CharField(max_length=100, blank=True, null=True, verbose_name='Machine No.')
    capacity = models.CharField(max_length=100, blank=True, null=True, verbose_name='Capacity')

    installed_date = models.DateField(
        blank=True,
        null=True,
        verbose_name='Installation Date'
    )

    remarks = models.TextField(blank=True, null=True, verbose_name='Remarks')

    class Meta:
        db_table     = 'MstMachine'
        verbose_name = 'Machine'
        verbose_name_plural = 'Machines'
        ordering = ['machine_name']

    def __str__(self):
        return self.machine_name


class MstOperator(models.Model):
    """
    Table: mstoperator
    Operator master; linked to one or more sections via MstOperatorSection.
    """

    opt_id = models.AutoField(primary_key=True, db_column='Opt_id')
    opt_name = models.CharField(
        max_length=30,
        unique=True,
        db_column='Opt_name',
        verbose_name='Operator name',
    )
    designation = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        db_column='Designation',
        verbose_name='Designation',
    )

    class Meta:
        db_table = 'mstoperator'
        verbose_name = 'Operator'
        verbose_name_plural = 'Operators'
        ordering = ['opt_name']

    def __str__(self):
        return self.opt_name


class MstOperatorSection(models.Model):
    """
    Table: MstOperatorSection
    Many-to-many link: one operator may work in multiple sections.
    """

    operator = models.ForeignKey(
        MstOperator,
        on_delete=models.CASCADE,
        db_column='Opt_id',
        related_name='section_links',
        verbose_name='Operator',
    )
    section = models.ForeignKey(
        MstSection,
        on_delete=models.PROTECT,
        db_column='section_id',
        related_name='operator_section_links',
        verbose_name='Section',
    )

    class Meta:
        db_table = 'MstOperatorSection'
        verbose_name = 'Operator section'
        verbose_name_plural = 'Operator sections'
        constraints = [
            models.UniqueConstraint(
                fields=['operator', 'section'],
                name='uniq_mst_operator_section',
            )
        ]

    def __str__(self):
        return f'{self.operator.opt_name} @ {self.section.section_name}'


class MstUom(models.Model):
    """
    Table: MstUom
    Unit of Measurement master.
    """
    uom_id = models.AutoField(primary_key=True)

    uom_name = models.CharField(
        max_length=150,
        unique=True,
        verbose_name='UOM Name'
    )

    short_name = models.CharField(
        max_length=3,
        unique=True,
        verbose_name='Abbreviation'
    )

    class Meta:
        db_table            = 'MstUom'
        verbose_name        = 'Unit of Measurement'
        verbose_name_plural = 'Units of Measurement'
        ordering            = ['uom_name']

    def __str__(self):
        return f"{self.uom_name} ({self.short_name})"


# ═══════════════════════════════════════════════════════════════
#  PRODUCT ATTRIBUTE MODELS
# ═══════════════════════════════════════════════════════════════

class MstColor(models.Model):
    color_id   = models.AutoField(primary_key=True)
    color_name = models.CharField(max_length=150, unique=True, verbose_name='Colour Name')

    class Meta:
        db_table            = 'MstColor'
        verbose_name        = 'Colour'
        verbose_name_plural = 'Colours'
        ordering            = ['color_name']

    def __str__(self):
        return self.color_name


class MstShape(models.Model):
    shape_id   = models.AutoField(primary_key=True)
    shape_name = models.CharField(max_length=150, unique=True, verbose_name='Shape Name')

    class Meta:
        db_table            = 'MstShape'
        verbose_name        = 'Product Shape'
        verbose_name_plural = 'Product Shapes'
        ordering            = ['shape_name']

    def __str__(self):
        return self.shape_name


class MstCoatType(models.Model):
    coating_id   = models.AutoField(primary_key=True)
    coating_name = models.CharField(max_length=150, unique=True, verbose_name='Coating Type')

    class Meta:
        db_table            = 'MstCoatType'
        verbose_name        = 'Coating Type'
        verbose_name_plural = 'Coating Types'
        ordering            = ['coating_name']

    def __str__(self):
        return self.coating_name


class MstProdCat(models.Model):
    prod_cat_id   = models.CharField(max_length=2, primary_key=True, verbose_name='Category ID')
    prod_cat_name = models.CharField(max_length=150, unique=True, verbose_name='Category Name')

    class Meta:
        db_table            = 'MstProdCat'
        verbose_name        = 'Product Category'
        verbose_name_plural = 'Product Categories'
        ordering            = ['prod_cat_name']

    def __str__(self):
        return f"{self.prod_cat_id} – {self.prod_cat_name}"


class MstCapsule(models.Model):
    capsule_id    = models.AutoField(primary_key=True)
    # capsule_name is always derived from capsule_size + capsule_color.
    # It is recomputed in save() (L2) so that writes via admin, shell, or
    # migrations never produce a name that diverges from the component fields.
    capsule_name  = models.CharField(max_length=200, unique=True, verbose_name='Capsule Name')
    capsule_size  = models.CharField(max_length=100, verbose_name='Capsule Size')
    capsule_color = models.CharField(max_length=100, verbose_name='Capsule Colour')

    class Meta:
        db_table            = 'MstCapsule'
        verbose_name        = 'Capsule Type'
        verbose_name_plural = 'Capsule Types'
        ordering            = ['capsule_name']
        constraints = [
            # M4: DB-level enforcement of the size+color composite uniqueness.
            # CapsuleForm.clean() gives a friendly pre-check; this constraint
            # is the last line of defence against concurrent duplicates.
            models.UniqueConstraint(
                fields=['capsule_size', 'capsule_color'],
                name='unique_capsule_size_color',
            )
        ]

    def save(self, *args, **kwargs):
        # L2: always recompute capsule_name from its components so that writes
        # via Django admin, shell, or management commands stay consistent.
        self.capsule_name = f"{self.capsule_size} {self.capsule_color}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.capsule_name


# ═══════════════════════════════════════════════════════════════
#  Logistics MODEL
# ═══════════════════════════════════════════════════════════════

class MstState(models.Model):
    """
    Table: MstState
    Indian state master with GST codes.
    """
    state_id = models.AutoField(primary_key=True)

    state_name = models.CharField(
        max_length=150,
        unique=True,
        verbose_name='State Name'
    )

    gst_code = models.CharField(
        max_length=10,
        unique=True,
        verbose_name='GST Code'
    )

    class Meta:
        db_table            = 'MstState'
        verbose_name        = 'State'
        verbose_name_plural = 'States'
        ordering            = ['state_name']

    def __str__(self):
        return f"{self.state_name} ({self.gst_code})"


class MstTransport(models.Model):
    transport_id   = models.AutoField(primary_key=True)
    transport_name = models.CharField(max_length=200, unique=True, verbose_name='Transporter Name')

    class Meta:
        db_table            = 'MstTransport'
        verbose_name        = 'Transporter'
        verbose_name_plural = 'Transporters'
        ordering            = ['transport_name']

    def __str__(self):
        return self.transport_name


class MstPdnStage(models.Model):
    stage_id   = models.AutoField(primary_key=True)
    stage_name = models.CharField(max_length=150, unique=True, verbose_name='Production Stage')

    class Meta:
        db_table            = 'MstPdnStage'
        verbose_name        = 'Production Stage'
        verbose_name_plural = 'Production Stages'
        ordering            = ['stage_name']

    def __str__(self):
        return self.stage_name


class MstItemType(models.Model):
    item_type_id   = models.AutoField(primary_key=True)
    item_category  = models.ForeignKey(
        MstProdCat,
        on_delete=models.PROTECT,
        db_column='prod_cat_id',
        verbose_name='Item Category'
    )
    item_type_name = models.CharField(max_length=150, unique=True, verbose_name='Item Type Name')

    class Meta:
        db_table            = 'MstItemType'
        verbose_name        = 'Item Type'
        verbose_name_plural = 'Item Types'
        ordering            = ['item_type_name']

    def __str__(self):
        return self.item_type_name


class MstPkgStyle(models.Model):
    """
    Table: MstPkgStyle
    Packing style master. Each style has a numeric value and is linked
    to an item type (e.g. Carton, Shipper).

    Constraints:
        - (pkg_style_name + pkg_type) must be unique.
        - pkg_style_value must be > 0 (enforced in form clean).
    """

    pkg_style_id    = models.AutoField(primary_key=True)

    pkg_style_name  = models.CharField(
        max_length=150,
        verbose_name='Packing Style Name'
    )

    pkg_style_value = models.PositiveIntegerField(
        verbose_name='Packing Style Value'
    )

    pkg_type = models.ForeignKey(
        MstItemType,
        on_delete=models.PROTECT,
        db_column='pkg_type_id',
        verbose_name='Packing Type (Item Type)'
    )

    class Meta:
        db_table            = 'MstPkgStyle'
        verbose_name        = 'Packing Style'
        verbose_name_plural = 'Packing Styles'
        ordering            = ['pkg_style_name']
        constraints = [
            models.UniqueConstraint(
                fields=['pkg_style_name', 'pkg_type'],
                name='unique_pkgstyle_per_itemtype'
            )
        ]

    def __str__(self):
        return f"{self.pkg_style_name} ({self.pkg_type.item_type_name})"

class MstExpGroup(models.Model):
    exp_group   = models.CharField(primary_key=True, max_length=20, unique=True, verbose_name='Production Stage')

    class Meta:
        db_table            = 'MstExpGroup'
        verbose_name        = 'Expenses Group'
        verbose_name_plural = 'Expenses Group'
        ordering            = ['exp_group']

    def __str__(self):
        return self.exp_group


class MstExpenses(models.Model):
    """
    Table: MstExpenses
    Master list of expense categories (Salary, Transport, etc.).

    Constraints:
        - exp_name must be unique (case-insensitive enforced in form).
    """

    exp_id = models.AutoField(primary_key=True)

    exp_name = models.CharField(
        max_length=200,
        unique=True,
        verbose_name='Expense Name'
    )
    exp_group= models.ForeignKey(
        MstExpGroup, on_delete=models.PROTECT, db_column='exp_group',
        related_name='expenses_group', verbose_name=''
    )


    class Meta:
        db_table            = 'MstExpenses'
        verbose_name        = 'Expense'
        verbose_name_plural = 'Expenses'
        ordering            = ['exp_name']

    def __str__(self):
        return self.exp_name


class MstProd(models.Model):
    """
    Table: MstProd
    Master product register.
 
    Business rules enforced here or in ProductForm:
    - prod_name must be unique (form clean + DB unique=True)
    - generic_name must not be blank
    - prod_type FK → MstItemType; prod_category is derived from prod_type
    - first_color / second_color enabled only when tablet_layer == 'Double'
    - first_color != second_color when both are set
    - image_path stores the relative filesystem path; the file lives under
      MEDIA_ROOT/products/
    """
 
    LAYER_SINGLE = 'Single'
    LAYER_DOUBLE = 'Double'
    LAYER_CHOICES = [
        (LAYER_SINGLE, 'Single'),
        (LAYER_DOUBLE, 'Double'),
    ]
 
    prod_id = models.AutoField(primary_key=True)
 
    prod_name = models.CharField(
        max_length=200,
        unique=True,
        verbose_name='Product Name',
    )
 
    generic_name = models.TextField(
        verbose_name='Generic Name',
    )
 
    prod_type = models.ForeignKey(
        'MstItemType',
        on_delete=models.PROTECT,
        db_column='item_type_id',
        verbose_name='Product Type',
        related_name='products',
    )
 
    # prod_category is stored explicitly so queries/reports can filter
    # by category without always joining through MstItemType.
    prod_category = models.ForeignKey(
        'MstProdCat',
        on_delete=models.PROTECT,
        db_column='prod_cat_id',
        verbose_name='Product Category',
        related_name='products',
    )
 
    uom = models.ForeignKey(
        'MstUom',
        on_delete=models.PROTECT,
        db_column='uom_id',
        verbose_name='Unit of Measurement',
        related_name='products',
    )
 
    hsn_code = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='HSN Code',
    )
 
    tablet_layer = models.CharField(
        max_length=10,
        choices=LAYER_CHOICES,
        default=LAYER_SINGLE,
        verbose_name='Tablet Layer Type',
    )
 
    first_color = models.ForeignKey(
        'MstColor',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column='first_color_id',
        related_name='first_color_products',
        verbose_name='First Layer Colour',
    )
 
    second_color = models.ForeignKey(
        'MstColor',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_column='second_color_id',
        related_name='second_color_products',
        verbose_name='Second Layer Colour',
    )
 
    # Stores relative path under MEDIA_ROOT, e.g. "products/paracetamol.jpg"
    image_path = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name='Product Image Path',
    )
 
    class Meta:
        db_table            = 'MstProd'
        verbose_name        = 'Product'
        verbose_name_plural = 'Products'
        ordering            = ['prod_name']
 
    def __str__(self):
        return self.prod_name
    
# ═══════════════════════════════════════════════════════════════
#  MstItem MODEL 
# ═══════════════════════════════════════════════════════════════
class MstItem(models.Model):
    """
    Table: MstItem
    Raw material / packing material item master.

    Business rules:
    - item_name must be unique (enforced in form + DB unique=True).
    - item_category is derived from item_type.item_category and stored
      explicitly to avoid join overhead in reports.
    - maintain_batch / mfg_date / exp_date are single-char Y/N flags.
      Cascade: mfg_date can only be Y when maintain_batch=Y.
               exp_date can only be Y when mfg_date=Y.
    - max_level >= min_level when both are provided (form clean).
    - last_purchase_rate >= 0, default 0.
    - sample_qty >= 0, default 0 — deducted from each inward receipt when posting to inventory.
    - uom FK → MstUom (required on the item form; BOM detail lines copy UOM from the item).
    """

    YN_CHOICES = [('Y', 'Yes'), ('N', 'No')]

    item_id = models.AutoField(primary_key=True)

    item_name = models.CharField(
        max_length=200, unique=True, verbose_name='Item Name',
    )

    item_type = models.ForeignKey(
        'MstItemType',
        on_delete=models.PROTECT,
        db_column='item_type_id',
        verbose_name='Item Type',
        related_name='items',
    )

    # Stored explicitly — mirrors item_type.item_category for fast filtering.
    item_category = models.ForeignKey(
        'MstProdCat',
        on_delete=models.PROTECT,
        db_column='item_cat_id',
        verbose_name='Item Category',
        related_name='items',
    )

    hsn_code = models.CharField(
        max_length=50, blank=True, null=True, verbose_name='HSN Code',
    )

    min_level = models.DecimalField(
        max_digits=10, decimal_places=3,
        blank=True, null=True, verbose_name='Minimum Stock Level',
    )

    max_level = models.DecimalField(
        max_digits=10, decimal_places=3,
        blank=True, null=True, verbose_name='Maximum Stock Level',
    )

    maintain_batch = models.CharField(
        max_length=1, choices=YN_CHOICES, default='N',
        verbose_name='Maintain Batches',
    )

    mfg_date = models.CharField(
        max_length=1, choices=YN_CHOICES, default='N',
        verbose_name='Manufacturing Date',
    )

    exp_date = models.CharField(
        max_length=1, choices=YN_CHOICES, default='N',
        verbose_name='Expiry Date',
    )

    last_purchase_rate = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=0, verbose_name='Last Purchase Rate',
    )

    sample_qty = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=0,
        verbose_name='Sample qty',
    )

    uom = models.ForeignKey(
        'MstUom',
        on_delete=models.PROTECT,
        db_column='uom_id',
        verbose_name='UOM',
        related_name='items',
        blank=True,
        null=True,
    )

    class Meta:
        db_table            = 'MstItem'
        verbose_name        = 'Item'
        verbose_name_plural = 'Items'
        ordering            = ['item_name']

    def __str__(self):
        return self.item_name
    
# ═══════════════════════════════════════════════════════════════
#  CUSTOMER MODELS — append to masters/models.py
# ═══════════════════════════════════════════════════════════════

class MstCust(models.Model):
    """
    Table: MstCust
    Customer master.

    Business rules:
    - cust_name must be unique (case-insensitive check in form).
    - short_name: unique, no spaces, max 10 chars, uppercase.
      Once referenced in a transaction it becomes immutable
      (enforced in form.clean_short_name via a transaction FK check).
    - address, state are mandatory.
    """

    cust_id = models.AutoField(primary_key=True)

    cust_name = models.CharField(
        max_length=200, unique=True, verbose_name='Customer Name',
    )

    short_name = models.CharField(
        max_length=10, unique=True, verbose_name='Short Name',
    )

    address = models.TextField(verbose_name='Address')

    state = models.ForeignKey(
        'MstState',
        on_delete=models.PROTECT,
        db_column='state_id',
        verbose_name='State',
        related_name='customers',
    )

    pin_code = models.CharField(
        max_length=6, blank=True, null=True, verbose_name='Pin Code',
    )

    landline_no = models.CharField(
        max_length=20, blank=True, null=True, verbose_name='Land Line No.',
    )

    mobile_no = models.CharField(
        max_length=10, blank=True, null=True, verbose_name='Mobile No.',
    )

    email = models.CharField(
        max_length=50, blank=True, null=True, verbose_name='Email ID',
    )

    pan_no = models.CharField(
        max_length=10, blank=True, null=True, verbose_name='PAN No.',
    )

    gst_no = models.CharField(
        max_length=15, blank=True, null=True, verbose_name='GST No.',
    )

    udyam_cert = models.CharField(
        max_length=30, blank=True, null=True, verbose_name='Udyam Certificate',
    )

    class Meta:
        db_table            = 'MstCust'
        verbose_name        = 'Customer'
        verbose_name_plural = 'Customers'
        ordering            = ['cust_name']

    def __str__(self):
        return f"{self.cust_name} ({self.short_name})"


class MstSupplier(models.Model):
    """
    Table: mstSupplier
    Supplier master — same core fields as MstCust, without customer-product links.
    """

    supl_id = models.AutoField(primary_key=True)

    supl_name = models.CharField(
        max_length=200, unique=True, verbose_name='Supplier Name',
    )

    short_name = models.CharField(
        max_length=10,
        unique=True,
        blank=True,
        null=True,
        verbose_name='Short Name',
    )

    address = models.TextField(verbose_name='Address')

    state = models.ForeignKey(
        'MstState',
        on_delete=models.PROTECT,
        db_column='state_id',
        verbose_name='State',
        related_name='suppliers',
    )

    pin_code = models.CharField(
        max_length=6, verbose_name='Pin Code',
    )

    landline_no = models.CharField(
        max_length=10, blank=True, null=True, verbose_name='Land Line No.',
    )

    mobile_no = models.CharField(
        max_length=10, blank=True, null=True, verbose_name='Mobile No.',
    )

    email = models.CharField(
        max_length=150, blank=True, null=True, verbose_name='Email ID',
    )

    pan_no = models.CharField(
        max_length=10, blank=True, null=True, verbose_name='PAN No.',
    )

    gst_no = models.CharField(
        max_length=15, blank=True, null=True, verbose_name='GST No.',
    )

    udyam_cert = models.CharField(
        max_length=30, blank=True, null=True, verbose_name='Udyam Certificate',
    )

    class Meta:
        db_table = 'mstSupplier'
        verbose_name = 'Supplier'
        verbose_name_plural = 'Suppliers'
        ordering = ['supl_name']

    def __str__(self):
        return f"{self.supl_name}" + (f" ({self.short_name})" if self.short_name else "")


class MstCustProd(models.Model):
    """
    Table: MstCustProd
    Products ordered by a customer — one row per product per customer.

    Business rules:
    - (customer + product) must be unique — a product cannot be added
      twice for the same customer.
    - adv_license: Y/N, default N.
    - license_details: mandatory when adv_license = Y.
    - batch_abbr: exactly 3 chars (letters/symbols), mandatory.
    """

    cust_prod_id = models.AutoField(primary_key=True)

    customer = models.ForeignKey(
        MstCust,
        on_delete=models.CASCADE,       # deleting customer removes its products
        db_column='cust_id',
        verbose_name='Customer',
        related_name='cust_products',
    )

    product = models.ForeignKey(
        'MstProd',
        on_delete=models.PROTECT,
        db_column='prod_id',
        verbose_name='Product',
        related_name='cust_products',
    )

    adv_license = models.CharField(
        max_length=1,
        choices=[('Y', 'Yes'), ('N', 'No')],
        default='N',
        verbose_name='Advance License',
    )

    license_details = models.CharField(
        max_length=300, blank=True, null=True, verbose_name='License Details',
    )

    batch_abbr = models.CharField(
        max_length=3, verbose_name='Batch Abbreviation',
    )

    class Meta:
        db_table    = 'MstCustProd'
        verbose_name        = 'Customer Product'
        verbose_name_plural = 'Customer Products'
        ordering            = ['customer', 'product']
        constraints = [
            models.UniqueConstraint(
                fields=['customer', 'product'],
                name='unique_product_per_customer',
            )
        ]

    def __str__(self):
        return f"{self.customer.short_name} — {self.product.prod_name}"

# ═══════════════════════════════════════════════════════════════
#  BOM RELATED MODELS
# ═══════════════════════════════════════════════════════════════
class MstBomRmHed(models.Model):
    spec_id = models.AutoField(primary_key=True)
    spec_name = models.CharField(max_length=300, verbose_name='Specification Name')
    machine = models.ForeignKey(
        MstMachine, on_delete=models.PROTECT, db_column='machine_id',
        related_name='bom_rm_headers', verbose_name='Machine'
    )
    customer = models.ForeignKey(
        MstCust, on_delete=models.PROTECT, db_column='cust_id',
        related_name='bom_rm_headers', verbose_name='Customer'
    )
    product = models.ForeignKey(
        MstProd, on_delete=models.PROTECT, db_column='prod_id',
        related_name='bom_rm_headers', verbose_name='Product'
    )
    no_of_lots = models.DecimalField(max_digits=10, decimal_places=0, verbose_name='No of Lots')
    shape = models.ForeignKey(
        MstShape, on_delete=models.PROTECT, db_column='shape_id',
        related_name='bom_rm_headers', verbose_name='Shape',
        blank=True, null=True
    )
    color = models.ForeignKey(
        MstColor, on_delete=models.PROTECT, db_column='color_id',
        related_name='bom_rm_headers', verbose_name='Colour',
        blank=True, null=True
    )
    coating = models.ForeignKey(
        MstCoatType, on_delete=models.PROTECT, db_column='coating_id',
        related_name='bom_rm_headers', verbose_name='Coating',
        blank=True, null=True
    )
    capsule = models.ForeignKey(
        MstCapsule, on_delete=models.PROTECT, db_column='capsule_id',
        related_name='bom_rm_headers', verbose_name='Capsule',
        blank=True, null=True
    )
    avg_wt = models.PositiveIntegerField(blank=True, null=True, verbose_name='Average Weight')
    batch_size = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Batch size (lakh)',
        help_text='Quantity in lakh (2 decimal places).',
    )
    batch_nos = models.PositiveBigIntegerField(
        verbose_name='Batch nos.',
        help_text='Derived: batch size × 100,000.',
    )
    is_locked = models.BooleanField(default=False, verbose_name='Locked')

    class Meta:
        db_table = 'MstBomRmHed'
        verbose_name = 'BOM RM Header'
        verbose_name_plural = 'BOM RM Headers'
        ordering = ['-spec_id']
        constraints = [
            models.UniqueConstraint(
                fields=['spec_name', 'product'],
                name='unique_bom_rm_specname_product',
            ),
        ]

    def __str__(self):
        return self.spec_name


class MstBomRmDtl(models.Model):
    dtl_id = models.AutoField(primary_key=True)
    spec = models.ForeignKey(
        MstBomRmHed, on_delete=models.CASCADE, db_column='spec_id',
        related_name='items', verbose_name='Specification'
    )
    stage = models.ForeignKey(
        MstPdnStage, on_delete=models.PROTECT, db_column='stage_id',
        related_name='bom_rm_items', verbose_name='Stage'
    )
    item = models.ForeignKey(
        MstItem, on_delete=models.PROTECT, db_column='item_id',
        related_name='bom_rm_items', verbose_name='Item'
    )
    qty = models.DecimalField(max_digits=12, decimal_places=3, verbose_name='Quantity')
    uom = models.ForeignKey(
        MstUom, on_delete=models.PROTECT, db_column='uom_id',
        related_name='bom_rm_items', verbose_name='UOM'
    )

    class Meta:
        db_table = 'MstBomRmDtl'
        verbose_name = 'BOM RM Item'
        verbose_name_plural = 'BOM RM Items'
        ordering = ['spec_id', 'dtl_id']
        constraints = [
            models.UniqueConstraint(
                fields=['spec', 'stage', 'item'],
                name='unique_bom_rm_stage_item_per_spec',
            )
        ]

    def __str__(self):
        return f"{self.spec.spec_name} - {self.item.item_name}"


class MstBomPmHed(models.Model):
    spec_id = models.AutoField(primary_key=True)
    spec_name = models.CharField(max_length=300, verbose_name='Specification Name')
    customer = models.ForeignKey(
        MstCust, on_delete=models.PROTECT, db_column='cust_id',
        related_name='bom_pm_headers', verbose_name='Customer'
    )
    product = models.ForeignKey(
        MstProd, on_delete=models.PROTECT, db_column='prod_id',
        related_name='bom_pm_headers', verbose_name='Product'
    )
    pkg_style = models.ForeignKey(
        MstPkgStyle, on_delete=models.PROTECT, db_column='pkg_style_id',
        related_name='bom_pm_headers', verbose_name='Packing Style'
    )
    batch_size = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Batch size (lakh)',
        help_text='Quantity in lakh (2 decimal places).',
    )
    batch_nos = models.PositiveBigIntegerField(
        verbose_name='Batch nos.',
        help_text='Derived: batch size × 100,000.',
    )
    is_locked = models.BooleanField(default=False, verbose_name='Locked')

    class Meta:
        db_table = 'MstBomPmHed'
        verbose_name = 'BOM PM Header'
        verbose_name_plural = 'BOM PM Headers'
        ordering = ['-spec_id']
        constraints = [
            models.UniqueConstraint(
                fields=['customer', 'product', 'pkg_style'],
                name='unique_bom_pm_customer_product_pkgstyle',
            )
            ,
            models.UniqueConstraint(
                fields=['spec_name', 'product'],
                name='unique_bom_pm_specname_product',
            ),
        ]

    def __str__(self):
        return self.spec_name


class MstBomPmDtl(models.Model):
    dtl_id = models.AutoField(primary_key=True)
    spec = models.ForeignKey(
        MstBomPmHed, on_delete=models.CASCADE, db_column='spec_id',
        related_name='items', verbose_name='Specification'
    )
    stage = models.ForeignKey(
        MstPdnStage, on_delete=models.PROTECT, db_column='stage_id',
        related_name='bom_pm_items', verbose_name='Stage'
    )
    item = models.ForeignKey(
        MstItem, on_delete=models.PROTECT, db_column='item_id',
        related_name='bom_pm_items', verbose_name='Item'
    )
    qty = models.DecimalField(max_digits=12, decimal_places=3, verbose_name='Quantity')
    uom = models.ForeignKey(
        MstUom, on_delete=models.PROTECT, db_column='uom_id',
        related_name='bom_pm_items', verbose_name='UOM'
    )

    class Meta:
        db_table = 'MstBomPmDtl'
        verbose_name = 'BOM PM Item'
        verbose_name_plural = 'BOM PM Items'
        ordering = ['spec_id', 'dtl_id']
        constraints = [
            models.UniqueConstraint(
                fields=['spec', 'stage', 'item'],
                name='unique_bom_pm_stage_item_per_spec',
            )
        ]

    def __str__(self):
        return f"{self.spec.spec_name} - {self.item.item_name}"


# ═══════════════════════════════════════════════════════════════
#  FINANCIAL YEAR (BACKEND ONLY)
# ═══════════════════════════════════════════════════════════════

class FinancialYear(models.Model):
    """
    Table: MstFinYr
    Financial Year master (Apr 1 -> Mar 31).

    Notes:
    - FY assignment is backend-only; users never enter FY fields.
    - MySQL cannot enforce "only one current row" via a partial unique index.
      We enforce it in model validation + rollover utility functions.
    """

    fy_id = models.AutoField(primary_key=True)

    fy_start_year = models.PositiveIntegerField(
        unique=True,
        db_index=True,
        verbose_name='FY Start Year',
        help_text='e.g. 2025 for FY 2025-26',
    )
    fy_end_year = models.PositiveIntegerField(
        verbose_name='FY End Year',
        help_text='e.g. 2026 for FY 2025-26',
    )
    fy_display = models.CharField(
        max_length=9,
        verbose_name='FY Display',
        help_text='Format: "2025-26"',
    )

    start_date = models.DateField(verbose_name='Start Date')
    end_date = models.DateField(verbose_name='End Date')

    is_current = models.BooleanField(default=False, verbose_name='Current')
    is_open = models.BooleanField(default=True, verbose_name='Open')
    is_closed = models.BooleanField(default=False, verbose_name='Closed')

    remarks = models.TextField(blank=True, null=True, verbose_name='Remarks')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'MstFinYr'
        verbose_name = 'Financial Year'
        verbose_name_plural = 'Financial Years'
        ordering = ['-fy_start_year']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(fy_end_year=models.F('fy_start_year') + 1),
                name='mst_finyr_end_year_is_start_plus_1',
            ),
            models.CheckConstraint(
                condition=models.Q(start_date__month=4, start_date__day=1),
                name='mst_finyr_start_date_is_apr_1',
            ),
            models.CheckConstraint(
                condition=models.Q(end_date__month=3, end_date__day=31),
                name='mst_finyr_end_date_is_mar_31',
            ),
            models.CheckConstraint(
                condition=models.Q(start_date__lte=models.F('end_date')),
                name='mst_finyr_start_date_lte_end_date',
            ),
            models.CheckConstraint(
                condition=~(models.Q(is_current=True) & models.Q(is_closed=True)),
                name='mst_finyr_current_not_closed',
            ),
        ]

    def __str__(self):
        return self.fy_display

    def clean(self):
        super().clean()

        if self.fy_start_year and self.fy_end_year and self.fy_end_year != self.fy_start_year + 1:
            raise ValidationError({'fy_end_year': 'FY end year must be start year + 1.'})

        if self.start_date:
            if not (self.start_date.month == 4 and self.start_date.day == 1):
                raise ValidationError({'start_date': 'Start date must be 1-Apr.'})
        if self.end_date:
            if not (self.end_date.month == 3 and self.end_date.day == 31):
                raise ValidationError({'end_date': 'End date must be 31-Mar.'})

        if self.fy_start_year and self.start_date and self.start_date != date(self.fy_start_year, 4, 1):
            raise ValidationError({'start_date': 'Start date must match FY start year (1-Apr of start year).'})
        if self.fy_end_year and self.end_date and self.end_date != date(self.fy_end_year, 3, 31):
            raise ValidationError({'end_date': 'End date must match FY end year (31-Mar of end year).'})

        if self.start_date and self.end_date:
            expected_end = date(self.start_date.year + 1, 3, 31)
            if self.end_date != expected_end:
                raise ValidationError({'end_date': 'End date must be 31-Mar of the year after start date.'})

        # Status coherence
        if self.is_closed and self.is_open:
            raise ValidationError({'is_open': 'Closed FY cannot be marked open.'})
        if self.is_current and self.is_closed:
            raise ValidationError({'is_closed': 'Current FY cannot be marked closed.'})
        if self.is_current and not self.is_open:
            raise ValidationError({'is_open': 'Current FY must be open.'})

        # Critical: current FY cannot be closed before end_date.
        today = timezone.localdate()
        if self.is_current and (self.is_closed or not self.is_open) and self.end_date and today < self.end_date:
            raise ValidationError('Cannot close current FY before end date.')

        # Only one current FY at a time (model-level enforcement).
        if self.is_current:
            qs = FinancialYear.objects.filter(is_current=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError({'is_current': 'Only one Financial Year can be current.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)