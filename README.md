# O2C Graph Intelligence

A **context graph system with an LLM-powered query interface** for SAP Order-to-Cash data.

Built for the Forward Deployed Engineer assignment. Live demo: [your-deploy-url]

---

## What It Does

- Ingests 13 SAP O2C entity types into SQLite and constructs a **graph of 1,354 edges**
- Visualizes the graph interactively with D3.js (force-directed, expandable nodes)
- Provides a **natural language → SQL → data** chat interface powered by Claude Sonnet
- Enforces guardrails to keep queries domain-scoped
- Includes a table explorer for direct entity browsing

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Browser (SPA)                        │
│  ┌──────────────────┐   ┌──────────────────────────┐   │
│  │  D3 Graph View   │   │  NL Chat Interface       │   │
│  │  - Force layout  │   │  - Suggestion chips      │   │
│  │  - Node expand   │   │  - SQL + data display    │   │
│  │  - Node details  │   │  - Graph node highlights │   │
│  └─────────┬────────┘   └────────────┬─────────────┘   │
└────────────┼───────────────────────────┼────────────────┘
             │ REST API                  │ REST API
             ▼                          ▼
┌─────────────────────────────────────────────────────────┐
│              Flask Backend (Python)                     │
│  GET /api/stats          — Dashboard counts            │
│  GET /api/graph/overview — Graph nodes + edges         │
│  GET /api/graph/expand/  — Expand node neighbors       │
│  POST /api/query         — Direct SQL execution        │
│  POST /api/chat          — NL → SQL → Answer pipeline  │
└──────────────────────┬──────────────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        ▼                             ▼
   SQLite (o2c.db)           Anthropic Claude API
   13 entity tables          claude-sonnet-4-20250514
   graph_edges table         3-step pipeline
```

---

## Database Choice: SQLite

**Rationale:** The dataset is ~2MB with ~18K records across 13 entity types. SQLite gives:
- Zero infrastructure overhead (single file, ships with Python)
- Full SQL power for complex O2C queries (JOINs, aggregations, subqueries)
- Fast enough for this dataset (queries run in <10ms)
- Easy to inspect and debug

A graph database (Neo4j, ArangoDB) would be natural for traversal queries, but given the dataset size and the requirement to translate NL→SQL, a relational DB with a graph_edges materialized view is simpler and equally powerful here. The LLM generates SQL, not Cypher.

---

## Graph Modeling

### Nodes (entity types)
| Type | Count | Description |
|---|---|---|
| SalesOrder | 100 | Sales order headers |
| Customer | 8 | Business partners |
| BillingDocument | 80 | Cancellation billing docs |
| Delivery | 86 | Outbound delivery headers |
| Plant | 44 | Production/shipping plants |
| JournalEntry | 123 | AR accounting entries |
| Payment | 120 | Payment receipts |
| Material | 167 (unique) | Product materials from SO items |

### Edges (1,354 total)
| Relationship | Count | Notes |
|---|---|---|
| SalesOrder → Delivery | 200 | Inferred: same date + plant |
| SalesOrder → SalesOrderItem | 167 | Direct FK |
| SalesOrderItem → Material | 167 | Direct FK |
| SalesOrderItem → Plant | 167 | productionPlant field |
| JournalEntry → Customer | 123 | Direct FK |
| JournalEntry → Payment | 120 | clearingAccountingDocument |
| SalesOrder → Customer | 100 | soldToParty FK |
| Delivery → Plant | 86 | shippingPoint FK |
| BillingDocument → Customer | 80 | soldToParty FK |
| BillingDocument → JournalEntry | 64 | referenceDocument FK |

### Design decisions
- **No direct SO→BillingDocument FK in dataset** — the O2C flow is reconstructed via shared customer + journal linkages
- Delivery→SalesOrder is inferred (same date + same plant), not stored as a FK in the raw data
- The `graph_edges` table is pre-materialized at ingest time for fast graph traversal

---

## LLM Integration & Prompting Strategy

### Pipeline (3 steps per query)
```
User NL → Step 1: LLM generates SQL + insight JSON
         → Step 2: Execute SQL against SQLite
         → (if error) Step 2b: LLM auto-corrects SQL
         → Step 3: LLM formulates final NL answer from real results
```

### Why 3 steps?
- Step 1 generates the query without knowing results (avoids hallucinating answers)
- Step 2 grounds the response in real data
- Step 3 ensures the final answer is specific and accurate (mentions actual names, numbers)

### Prompt design
- Full schema description with all tables, PKs, FKs, and semantic notes
- Explicit JOIN path guidance (e.g., "referenceDocument = billingDocument")
- Response format enforced as JSON `{sql, insight, highlighted_nodes}`
- Multi-turn history (last 8 turns) for conversation continuity
- Temperature: default (balanced between creativity and accuracy)

### Model: claude-sonnet-4-20250514
Fast enough for interactive use, capable enough for complex multi-table SQL generation.

---

## Guardrails

The system enforces domain restriction at the LLM prompt level:

```python
# In SYSTEM_PROMPT:
"If asked anything outside this O2C dataset domain, respond with EXACTLY:
GUARDRAIL: This system only answers questions about the SAP Order-to-Cash dataset..."
```

The backend then checks for the `GUARDRAIL:` prefix and short-circuits to return the refusal message without SQL execution.

**Tested against:**
- General knowledge questions ("What is the capital of France?")
- Coding help ("Write me a Python function")
- Creative writing ("Tell me a story")
- Opinion questions ("What is the best database?")

---

## Setup & Running

### Prerequisites
- Python 3.8+
- ANTHROPIC_API_KEY environment variable

### Install
```bash
git clone https://github.com/AbhishekArjun/o2c-graph-intelligence
cd o2c-graph-intelligence

# Install Python dependencies
pip install flask flask-cors anthropic

# Build the database (first time only)
python backend/ingest.py
```

### Run
```bash
export ANTHROPIC_API_KEY=your_key_here

# Start backend
python backend/app.py
# → Running on http://localhost:5001

# Open frontend
open frontend/index.html
# Or serve with: python -m http.server 8080 --directory frontend
```

### Deployment
See `render.yaml` for one-click Render deployment.

---

## Example Queries the System Answers

**a. Products with most billing documents**
```sql
SELECT pd.productDescription, COUNT(DISTINCT b.billingDocument) as billing_count
FROM billing_documents b
JOIN journal_entry_items j ON j.referenceDocument = b.billingDocument
JOIN sales_order_headers s ON s.soldToParty = b.soldToParty
JOIN sales_order_items si ON si.salesOrder = s.salesOrder
JOIN product_descriptions pd ON pd.product = si.material
GROUP BY pd.product ORDER BY billing_count DESC LIMIT 10
```

**b. Full flow trace for a billing document**
```sql
SELECT 
  b.billingDocument, b.soldToParty, bp.businessPartnerName,
  b.totalNetAmount, b.billingDocumentDate,
  j.accountingDocument, j.amountInTransactionCurrency,
  p.clearingAccountingDocument, p.clearingDate
FROM billing_documents b
JOIN business_partners bp ON bp.businessPartner = b.soldToParty
LEFT JOIN journal_entry_items j ON j.referenceDocument = b.billingDocument
LEFT JOIN payments p ON p.accountingDocument = j.accountingDocument
WHERE b.billingDocument = '90504219'
```

**c. Broken/incomplete O2C flows**
```sql
-- Sales orders with no associated journal entries (potential billing gap)
SELECT s.salesOrder, s.soldToParty, s.totalNetAmount, s.creationDate
FROM sales_order_headers s
WHERE NOT EXISTS (
  SELECT 1 FROM journal_entry_items j
  WHERE j.customer = s.soldToParty
  AND DATE(j.postingDate) >= DATE(s.creationDate)
)
ORDER BY s.totalNetAmount DESC LIMIT 20
```

---

## File Structure

```
o2c-graph-intelligence/
├── backend/
│   ├── app.py          # Flask API server
│   ├── ingest.py       # Data ingestion + graph construction
│   └── o2c.db          # SQLite database (generated)
├── frontend/
│   └── index.html      # Single-file SPA (D3 + vanilla JS)
├── dataset/            # Raw JSONL files (not committed)
├── start.sh            # Convenience startup script
├── render.yaml         # Render deployment config
└── README.md
```

---

## Bonus Features Implemented

- [x] Natural language to SQL translation (dynamic, not templated)
- [x] Highlighting graph nodes referenced in chat responses
- [x] Conversation memory (multi-turn context, last 8 turns)
- [x] Auto-correction: if SQL fails, LLM rewrites and retries
- [x] Node expansion: double-click any node to load its graph neighbors
- [x] Table explorer: browse raw entities without writing SQL
- [x] Node detail panel: click any node to inspect its properties

---

## AI Coding Session

Built using Claude (claude.ai) — session transcript included in `ai-session-log.md`.

Key architectural decisions made with AI assistance:
1. Schema normalization strategy for JSONL → SQLite
2. Graph edge materialization approach
3. 3-step LLM pipeline design (SQL generation → execution → NL answer)
4. Guardrail implementation pattern
