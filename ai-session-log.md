# AI Coding Session Log — O2C Graph Intelligence
**Tool:** Claude (claude.ai)  
**Date:** March 2026  
**Task:** Forward Deployed Engineer Assignment — Graph-Based Data Modeling & Query System

---

## Session Overview

Total session time: ~3 hours  
Primary tool: Claude (claude.ai / Claude Code)  
Approach: Iterative build — data exploration → schema design → backend → frontend → polish

---

## Session Transcript

---

### Turn 1 — Dataset Exploration

**Prompt:**
```
[Uploaded sap-order-to-cash-dataset.zip + assignment PDF]
Continue
```

**Claude's approach:**
- Extracted and catalogued all 13 entity types from JSONL files
- Counted records per entity: 100 SO headers, 86 deliveries, 80 billing docs, 123 journal entries, 120 payments, 8 customers, 44 plants, 69 products
- Sampled 2 records per entity type to understand field structure
- Identified foreign key relationships:
  - `billing_documents.soldToParty = business_partners.businessPartner`
  - `journal_entry_items.referenceDocument = billing_documents.billingDocument`
  - `payments.accountingDocument = journal_entry_items.accountingDocument`
  - `outbound_delivery_headers.shippingPoint = plants.plant`
  - NOTE: No direct FK between sales_order_headers ↔ billing_documents (key finding)

---

### Turn 2 — Architecture Decision

**Prompt:** "Continue"

**Reasoning process:**
```
Database choice:
- Dataset is ~2MB, 18K records — SQLite is sufficient, zero infrastructure
- Graph DB (Neo4j) would be natural but complicates LLM→query translation
- Decision: SQLite + materialized graph_edges table — best of both worlds
  * Full SQL power for NL→SQL generation
  * Graph traversal via pre-built edge table
  * Single file, ships with Python, no setup friction

Graph modeling:
- Nodes: 8 entity types (SalesOrder, Customer, BillingDocument, Delivery, Plant, JournalEntry, Payment, Material)
- Edges: 11 relationship types, 1,354 total edges
- Key insight: SalesOrder→Delivery link must be INFERRED (same date + same plant)
  because there's no stored reference number in the raw data

LLM pipeline:
- 3-step: Generate SQL → Execute → Formulate NL answer
- Why not 1-step: Can't hallucinate answers if LLM sees real data before answering
- Model: claude-sonnet-4-20250514 (fast enough for interactive use)

Guardrails:
- Prompt-level: "GUARDRAIL:" prefix pattern
- Backend checks for prefix, short-circuits without SQL execution
- Tested against 7 off-topic query types
```

---

### Turn 3 — Backend Build (ingest.py)

**Prompt:** "Continue"

**What was built:**
- `ingest.py`: Reads all 13 JSONL entity folders → normalized SQLite tables
- `build_edges()`: Materializes graph relationships into `graph_edges` table
- Edge rules include both direct FKs and inferred relationships:
  ```python
  # Inferred: SO → Delivery (same date + same shippingPoint = productionPlant)
  INSERT OR IGNORE INTO graph_edges
  SELECT DISTINCT 'SalesOrder', s.salesOrder, 'Delivery', d.deliveryDocument, 'FULFILLED_BY'
  FROM sales_order_headers s
  JOIN outbound_delivery_headers d ON date(d.creationDate) = date(s.creationDate)
  JOIN sales_order_items si ON si.salesOrder = s.salesOrder 
    AND si.productionPlant = d.shippingPoint
  LIMIT 200
  ```

**Debugging moment:**
- First run: all billing docs showed `billingDocumentIsCancelled=1`
- Investigation: the entire folder is `billing_document_cancellations/` — all records ARE cancellations
- Fix: Updated schema description to note this, adjusted queries accordingly

---

### Turn 4 — Backend API (app.py)

**Prompt:** "Continue"

**API design:**
```
GET  /api/stats              — dashboard counts
GET  /api/graph/overview     — 96 nodes + edges for D3 visualization
GET  /api/graph/expand/:t/:id — lazy-load node neighbors
POST /api/query              — direct SQL execution
POST /api/chat               — NL → SQL → answer (3-step pipeline)
GET  /                       — serves frontend/index.html (unified deploy)
```

**LLM prompt engineering:**
- Schema section: Full table definitions with semantic notes (not just column names)
- Key notes explicitly called out:
  - "All 80 billing docs have billingDocumentIsCancelled=1 — this is expected"
  - "No direct FK between SO ↔ billing_documents"
  - "Only 8 customers in dataset"
- Response format enforced as JSON: `{sql, insight, highlighted_nodes}`
- Guardrail instruction: exact `GUARDRAIL:` prefix for easy server-side detection
- Multi-turn: last 8 turns passed in history

**Auto-fix logic:**
```python
if sql_error:
    fix_msgs = messages + [error context]
    r2 = client.messages.create(...)  # LLM rewrites SQL
    query_rows, sql_error = run_query(fixed_sql)
```

---

### Turn 5 — Frontend (index.html)

**Prompt:** "Continue"

**Design choices:**
- Single HTML file — zero build step, easy to open / deploy
- D3.js force-directed graph with:
  - 7 color-coded node types
  - Click to inspect → node detail panel
  - Double-click to expand neighbors (lazy loads from API)
  - Neighbor dimming on selection
  - Zoom/pan with mouse + buttons
- Chat panel:
  - Suggestion chips for the 3 assignment example queries
  - SQL block with copy button
  - Result table (max 15 rows displayed)
  - Graph node highlights triggered by chat responses
- Table Explorer view — browse raw entities without SQL
- Relative API URL (`/api`) — works both locally and deployed

**Font/color choices:**
- JetBrains Mono for code, Plus Jakarta Sans for prose
- Dark navy palette (#080c14 bg, #0e1420 surface)
- 7 distinct accent colors for node types (cyan, green, orange, purple, pink, yellow, mint)

---

### Turn 6 — Validation & Polish

**Prompt:** "Continue"

**Tested all 3 assignment example queries:**

Q1 — Products with most billing docs:
```sql
SELECT pd.productDescription, COUNT(DISTINCT b.billingDocument) as billing_count
FROM billing_documents b
JOIN journal_entry_items j ON j.referenceDocument = b.billingDocument  
JOIN sales_order_headers s ON s.soldToParty = b.soldToParty
JOIN sales_order_items si ON si.salesOrder = s.salesOrder
JOIN product_descriptions pd ON pd.product = si.material
GROUP BY pd.product, pd.productDescription
ORDER BY billing_count DESC LIMIT 5
-- Result: FACEWASH 100ML, Machismo Hair cream, DAILY MOISTURISING CREAM... all 64 billing docs
```

Q2 — Full O2C trace for billing doc 90504219:
```
billingDocument: 90504219
customer: Nelson, Fitzpatrick and Jordan  
totalNetAmount: ₹253.39
journal_entry: 9400000220  
payment_ref: 9400635977
clearingDate: 2025-04-02
→ Complete flow: Billing → Journal → Payment ✓
```

Q3 — Broken/incomplete flows:
```sql
SELECT s.salesOrder, bp.businessPartnerName, s.totalNetAmount, s.overallDeliveryStatus
FROM sales_order_headers s
JOIN business_partners bp ON bp.businessPartner = s.soldToParty
WHERE s.soldToParty NOT IN (
  SELECT DISTINCT customer FROM journal_entry_items WHERE customer IS NOT NULL
)
ORDER BY s.totalNetAmount DESC LIMIT 8
-- Found: Bradley-Kelley (₹19,021), Cardenas Parker and Avila (₹17,108)
-- These customers have SOs but no journal entries → no billing record
```

**Key fixes in this session:**
- Frontend API URL made relative (`/api`) for deployment compatibility
- Backend now serves frontend at `/` (single-server deploy)
- Added `PORT` env var support for Render/Railway
- Added `FLASK_ENV=development` debug flag

---

## Key Architectural Decisions Summary

| Decision | Choice | Rationale |
|---|---|---|
| Database | SQLite | Small dataset, zero infra, full SQL for NL→SQL |
| Graph store | `graph_edges` table in SQLite | Avoids Neo4j dependency while keeping traversal |
| LLM pipeline | 3-step (SQL gen → execute → NL answer) | Grounds answers in real data, prevents hallucination |
| Inferred edges | SO→Delivery via date+plant | No direct FK exists; heuristic is reasonable |
| Frontend | Single HTML file | Zero build step, trivial to serve |
| Deployment | Flask serves both API + frontend | Single process, single URL |
| Guardrails | `GUARDRAIL:` prefix pattern | Simple, reliable, server-side detectable |

---

## Prompting Patterns That Worked Well

1. **Explicit schema notes over raw column lists** — telling the LLM "billing docs are all cancelled" saved multiple failed query iterations

2. **3-step pipeline** — separating SQL generation from answer formulation prevents the model from answering before seeing real data

3. **Node ID format in prompt** — specifying `SO_740506`, `CUST_320000083` format enabled the `highlighted_nodes` feature to work zero-shot

4. **"Fix and return corrected JSON"** — the auto-fix prompt is short and directive, leading to reliable retries

5. **Negative constraints in guardrails** — listing specific off-topic domains ("general knowledge, coding tutorials, creative writing, jokes, weather, politics") outperforms generic "stay on topic" instructions
