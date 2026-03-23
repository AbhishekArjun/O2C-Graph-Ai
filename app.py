"""
O2C Graph Intelligence — Flask Backend
Serves: REST API on /api/* + frontend static files on /
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3, json, os, re
import groq

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(__file__)
PROJECT_DIR  = os.path.dirname(BASE_DIR)
DB_PATH      = os.path.join(BASE_DIR, "o2c.db")
FRONTEND_DIR = BASE_DIR

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app)

# ── Database helpers ────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def sanitize_sql(sql):
    """Fix common LLM SQL mistakes before execution."""
    import re
    # Fix unquoted numeric IDs in WHERE clauses for TEXT columns
    # e.g. WHERE billingDocument = 90504219 -> WHERE billingDocument = '90504219'
    text_id_cols = [
        'billingDocument', 'salesOrder', 'deliveryDocument',
        'accountingDocument', 'businessPartner', 'soldToParty',
        'customer', 'plant', 'referenceDocument', 'clearingAccountingDocument',
        'cancelledBillingDocument', 'material',
    ]
    for col in text_id_cols:
        # Match col = <unquoted number> (not already quoted)
        pattern = rf"({re.escape(col)}\s*=\s*)([0-9]{{5,}})"
        sql = re.sub(pattern, lambda m: m.group(1) + "'" + m.group(2) + "'", sql)
    return sql

def run_query(sql, params=()):
    conn = get_db()
    try:
        sql = sanitize_sql(sql)
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
        return rows, None
    except Exception as e:
        return None, str(e)
    finally:
        conn.close()

# ── LLM Schema + Prompt ─────────────────────────────────────────────────────

SCHEMA = """
SAP Order-to-Cash (O2C) SQLite database — VERIFIED WORKING SCHEMA:

TABLES AND EXACT COLUMN NAMES:

1. sales_order_headers
   Columns: salesOrder(PK,TEXT), salesOrderType, salesOrganization, distributionChannel,
   soldToParty(TEXT, FK→business_partners.businessPartner), creationDate(TEXT ISO8601),
   createdByUser, totalNetAmount(REAL INR), overallDeliveryStatus(TEXT: 'A'=not started,'B'=partial,'C'=complete),
   overallOrdReltdBillgStatus, transactionCurrency, requestedDeliveryDate,
   headerBillingBlockReason, deliveryBlockReason, incotermsClassification,
   incotermsLocation1, customerPaymentTerms
   ROW COUNT: 100

2. sales_order_items
   Columns: salesOrder(TEXT FK→sales_order_headers.salesOrder), salesOrderItem(TEXT),
   material(TEXT, product/material code), requestedQuantity(REAL), requestedQuantityUnit,
   netAmount(REAL INR), materialGroup, productionPlant(TEXT FK→plants.plant), storageLocation
   PRIMARY KEY: (salesOrder, salesOrderItem) | ROW COUNT: 167

3. business_partners  [= Customers]
   Columns: businessPartner(PK TEXT), customer(TEXT same value as businessPartner),
   businessPartnerFullName, businessPartnerName(TEXT), businessPartnerCategory,
   businessPartnerGrouping, creationDate, businessPartnerIsBlocked(INTEGER 0/1),
   isMarkedForArchiving(INTEGER 0/1)
   ROW COUNT: 8 (all customers)

4. outbound_delivery_headers  [= Deliveries]
   Columns: deliveryDocument(PK TEXT), creationDate(TEXT ISO8601),
   shippingPoint(TEXT FK→plants.plant), overallGoodsMovementStatus(TEXT 'A'=not moved,'C'=complete),
   overallPickingStatus(TEXT 'A'=not picked,'C'=picked), hdrGeneralIncompletionStatus,
   headerBillingBlockReason, deliveryBlockReason, actualGoodsMovementDate
   ROW COUNT: 86

5. billing_documents  [= Cancelled Billing/Invoice records]
   Columns: billingDocument(PK TEXT), billingDocumentType, creationDate(TEXT ISO8601),
   billingDocumentDate, billingDocumentIsCancelled(INTEGER — ALL ROWS = 1),
   cancelledBillingDocument, totalNetAmount(REAL INR), transactionCurrency,
   companyCode, fiscalYear, accountingDocument(TEXT FK→journal_entry_items.accountingDocument),
   soldToParty(TEXT FK→business_partners.businessPartner)
   ROW COUNT: 80 — NOTE: ALL records have billingDocumentIsCancelled=1 (this entire table
   represents cancellation events). Do NOT filter by billingDocumentIsCancelled=0 — that returns 0 rows.

6. journal_entry_items  [= Accounts Receivable accounting entries]
   Columns: accountingDocument(TEXT), accountingDocumentItem(TEXT),
   companyCode, fiscalYear, glAccount, referenceDocument(TEXT = billingDocument,
   FK→billing_documents.billingDocument), profitCenter, transactionCurrency,
   amountInTransactionCurrency(REAL INR), postingDate(TEXT ISO8601), documentDate,
   customer(TEXT FK→business_partners.businessPartner), clearingDate,
   clearingAccountingDocument(TEXT)
   PRIMARY KEY: (accountingDocument, accountingDocumentItem) | ROW COUNT: 123

7. payments  [= Payment clearing records]
   Columns: accountingDocument(TEXT FK→journal_entry_items.accountingDocument),
   accountingDocumentItem(TEXT), companyCode, fiscalYear, clearingDate(TEXT ISO8601),
   clearingAccountingDocument(TEXT), amountInTransactionCurrency(REAL INR),
   transactionCurrency, customer(TEXT FK→business_partners.businessPartner),
   postingDate(TEXT ISO8601), glAccount
   PRIMARY KEY: (accountingDocument, accountingDocumentItem) | ROW COUNT: 120

8. plants
   Columns: plant(PK TEXT), plantName(TEXT), salesOrganization, distributionChannel, addressId
   ROW COUNT: 44

9. product_descriptions
   Columns: product(PK TEXT), language, productDescription(TEXT)
   ROW COUNT: 69
   *** CRITICAL: product codes here (B89..., 3001...) DO NOT MATCH material codes in
   sales_order_items (S89...). You CANNOT join product_descriptions to sales_order_items
   directly on product=material. Use LIKE '%' + SUBSTR(material,3) + '%' heuristic OR
   query product_descriptions separately. ***

10. customer_sales_area
    Columns: customer(TEXT), salesOrganization, distributionChannel, currency,
    customerPaymentTerms, incotermsClassification, incotermsLocation1
    PRIMARY KEY: (customer, salesOrganization, distributionChannel)

CONFIRMED WORKING FOREIGN KEY JOINS (use EXACTLY these):
  sales_order_headers.soldToParty   = business_partners.businessPartner   ✓ (100% match)
  sales_order_headers.salesOrder    = sales_order_items.salesOrder         ✓ (100% match)
  billing_documents.soldToParty     = business_partners.businessPartner   ✓ (100% match)
  journal_entry_items.referenceDocument = billing_documents.billingDocument ✓ (64 links)
  payments.accountingDocument       = journal_entry_items.accountingDocument ✓ (120 links)
  outbound_delivery_headers.shippingPoint = plants.plant                  ✓ (86 links)

GAPS — NO DIRECT FK (infer via shared soldToParty):
  sales_order_headers ↔ billing_documents   — no direct reference stored
  sales_order_headers ↔ outbound_delivery_headers — no direct reference stored

VERIFIED WORKING QUERY PATTERNS:

Pattern A — Products with most billing docs:
  SELECT pd.productDescription, COUNT(DISTINCT b.billingDocument) as billing_count
  FROM billing_documents b
  JOIN journal_entry_items j ON j.referenceDocument = b.billingDocument
  JOIN sales_order_headers s ON s.soldToParty = b.soldToParty
  JOIN sales_order_items si ON si.salesOrder = s.salesOrder
  JOIN product_descriptions pd ON pd.product = si.material
  GROUP BY pd.product, pd.productDescription ORDER BY billing_count DESC LIMIT 10

Pattern B — Full O2C trace for a billing document:
  SELECT b.billingDocument, bp.businessPartnerName, b.totalNetAmount,
    j.accountingDocument, j.amountInTransactionCurrency, j.postingDate,
    p.clearingAccountingDocument, p.clearingDate
  FROM billing_documents b
  JOIN business_partners bp ON bp.businessPartner = b.soldToParty
  LEFT JOIN journal_entry_items j ON j.referenceDocument = b.billingDocument
  LEFT JOIN payments p ON p.accountingDocument = j.accountingDocument
  WHERE b.billingDocument = '<ID>'

Pattern C — Broken flows (customers with SOs but no billing/journal):
  SELECT s.salesOrder, bp.businessPartnerName, s.totalNetAmount, s.overallDeliveryStatus
  FROM sales_order_headers s
  JOIN business_partners bp ON bp.businessPartner = s.soldToParty
  WHERE s.soldToParty NOT IN (
    SELECT DISTINCT customer FROM journal_entry_items WHERE customer IS NOT NULL
  ) ORDER BY s.totalNetAmount DESC LIMIT 20

Pattern D — Revenue by customer:
  SELECT bp.businessPartnerName, COUNT(s.salesOrder) as order_count,
    ROUND(SUM(s.totalNetAmount),2) as total_revenue
  FROM sales_order_headers s
  JOIN business_partners bp ON bp.businessPartner = s.soldToParty
  GROUP BY s.soldToParty, bp.businessPartnerName ORDER BY total_revenue DESC

Pattern E — List sales orders (always works):
  SELECT s.salesOrder, bp.businessPartnerName, s.totalNetAmount,
    s.overallDeliveryStatus, s.creationDate
  FROM sales_order_headers s
  JOIN business_partners bp ON bp.businessPartner = s.soldToParty
  ORDER BY s.totalNetAmount DESC LIMIT 20
"""

SYSTEM_PROMPT = f"""You are an expert SAP Order-to-Cash (O2C) data analyst with direct knowledge of this database.

{SCHEMA}

## STRICT GUARDRAILS
If the user asks ANYTHING outside this O2C dataset — general knowledge, coding, creative
writing, events, opinions, math, jokes, weather, or requests to CREATE/INSERT/UPDATE data —
respond with EXACTLY:
GUARDRAIL: This system is designed to answer questions about the SAP Order-to-Cash dataset only. I can help you explore sales orders, billing documents, deliveries, payments, customers, plants, and products.

## RESPONSE FORMAT (O2C questions only)
Return ONLY valid JSON, no markdown, no code fences, nothing outside the JSON object:
{{"sql": "SELECT ...", "insight": "1-2 sentence business insight", "highlighted_nodes": ["SO_740506"]}}

## CRITICAL SQL RULES
1. SQLite syntax only. SELECT only — never INSERT/UPDATE/DELETE/CREATE.
2. Use EXACTLY the column and table names from the schema above. No invented columns.
3. ALWAYS use a JOIN to business_partners when showing customer info (to get businessPartnerName).
4. For "products with billing docs": use Pattern A — join through journal_entry_items.
5. For "broken flows" or "orders without payments": use Pattern C NOT IN approach.
6. billingDocumentIsCancelled is ALWAYS 1 — never filter WHERE billingDocumentIsCancelled=0.
7. product_descriptions.product != sales_order_items.material — do NOT join them on equality.
8. LIMIT 50 for list queries. No LIMIT for COUNT/SUM aggregations.
9. Node IDs: SO_<salesOrder>, CUST_<businessPartner>, BD_<billingDocument>, PLANT_<plant>, DEL_<deliveryDocument>, JE_<accountingDocument>, PAY_<clearingAccountingDocument>
10. CRITICAL — ALL ID columns are TEXT not INTEGER. ALWAYS use single quotes: WHERE billingDocument = '90504219' not WHERE billingDocument = 90504219. This applies to salesOrder, billingDocument, businessPartner, deliveryDocument, accountingDocument, plant.
11. Use COALESCE to avoid NULL in aggregations: COALESCE(ROUND(SUM(totalNetAmount),2), 0) as total
12. Real data ranges: salesOrders 740506-740614, billingDocuments 90504219-90504301, customerIDs start with 310 or 320.
"""

# ── Frontend serving ────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")

# ── API: Stats ──────────────────────────────────────────────────────────────

@app.route("/api/stats")
def get_stats():
    conn = get_db()
    s = {
        "salesOrders":    conn.execute("SELECT COUNT(*) FROM sales_order_headers").fetchone()[0],
        "customers":      conn.execute("SELECT COUNT(*) FROM business_partners").fetchone()[0],
        "billingDocs":    conn.execute("SELECT COUNT(*) FROM billing_documents").fetchone()[0],
        "deliveries":     conn.execute("SELECT COUNT(*) FROM outbound_delivery_headers").fetchone()[0],
        "products":       conn.execute("SELECT COUNT(*) FROM product_descriptions").fetchone()[0],
        "plants":         conn.execute("SELECT COUNT(*) FROM plants").fetchone()[0],
        "journalEntries": conn.execute("SELECT COUNT(*) FROM journal_entry_items").fetchone()[0],
        "payments":       conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0],
        "graphEdges":     conn.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0],
        "totalRevenue":   conn.execute("SELECT ROUND(SUM(totalNetAmount),2) FROM sales_order_headers").fetchone()[0],
        "totalPayments":  conn.execute("SELECT ROUND(SUM(amountInTransactionCurrency),2) FROM payments").fetchone()[0],
        "cancelledBills": conn.execute("SELECT COUNT(*) FROM billing_documents WHERE billingDocumentIsCancelled=1").fetchone()[0],
    }
    conn.close()
    return jsonify(s)

# ── API: Graph ──────────────────────────────────────────────────────────────

NODE_PREFIX = {
    "Customer":"CUST_","SalesOrder":"SO_","BillingDocument":"BD_",
    "Plant":"PLANT_","Delivery":"DEL_","JournalEntry":"JE_",
    "Payment":"PAY_","Material":"MAT_","SalesOrderItem":"SOI_"
}

TABLE_MAP = {
    "Customer":        ("business_partners",         "businessPartner",  "businessPartnerName"),
    "SalesOrder":      ("sales_order_headers",       "salesOrder",       "salesOrder"),
    "BillingDocument": ("billing_documents",         "billingDocument",  "billingDocument"),
    "Plant":           ("plants",                    "plant",            "plantName"),
    "Delivery":        ("outbound_delivery_headers", "deliveryDocument", "deliveryDocument"),
    "JournalEntry":    ("journal_entry_items",       "accountingDocument","accountingDocument"),
}

@app.route("/api/graph/overview")
def graph_overview():
    conn = get_db()
    nodes = []

    def add(qsql, ntype, id_col, label_col=None):
        for r in conn.execute(qsql):
            d = dict(r)
            lbl = str(d.get(label_col or id_col, d.get(id_col, "?")))
            if len(lbl) > 20: lbl = lbl[:19] + "…"
            nodes.append({"id": NODE_PREFIX[ntype]+str(d[id_col]), "label": lbl,
                          "type": ntype, "data": d})

    add("SELECT businessPartner, businessPartnerName, businessPartnerIsBlocked FROM business_partners",
        "Customer", "businessPartner", "businessPartnerName")
    add("SELECT salesOrder, soldToParty, totalNetAmount, overallDeliveryStatus, creationDate FROM sales_order_headers LIMIT 25",
        "SalesOrder", "salesOrder")
    add("SELECT billingDocument, totalNetAmount, billingDocumentIsCancelled, soldToParty, creationDate FROM billing_documents LIMIT 20",
        "BillingDocument", "billingDocument")
    add("SELECT plant, plantName FROM plants LIMIT 15",
        "Plant", "plant", "plantName")
    add("SELECT deliveryDocument, creationDate, shippingPoint, overallGoodsMovementStatus FROM outbound_delivery_headers LIMIT 12",
        "Delivery", "deliveryDocument")
    add("SELECT accountingDocument, amountInTransactionCurrency, postingDate, customer FROM journal_entry_items LIMIT 10",
        "JournalEntry", "accountingDocument")

    seen_pay = set()
    for r in conn.execute("SELECT DISTINCT clearingAccountingDocument, amountInTransactionCurrency, clearingDate FROM payments WHERE clearingAccountingDocument IS NOT NULL LIMIT 8"):
        nid = "PAY_" + str(r["clearingAccountingDocument"])
        if nid not in seen_pay:
            seen_pay.add(nid)
            nodes.append({"id": nid, "label": f"PAY {r['clearingAccountingDocument']}",
                          "type": "Payment", "data": dict(r)})

    node_ids = {n["id"] for n in nodes}
    raw_edges = conn.execute("SELECT source_type, source_id, target_type, target_id, relationship FROM graph_edges").fetchall()
    edges, seen_e = [], set()
    for e in raw_edges:
        src = NODE_PREFIX.get(e["source_type"], e["source_type"]+"_") + e["source_id"]
        tgt = NODE_PREFIX.get(e["target_type"], e["target_type"]+"_") + e["target_id"]
        key = (src, tgt)
        if src in node_ids and tgt in node_ids and key not in seen_e:
            seen_e.add(key)
            edges.append({"source": src, "target": tgt, "label": e["relationship"]})

    conn.close()
    return jsonify({"nodes": nodes, "edges": edges})

@app.route("/api/graph/expand/<node_type>/<path:node_id>")
def expand_node(node_type, node_id):
    conn = get_db()
    nbrs = conn.execute(
        "SELECT * FROM graph_edges WHERE (source_type=? AND source_id=?) OR (target_type=? AND target_id=?) LIMIT 30",
        (node_type, node_id, node_type, node_id)
    ).fetchall()

    src_prefix = NODE_PREFIX.get(node_type, node_type+"_")
    new_nodes, new_edges = [], []

    for e in nbrs:
        e = dict(e)
        if e["source_type"] == node_type and e["source_id"] == node_id:
            nt, ni, direction = e["target_type"], e["target_id"], "out"
        else:
            nt, ni, direction = e["source_type"], e["source_id"], "in"

        prefix = NODE_PREFIX.get(nt, nt+"_")
        label, data = f"{nt} {ni}", {}

        if nt in TABLE_MAP:
            tbl, pk, lbl_col = TABLE_MAP[nt]
            row = conn.execute(f"SELECT * FROM {tbl} WHERE {pk}=? LIMIT 1", (ni,)).fetchone()
            if row:
                data = dict(row)
                label = str(data.get(lbl_col, ni))
                if len(label) > 20: label = label[:19] + "…"

        new_nodes.append({"id": prefix+ni, "label": label, "type": nt, "data": data})
        if direction == "out":
            new_edges.append({"source": src_prefix+node_id, "target": prefix+ni, "label": e["relationship"]})
        else:
            new_edges.append({"source": prefix+ni, "target": src_prefix+node_id, "label": e["relationship"]})

    conn.close()
    return jsonify({"nodes": new_nodes, "edges": new_edges})

# ── API: Direct SQL Query ───────────────────────────────────────────────────

@app.route("/api/query", methods=["POST"])
def direct_query():
    sql = (request.json or {}).get("sql", "").strip()
    if not sql.upper().startswith("SELECT"):
        return jsonify({"error": "Only SELECT queries are permitted"}), 400
    rows, err = run_query(sql)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"rows": rows, "count": len(rows)})

# ── API: Chat (NL → SQL → Answer) ──────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def chat():
    body     = request.json or {}
    user_msg = body.get("message", "").strip()
    history  = body.get("history", [])

    if not user_msg:
        return jsonify({"error": "Empty message"}), 400

    client   = groq.Groq(api_key=os.environ.get("GROQ_API_KEY", "your_groq_api_key_here"))
    messages = [{"role": h["role"], "content": h["content"]} for h in history[-8:]]
    messages.append({"role": "user", "content": user_msg})

    def get_completion(msgs, max_toks):
        full_msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + msgs
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=full_msgs,
            max_tokens=max_toks,
            temperature=0.1
        )
        return resp.choices[0].message.content.strip()

    try:
        # ── Step 1: Generate SQL ────────────────────────────────────────────────
        raw = get_completion(messages, 1500)
    
        # Guardrail check
        if raw.startswith("GUARDRAIL:"):
            return jsonify({
                "answer": raw[len("GUARDRAIL:"):].strip(),
                "sql": None, "data": [], "highlighted_nodes": [],
                "guardrail": True, "row_count": 0
            })
    
        # Parse JSON response
        parsed = {}
        try:
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            parsed = json.loads(m.group() if m else raw)
        except Exception:
            # Non-JSON means either guardrail or plain text answer
            is_guard = any(kw in raw.lower() for kw in ["dataset only", "order-to-cash dataset", "cannot answer"])
            return jsonify({
                "answer": raw, "sql": None, "data": [], "highlighted_nodes": [],
                "guardrail": is_guard, "row_count": 0
            })
    
        sql         = parsed.get("sql", "")
        highlighted = parsed.get("highlighted_nodes", [])
    
        # ── Step 2: Execute SQL (with auto-fix on error) ────────────────────────
        query_rows, sql_error = [], None
    
        if sql and sql.strip().upper().startswith("SELECT"):
            query_rows, sql_error = run_query(sql)
    
            if sql_error:
                fix_msgs = messages + [
                    {"role": "assistant", "content": raw},
                    {"role": "user",      "content": f"SQL execution error: {sql_error}\nFix the SQL and return corrected JSON only."}
                ]
                raw2 = get_completion(fix_msgs, 1000)
                try:
                    m2 = re.search(r'\{.*\}', raw2, re.DOTALL)
                    p2 = json.loads(m2.group() if m2 else raw2)
                    sql = p2.get("sql", sql)
                    query_rows, sql_error = run_query(sql)
                    highlighted = p2.get("highlighted_nodes", highlighted)
                except Exception:
                    pass
    
        # ── Step 3: Generate natural language answer from real results ──────────
        row_count = len(query_rows) if query_rows else 0
        preview   = json.dumps((query_rows or [])[:15], indent=2, default=str)
    
        final_msgs = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content":
                f"The SQL query returned {row_count} rows. Here are the results:\n{preview}\n\n"
                f"Write a clear, specific 2-4 sentence answer in plain text (no JSON, no markdown). "
                f"Cite actual values — customer names, amounts (in ₹), document IDs, counts — from the results. "
                f"If 0 rows, explain what the zero result means for the business (e.g. 'no broken flows found')."}
        ]
        answer = get_completion(final_msgs, 600)
    
        # Strip JSON if model slipped back to it
        if answer.startswith("{"):
            try:
                fa = json.loads(answer)
                answer = fa.get("insight") or fa.get("answer") or answer
            except Exception:
                pass
    
        return jsonify({
            "answer":           answer,
            "sql":              sql,
            "data":             (query_rows or [])[:20],
            "highlighted_nodes": highlighted,
            "guardrail":        False,
            "sql_error":        sql_error,
            "row_count":        row_count,
        })
    except Exception as e:
        return jsonify({
            "answer": f"LLM / Backend Error: {str(e)}",
            "sql": None,
            "data": [],
            "highlighted_nodes": [],
            "guardrail": False,
            "sql_error": str(e),
            "row_count": 0,
        })

# ── Run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    debug = os.environ.get("FLASK_ENV") == "development"
    print(f"O2C Graph Intelligence -> http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
