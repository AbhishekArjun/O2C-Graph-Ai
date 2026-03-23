import sqlite3
import ingest

db = "o2c.db"
conn = sqlite3.connect(db)

# 1. Customers
customers = [
    ("CUST_1", "CUST_1", "TechCorp Inc", "TechCorp", "", "", "2025-01-01", 0, 0),
    ("CUST_2", "CUST_2", "Global Solutions", "GlobalSol", "", "", "2025-01-02", 0, 0),
    ("CUST_3", "CUST_3", "Retail Motors", "RetailMot", "", "", "2025-01-03", 0, 0),
]
conn.executemany("INSERT OR REPLACE INTO business_partners VALUES (?,?,?,?,?,?,?,?,?)", customers)

# 2. Plants
plants = [
    ("P100", "New York Plant", "ORG1", "CH1", "A1"),
    ("P200", "London Plant", "ORG1", "CH1", "A2"),
]
conn.executemany("INSERT OR REPLACE INTO plants VALUES (?,?,?,?,?)", plants)

# 3. Products
prods = [
    ("PROD_A", "EN", "High-End Server"),
    ("PROD_B", "EN", "Laptop Pro"),
    ("PROD_C", "EN", "Wireless Mouse")
]
conn.executemany("INSERT OR REPLACE INTO product_descriptions VALUES (?,?,?)", prods)

# 4. Sales Orders
sos = [
    ("SO_1001", "OR", "ORG1", "CH1", "CUST_1", "2025-02-01", "user1", 15000.0, "C", "C", "USD", "2025-02-10", "", "", "", "", ""),
    ("SO_1002", "OR", "ORG1", "CH1", "CUST_2", "2025-02-05", "user1", 2500.0, "C", "C", "USD", "2025-02-12", "", "", "", "", ""),
    ("SO_1003", "OR", "ORG1", "CH1", "CUST_3", "2025-03-01", "user2", 500.0, "A", "A", "USD", "2025-03-10", "", "", "", "", "")
]
conn.executemany("INSERT OR REPLACE INTO sales_order_headers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", sos)

so_items = [
    ("SO_1001", "10", "PROD_A", 2, "PC", 13000.0, "HW", "P100", "L1"),
    ("SO_1001", "20", "PROD_B", 2, "PC", 2000.0, "HW", "P100", "L1"),
    ("SO_1002", "10", "PROD_B", 2, "PC", 2500.0, "HW", "P200", "L2"),
    ("SO_1003", "10", "PROD_C", 10, "PC", 500.0, "ACC", "P100", "L1"),
]
conn.executemany("INSERT OR REPLACE INTO sales_order_items VALUES (?,?,?,?,?,?,?,?,?)", so_items)

# 5. Deliveries
dels = [
    ("DEL_5001", "2025-02-01 10:00", "P100", "C", "C", "C", "", "", "2025-02-02"),
    ("DEL_5002", "2025-02-05 11:00", "P200", "C", "C", "C", "", "", "2025-02-06"),
]
conn.executemany("INSERT OR REPLACE INTO outbound_delivery_headers VALUES (?,?,?,?,?,?,?,?,?)", dels)

# 6. Billing Docs
bills = [
    ("BD_9001", "F2", "2025-02-03", "2025-02-03", 0, "", 15000.0, "USD", "COMP", "2025", "JE_8001", "CUST_1"),
    ("BD_9002", "F2", "2025-02-07", "2025-02-07", 0, "",  2500.0, "USD", "COMP", "2025", "JE_8002", "CUST_2")
]
conn.executemany("INSERT OR REPLACE INTO billing_documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", bills)

# 7. Journal Entries
jes = [
    ("JE_8001", "1", "COMP", "2025", "GL100", "BD_9001", "PR1", "USD", 15000.0, "2025-02-03", "2025-02-03", "CUST_1", "2025-02-15", "PAY_7001"),
    ("JE_8002", "1", "COMP", "2025", "GL100", "BD_9002", "PR1", "USD", 2500.0, "2025-02-07", "2025-02-07", "CUST_2", "2025-02-20", "PAY_7002")
]
conn.executemany("INSERT OR REPLACE INTO journal_entry_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", jes)

# 8. Payments
pays = [
    ("JE_8001", "1", "COMP", "2025", "2025-02-15", "PAY_7001", 15000.0, "USD", "CUST_1", "2025-02-15", "GL200"),
    ("JE_8002", "1", "COMP", "2025", "2025-02-20", "PAY_7002", 2500.0,  "USD", "CUST_2", "2025-02-20", "GL200")
]
conn.executemany("INSERT OR REPLACE INTO payments VALUES (?,?,?,?,?,?,?,?,?,?,?)", pays)

conn.commit()

# Ensure edges are fully populated from the newly inserted tables
ingest.build_edges(conn)
conn.close()

print('Successfully populated database with synthetic data!')
