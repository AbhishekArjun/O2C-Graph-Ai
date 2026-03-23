import json, sqlite3, os, glob

DATA_DIR = os.path.join(os.path.dirname(__file__), "sap-o2c-data")
DB_PATH  = os.path.join(os.path.dirname(__file__), "o2c.db")

def load_jsonl(folder):
    records = []
    for f in glob.glob(os.path.join(DATA_DIR, folder, "*.jsonl")):
        with open(f) as fh:
            for line in fh:
                s = line.strip()
                if s: records.append(json.loads(s))
    return records

def create_tables(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS sales_order_headers (
        salesOrder TEXT PRIMARY KEY, salesOrderType TEXT,
        salesOrganization TEXT, distributionChannel TEXT,
        soldToParty TEXT, creationDate TEXT, createdByUser TEXT,
        totalNetAmount REAL, overallDeliveryStatus TEXT,
        overallOrdReltdBillgStatus TEXT, transactionCurrency TEXT,
        requestedDeliveryDate TEXT, headerBillingBlockReason TEXT,
        deliveryBlockReason TEXT, incotermsClassification TEXT,
        incotermsLocation1 TEXT, customerPaymentTerms TEXT
    );
    CREATE TABLE IF NOT EXISTS sales_order_items (
        salesOrder TEXT, salesOrderItem TEXT, material TEXT,
        requestedQuantity REAL, requestedQuantityUnit TEXT,
        netAmount REAL, materialGroup TEXT, productionPlant TEXT,
        storageLocation TEXT, PRIMARY KEY (salesOrder, salesOrderItem)
    );
    CREATE TABLE IF NOT EXISTS business_partners (
        businessPartner TEXT PRIMARY KEY, customer TEXT,
        businessPartnerFullName TEXT, businessPartnerName TEXT,
        businessPartnerCategory TEXT, businessPartnerGrouping TEXT,
        creationDate TEXT, businessPartnerIsBlocked INTEGER,
        isMarkedForArchiving INTEGER
    );
    CREATE TABLE IF NOT EXISTS outbound_delivery_headers (
        deliveryDocument TEXT PRIMARY KEY, creationDate TEXT,
        shippingPoint TEXT, overallGoodsMovementStatus TEXT,
        overallPickingStatus TEXT, hdrGeneralIncompletionStatus TEXT,
        headerBillingBlockReason TEXT, deliveryBlockReason TEXT,
        actualGoodsMovementDate TEXT
    );
    CREATE TABLE IF NOT EXISTS billing_documents (
        billingDocument TEXT PRIMARY KEY, billingDocumentType TEXT,
        creationDate TEXT, billingDocumentDate TEXT,
        billingDocumentIsCancelled INTEGER, cancelledBillingDocument TEXT,
        totalNetAmount REAL, transactionCurrency TEXT,
        companyCode TEXT, fiscalYear TEXT,
        accountingDocument TEXT, soldToParty TEXT
    );
    CREATE TABLE IF NOT EXISTS journal_entry_items (
        accountingDocument TEXT, accountingDocumentItem TEXT,
        companyCode TEXT, fiscalYear TEXT, glAccount TEXT,
        referenceDocument TEXT, profitCenter TEXT,
        transactionCurrency TEXT, amountInTransactionCurrency REAL,
        postingDate TEXT, documentDate TEXT, customer TEXT,
        clearingDate TEXT, clearingAccountingDocument TEXT,
        PRIMARY KEY (accountingDocument, accountingDocumentItem)
    );
    CREATE TABLE IF NOT EXISTS payments (
        accountingDocument TEXT, accountingDocumentItem TEXT,
        companyCode TEXT, fiscalYear TEXT, clearingDate TEXT,
        clearingAccountingDocument TEXT, amountInTransactionCurrency REAL,
        transactionCurrency TEXT, customer TEXT, postingDate TEXT,
        glAccount TEXT, PRIMARY KEY (accountingDocument, accountingDocumentItem)
    );
    CREATE TABLE IF NOT EXISTS plants (
        plant TEXT PRIMARY KEY, plantName TEXT,
        salesOrganization TEXT, distributionChannel TEXT, addressId TEXT
    );
    CREATE TABLE IF NOT EXISTS product_descriptions (
        product TEXT PRIMARY KEY, language TEXT, productDescription TEXT
    );
    CREATE TABLE IF NOT EXISTS customer_sales_area (
        customer TEXT, salesOrganization TEXT, distributionChannel TEXT,
        currency TEXT, customerPaymentTerms TEXT,
        incotermsClassification TEXT, incotermsLocation1 TEXT,
        PRIMARY KEY (customer, salesOrganization, distributionChannel)
    );
    CREATE TABLE IF NOT EXISTS graph_edges (
        source_type TEXT, source_id TEXT,
        target_type TEXT, target_id TEXT,
        relationship TEXT,
        PRIMARY KEY (source_type, source_id, target_type, target_id, relationship)
    );
    """)
    conn.commit()

def ingest(conn):
    print("Ingesting sales_order_headers...")
    for r in load_jsonl("sales_order_headers"):
        try:
            conn.execute("INSERT OR REPLACE INTO sales_order_headers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                r.get("salesOrder"), r.get("salesOrderType"), r.get("salesOrganization"),
                r.get("distributionChannel"), r.get("soldToParty"),
                r.get("creationDate"), r.get("createdByUser"),
                float(r.get("totalNetAmount") or 0), r.get("overallDeliveryStatus"),
                r.get("overallOrdReltdBillgStatus"), r.get("transactionCurrency"),
                r.get("requestedDeliveryDate"), r.get("headerBillingBlockReason"),
                r.get("deliveryBlockReason"), r.get("incotermsClassification"),
                r.get("incotermsLocation1"), r.get("customerPaymentTerms")
            ))
        except: pass

    print("Ingesting sales_order_items...")
    for r in load_jsonl("sales_order_items"):
        try:
            conn.execute("INSERT OR REPLACE INTO sales_order_items VALUES (?,?,?,?,?,?,?,?,?)", (
                r.get("salesOrder"), r.get("salesOrderItem"), r.get("material"),
                float(r.get("requestedQuantity") or 0), r.get("requestedQuantityUnit"),
                float(r.get("netAmount") or 0), r.get("materialGroup"),
                r.get("productionPlant"), r.get("storageLocation")
            ))
        except: pass

    print("Ingesting business_partners...")
    for r in load_jsonl("business_partners"):
        try:
            conn.execute("INSERT OR REPLACE INTO business_partners VALUES (?,?,?,?,?,?,?,?,?)", (
                r.get("businessPartner"), r.get("customer"),
                r.get("businessPartnerFullName"), r.get("businessPartnerName"),
                r.get("businessPartnerCategory"), r.get("businessPartnerGrouping"),
                r.get("creationDate"),
                1 if r.get("businessPartnerIsBlocked") else 0,
                1 if r.get("isMarkedForArchiving") else 0
            ))
        except: pass

    print("Ingesting outbound_delivery_headers...")
    for r in load_jsonl("outbound_delivery_headers"):
        try:
            conn.execute("INSERT OR REPLACE INTO outbound_delivery_headers VALUES (?,?,?,?,?,?,?,?,?)", (
                r.get("deliveryDocument"), r.get("creationDate"), r.get("shippingPoint"),
                r.get("overallGoodsMovementStatus"), r.get("overallPickingStatus"),
                r.get("hdrGeneralIncompletionStatus"), r.get("headerBillingBlockReason"),
                r.get("deliveryBlockReason"), r.get("actualGoodsMovementDate")
            ))
        except: pass

    print("Ingesting billing_documents...")
    for r in load_jsonl("billing_document_cancellations"):
        try:
            conn.execute("INSERT OR REPLACE INTO billing_documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
                r.get("billingDocument"), r.get("billingDocumentType"),
                r.get("creationDate"), r.get("billingDocumentDate"),
                1 if r.get("billingDocumentIsCancelled") else 0,
                r.get("cancelledBillingDocument"),
                float(r.get("totalNetAmount") or 0), r.get("transactionCurrency"),
                r.get("companyCode"), r.get("fiscalYear"),
                r.get("accountingDocument"), r.get("soldToParty")
            ))
        except: pass

    print("Ingesting journal_entry_items...")
    for r in load_jsonl("journal_entry_items_accounts_receivable"):
        try:
            conn.execute("INSERT OR REPLACE INTO journal_entry_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                r.get("accountingDocument"), r.get("accountingDocumentItem"),
                r.get("companyCode"), r.get("fiscalYear"),
                r.get("glAccount"), r.get("referenceDocument"),
                r.get("profitCenter"), r.get("transactionCurrency"),
                float(r.get("amountInTransactionCurrency") or 0),
                r.get("postingDate"), r.get("documentDate"),
                r.get("customer"), r.get("clearingDate"),
                r.get("clearingAccountingDocument")
            ))
        except: pass

    print("Ingesting payments...")
    for r in load_jsonl("payments_accounts_receivable"):
        try:
            conn.execute("INSERT OR REPLACE INTO payments VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
                r.get("accountingDocument"), r.get("accountingDocumentItem"),
                r.get("companyCode"), r.get("fiscalYear"),
                r.get("clearingDate"), r.get("clearingAccountingDocument"),
                float(r.get("amountInTransactionCurrency") or 0), r.get("transactionCurrency"),
                r.get("customer"), r.get("postingDate"), r.get("glAccount")
            ))
        except: pass

    print("Ingesting plants...")
    for r in load_jsonl("plants"):
        try:
            conn.execute("INSERT OR REPLACE INTO plants VALUES (?,?,?,?,?)", (
                r.get("plant"), r.get("plantName"), r.get("salesOrganization"),
                r.get("distributionChannel"), r.get("addressId")
            ))
        except: pass

    print("Ingesting product_descriptions...")
    for r in load_jsonl("product_descriptions"):
        try:
            conn.execute("INSERT OR REPLACE INTO product_descriptions VALUES (?,?,?)", (
                r.get("product"), r.get("language"), r.get("productDescription")
            ))
        except: pass

    print("Ingesting customer_sales_area...")
    for r in load_jsonl("customer_sales_area_assignments"):
        try:
            conn.execute("INSERT OR REPLACE INTO customer_sales_area VALUES (?,?,?,?,?,?,?)", (
                r.get("customer"), r.get("salesOrganization"), r.get("distributionChannel"),
                r.get("currency"), r.get("customerPaymentTerms"),
                r.get("incotermsClassification"), r.get("incotermsLocation1")
            ))
        except: pass

    conn.commit()
    print("Done ingesting base data.")

def build_edges(conn):
    print("Building graph edges...")
    conn.execute("DELETE FROM graph_edges")

    rules = [
        # SalesOrder → Customer
        """INSERT OR IGNORE INTO graph_edges
           SELECT 'SalesOrder', salesOrder, 'Customer', soldToParty, 'SOLD_TO'
           FROM sales_order_headers WHERE soldToParty IS NOT NULL AND soldToParty != ''""",
        # SalesOrder → SalesOrderItem
        """INSERT OR IGNORE INTO graph_edges
           SELECT 'SalesOrder', salesOrder, 'SalesOrderItem', salesOrder||'/'||salesOrderItem, 'HAS_ITEM'
           FROM sales_order_items""",
        # SalesOrderItem → Material (even without description)
        """INSERT OR IGNORE INTO graph_edges
           SELECT 'SalesOrderItem', salesOrder||'/'||salesOrderItem, 'Material', material, 'IS_MATERIAL'
           FROM sales_order_items WHERE material IS NOT NULL AND material != ''""",
        # SalesOrderItem → Plant (productionPlant)
        """INSERT OR IGNORE INTO graph_edges
           SELECT 'SalesOrderItem', salesOrder||'/'||salesOrderItem, 'Plant', productionPlant, 'PRODUCED_AT'
           FROM sales_order_items WHERE productionPlant IS NOT NULL AND productionPlant != ''""",
        # BillingDocument → Customer
        """INSERT OR IGNORE INTO graph_edges
           SELECT 'BillingDocument', billingDocument, 'Customer', soldToParty, 'BILLED_TO'
           FROM billing_documents WHERE soldToParty IS NOT NULL AND soldToParty != ''""",
        # BillingDocument → JournalEntry (via referenceDocument)
        """INSERT OR IGNORE INTO graph_edges
           SELECT 'BillingDocument', b.billingDocument, 'JournalEntry', j.accountingDocument, 'RECORDED_IN'
           FROM billing_documents b
           JOIN journal_entry_items j ON j.referenceDocument = b.billingDocument""",
        # BillingDocument → SalesOrder — inferred via customer + date proximity
        # (no direct FK in dataset, but billing soldToParty = SO soldToParty)
        # JournalEntry → Payment (via clearingAccountingDocument)
        """INSERT OR IGNORE INTO graph_edges
           SELECT 'JournalEntry', accountingDocument, 'Payment', clearingAccountingDocument, 'CLEARED_BY'
           FROM journal_entry_items
           WHERE clearingAccountingDocument IS NOT NULL AND clearingAccountingDocument != ''""",
        # JournalEntry → Customer
        """INSERT OR IGNORE INTO graph_edges
           SELECT 'JournalEntry', accountingDocument, 'Customer', customer, 'FOR_CUSTOMER'
           FROM journal_entry_items WHERE customer IS NOT NULL AND customer != ''""",
        # Delivery → Plant (shippingPoint = plant code)
        """INSERT OR IGNORE INTO graph_edges
           SELECT 'Delivery', deliveryDocument, 'Plant', shippingPoint, 'SHIPS_FROM'
           FROM outbound_delivery_headers
           WHERE shippingPoint IS NOT NULL AND shippingPoint != ''""",
        # SalesOrder → Delivery  (inferred: same soldToParty & creationDate)
        """INSERT OR IGNORE INTO graph_edges
           SELECT DISTINCT 'SalesOrder', s.salesOrder, 'Delivery', d.deliveryDocument, 'FULFILLED_BY'
           FROM sales_order_headers s
           JOIN outbound_delivery_headers d ON date(d.creationDate) = date(s.creationDate)
           JOIN sales_order_items si ON si.salesOrder = s.salesOrder AND si.productionPlant = d.shippingPoint
           LIMIT 200""",
        # Customer → BillingDocument (reverse edge for traversal)
        """INSERT OR IGNORE INTO graph_edges
           SELECT 'Customer', soldToParty, 'BillingDocument', billingDocument, 'HAS_BILLING'
           FROM billing_documents WHERE soldToParty IS NOT NULL AND soldToParty != ''""",
    ]

    for sql in rules:
        try:
            conn.execute(sql)
        except Exception as e:
            print(f"  Edge rule failed: {e}")

    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0]
    print(f"Built {count} graph edges.")

    # Print summary
    rows = conn.execute("SELECT source_type, target_type, relationship, COUNT(*) as c FROM graph_edges GROUP BY 1,2,3 ORDER BY c DESC").fetchall()
    for r in rows:
        print(f"  {r[0]} -[{r[2]}]-> {r[1]} : {r[3]}")

if __name__ == "__main__":
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    create_tables(conn)
    ingest(conn)
    build_edges(conn)
    conn.close()
    print("\nDatabase ready:", DB_PATH)
