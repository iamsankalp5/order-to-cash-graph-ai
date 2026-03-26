import streamlit as st
import networkx as nx
import json
import matplotlib.pyplot as plt
import glob
import re
import os
from groq import Groq
from dotenv import load_dotenv
import tempfile
import time

# -------- CONFIG --------
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

G = nx.Graph()

DATA_ROOTS = [".", "Dataset"]

# -------- CLEAN --------
def clean(val):
    return str(val).strip() if val else ""


def iter_data_files(subdir):
    files = []
    for root in DATA_ROOTS:
        files.extend(glob.glob(f"{root}/**/{subdir}/*.jsonl", recursive=True))
    return files

# -------- LOAD DATA --------
def load_data():
    G.clear()

    # -------- SO → PRODUCT --------
    for file in iter_data_files("sales_order_items"):
        with open(file) as f:
            for line in f:
                row = json.loads(line)

                so = clean(row.get("salesOrder"))
                mat = clean(row.get("material"))

                if so:
                    G.add_node(f"SO_{so}", type="SO")

                if mat:
                    G.add_node(f"PROD_{mat}", type="Product")

                if so and mat:
                    G.add_edge(f"SO_{so}", f"PROD_{mat}")

    # -------- DELIVERY → PRODUCT --------
    for file in iter_data_files("outbound_delivery_items"):
        with open(file) as f:
            for line in f:
                row = json.loads(line)

                delivery = clean(row.get("deliveryDocument"))
                ref_so = clean(row.get("referenceSdDocument"))
                mat = clean(row.get("material"))

                if delivery:
                    G.add_node(f"DEL_{delivery}", type="Delivery")

                if ref_so:
                    G.add_node(f"SO_{ref_so}", type="SO")
                    G.add_edge(f"SO_{ref_so}", f"DEL_{delivery}")

                if mat:
                    G.add_node(f"PROD_{mat}", type="Product")

                if delivery and mat:
                    G.add_edge(f"DEL_{delivery}", f"PROD_{mat}")

    # -------- INVOICE → PRODUCT --------
    for file in iter_data_files("billing_document_items"):
        with open(file) as f:
            for line in f:
                row = json.loads(line)

                invoice = clean(row.get("billingDocument"))
                ref_delivery = clean(row.get("referenceSdDocument"))
                mat = clean(row.get("material"))

                if invoice:
                    G.add_node(f"INV_{invoice}", type="Invoice")

                if ref_delivery:
                    G.add_node(f"DEL_{ref_delivery}", type="Delivery")
                    G.add_edge(f"DEL_{ref_delivery}", f"INV_{invoice}")

                if mat:
                    G.add_node(f"PROD_{mat}", type="Product")

                if invoice and mat:
                    G.add_edge(f"INV_{invoice}", f"PROD_{mat}")

    # -------- JOURNAL → INVOICE --------
    for file in iter_data_files("journal_entry_items_accounts_receivable"):
        with open(file) as f:
            for line in f:
                row = json.loads(line)

            journal = clean(row.get("accountingDocument"))
            ref = clean(row.get("referenceDocument"))

            if journal:
                G.add_node(
                    f"JE_{journal}",
                    type="Journal",
                    companyCode=row.get("companyCode"),
                    fiscalYear=row.get("fiscalYear"),
                    accountingDocument=row.get("accountingDocument"),
                    referenceDocument=row.get("referenceDocument"),
                    amount=row.get("amountInTransactionCurrency"),
                    currency=row.get("transactionCurrency"),
                    postingDate=row.get("postingDate"),
                    documentDate=row.get("documentDate"),
                    glAccount=row.get("glAccount")
                )

            if ref:
                G.add_node(f"INV_{ref}", type="Invoice")

            if journal and ref:
                G.add_edge(f"JE_{journal}", f"INV_{ref}")


# Load graph
load_data()

# -------- DRAW GRAPH (NO SCIPY ERROR) --------
def draw_graph(highlight_nodes=None):
    if len(G.nodes()) == 0:
        st.warning("No graph data found.")
        return

    from pyvis.network import Network
    import streamlit.components.v1 as components
    import tempfile
    import time

    # ✅ Bigger graph (important for UI)
    net = Network(
        height="850px",   # 🔥 increased
        width="100%",
        bgcolor="#ffffff",
        font_color="black",
        notebook=False
    )

    # ✅ Physics
    net.barnes_hut()

    # ✅ Styling (slightly improved visibility)
    net.set_options("""
    {
      "nodes": {
        "shape": "dot",
        "size": 20,
        "font": { "size": 10, "color": "#000000" }
      },
      "edges": {
        "width": 1,
        "color": { "opacity": 0.6 }
      },
      "interaction": {
        "hover": true,
        "zoomView": true,
        "dragView": true
      }
    }
    """)

    # ✅ Add nodes
    for node in G.nodes():

        if node.startswith("SO_"):
            color = "green"
            label = "Sales Order"
        elif node.startswith("DEL_"):
            color = "blue"
            label = "Delivery"
        elif node.startswith("INV_"):
            color = "red"
            label = "Invoice"
        elif node.startswith("JE_"):
            color = "purple"
            label = "Journal"
        else:
            color = "orange"
            label = "Product"

        data = G.nodes[node]

        # ✅ Tooltip
        title = f"{label}\n\n"
        title += f"ID: {node}\n"

        if data.get("companyCode"):
            title += f"Company Code: {data.get('companyCode')}\n"
        if data.get("fiscalYear"):
            title += f"Fiscal Year: {data.get('fiscalYear')}\n"
        if data.get("accountingDocument"):
            title += f"Accounting Doc: {data.get('accountingDocument')}\n"
        if data.get("referenceDocument"):
            title += f"Reference Doc: {data.get('referenceDocument')}\n"
        if data.get("amount"):
            title += f"Amount: {data.get('amount')} {data.get('currency')}\n"
        if data.get("postingDate"):
            title += f"Posting Date: {data.get('postingDate')}\n"

        title += f"Connections: {len(list(G.neighbors(node)))}"

        # ✅ Highlight logic
        is_highlighted = highlight_nodes and node in highlight_nodes

        net.add_node(
            node,
            label=node,
            title=title,
            color="gold" if is_highlighted else color,
            size=35 if is_highlighted else 20,
            borderWidth=4 if is_highlighted else 1
        )

    # ✅ Add edges
    for u, v in G.edges():
        net.add_edge(u, v)

    # ✅ Save & render (FIXED INDENTATION ONLY)
    tmp_file = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=f"_{time.time()}.html"
    )

    net.save_graph(tmp_file.name)

    with open(tmp_file.name, "r", encoding="utf-8") as f:
        html = f.read()

    components.html(html, height=850)

    st.set_page_config(layout="wide")


# Load data
load_data()
# -------- TRACE FUNCTION --------
def trace_so(so_id):
    result = {
        "SO": so_id,
        "DELIVERY": [],
        "INVOICE": [],
        "JOURNAL": [],
        "NOTE": ""
    }

    if so_id not in G:
        return result

    deliveries = set()
    invoices = set()
    journals = set()

    for n in G.neighbors(so_id):
        if n.startswith("DEL_"):
            deliveries.add(n)
        if n.startswith("INV_"):
            invoices.add(n)

    # delivery -> invoice
    for d in list(deliveries):
        for n in G.neighbors(d):
            if n.startswith("INV_"):
                invoices.add(n)

    # invoices → journal
    for inv in invoices:
        for n in G.neighbors(inv):
            if n.startswith("JE_"):
                journals.add(n)

    result["DELIVERY"] = list(deliveries)
    result["INVOICE"] = list(invoices)
    result["JOURNAL"] = list(journals)

    if deliveries and not invoices:
        result["NOTE"] = "Delivery exists but no billing document is linked in the dataset for this sales order."
    elif invoices and not journals:
        result["NOTE"] = "Billing document exists but no journal entry is linked in the dataset for this sales order."
    elif not deliveries:
        result["NOTE"] = "No delivery document is linked in the dataset for this sales order."

    return result


def trace_invoice(inv_id):
    result = {
        "INVOICE": inv_id,
        "SO": [],
        "DELIVERY": [],
        "JOURNAL": []
    }

    if inv_id not in G:
        return result

    deliveries = set()
    sales_orders = set()
    journals = set()

    for n in G.neighbors(inv_id):
        if n.startswith("DEL_"):
            deliveries.add(n)
        if n.startswith("JE_"):
            journals.add(n)

    for d in deliveries:
        for n in G.neighbors(d):
            if n.startswith("SO_"):
                sales_orders.add(n)

    result["SO"] = list(sales_orders)
    result["DELIVERY"] = list(deliveries)
    result["JOURNAL"] = list(journals)
    return result


def top_products_by_billing(limit=10):
    product_counts = []
    for n in G.nodes():
        if not n.startswith("PROD_"):
            continue
        inv_count = len([x for x in G.neighbors(n) if x.startswith("INV_")])
        if inv_count > 0:
            product_counts.append({"product": n, "billing_docs": inv_count})

    product_counts.sort(key=lambda x: x["billing_docs"], reverse=True)
    return product_counts[:limit]


def broken_or_incomplete_flows(limit=20):
    issues = []
    for so in G.nodes():
        if not so.startswith("SO_"):
            continue

        deliveries = {x for x in G.neighbors(so) if x.startswith("DEL_")}
        invoices = {x for x in G.neighbors(so) if x.startswith("INV_")}

        for d in deliveries:
            invoices.update({x for x in G.neighbors(d) if x.startswith("INV_")})

        if deliveries and not invoices:
            issues.append({"sales_order": so, "issue": "delivered_but_not_billed"})
        elif invoices and not deliveries:
            issues.append({"sales_order": so, "issue": "billed_without_delivery"})

    return issues[:limit]


def dataset_overview():
    return {
        "entities": [
            "sales_order_headers", "sales_order_items",
            "outbound_delivery_headers", "outbound_delivery_items",
            "billing_document_headers", "billing_document_items",
            "journal_entry_items_accounts_receivable",
            "payments_accounts_receivable",
            "products", "business_partners", "business_partner_addresses"
        ],
        "core_flow": "Sales Order -> Delivery -> Billing Document -> Journal Entry",
        "link_keys": {
            "SO_to_DEL": "outbound_delivery_items.referenceSdDocument -> sales_order.salesOrder",
            "DEL_to_INV": "billing_document_items.referenceSdDocument -> outbound_delivery.deliveryDocument",
            "INV_to_JE": "journal_entry_items_accounts_receivable.referenceDocument -> billing_document.billingDocument"
        },
        "graph_nodes": int(len(G.nodes())),
        "graph_edges": int(len(G.edges()))
    }


def graph_summary():
    counts = {
        "SO": 0,
        "DEL": 0,
        "INV": 0,
        "JE": 0,
        "PROD": 0,
        "OTHER": 0
    }

    for n in G.nodes():
        if n.startswith("SO_"):
            counts["SO"] += 1
        elif n.startswith("DEL_"):
            counts["DEL"] += 1
        elif n.startswith("INV_"):
            counts["INV"] += 1
        elif n.startswith("JE_"):
            counts["JE"] += 1
        elif n.startswith("PROD_"):
            counts["PROD"] += 1
        else:
            counts["OTHER"] += 1

    return {
        "node_counts": counts,
        "total_nodes": int(len(G.nodes())),
        "total_edges": int(len(G.edges())),
        "sample_questions": [
            "Trace flow for sales order SO_740510",
            "Trace invoice INV_90504206",
            "Which products have highest billing documents?",
            "Identify broken or incomplete flows",
            "Explain the dataset schema"
        ]
    }


def summarize_so_status(trace_result):
    so = trace_result.get("SO", "")
    deliveries = trace_result.get("DELIVERY", [])
    invoices = trace_result.get("INVOICE", [])
    journals = trace_result.get("JOURNAL", [])
    note = trace_result.get("NOTE", "")

    if deliveries and invoices and journals:
        return (
            f"Yes, {so} is fully processed. "
            f"Delivery, billing, and journal posting are all available in the dataset."
        )

    if deliveries and invoices and not journals:
        return (
            f"{so} is partially processed: delivery and billing exist, "
            f"but journal posting is not linked yet."
        )

    if deliveries and not invoices:
        return (
            f"{so} is not fully processed yet: delivery exists, "
            f"but billing is not linked."
        )

    if not deliveries:
        return f"{so} is not fully processed yet: no delivery link is available."

    return note or f"Could not determine full processing status for {so}."


def summarize_invoice_status(inv_result):
    inv = inv_result.get("INVOICE", "")
    so = inv_result.get("SO", [])
    deliveries = inv_result.get("DELIVERY", [])
    journals = inv_result.get("JOURNAL", [])

    if so and deliveries and journals:
        return f"{inv} is fully traceable: linked Sales Order, Delivery, and Journal Entry are available."
    if deliveries and journals:
        return f"{inv} is processed to finance, but upstream Sales Order link is missing in the graph." 
    if deliveries and not journals:
        return f"{inv} has delivery linkage but journal posting is not linked yet."
    return f"{inv} has limited linkage in current dataset."


def infer_entity_from_text(text):
    t = text.lower()
    if any(k in t for k in ["delivery", "deliveries", "dilevery", "del"]):
        return "DELIVERY"
    if any(k in t for k in ["invoice", "invoices", "billing", "bill"]):
        return "INVOICE"
    if any(k in t for k in ["journal", "journals", "je"]):
        return "JOURNAL"
    if any(k in t for k in ["product", "products", "material", "materials"]):
        return "PRODUCT"
    return ""


def count_entity_for_so(so_id, entity):
    trace_result = trace_so(so_id)
    entity = (entity or "").upper()

    if entity == "DELIVERY":
        return len(trace_result.get("DELIVERY", []))
    if entity == "INVOICE":
        return len(trace_result.get("INVOICE", []))
    if entity == "JOURNAL":
        return len(trace_result.get("JOURNAL", []))
    if entity == "PRODUCT":
        if so_id not in G:
            return 0
        return len([n for n in G.neighbors(so_id) if n.startswith("PROD_")])
    return 0


def entity_counts_for_so(so_id):
    return {
        "DELIVERY": count_entity_for_so(so_id, "DELIVERY"),
        "INVOICE": count_entity_for_so(so_id, "INVOICE"),
        "JOURNAL": count_entity_for_so(so_id, "JOURNAL"),
        "PRODUCT": count_entity_for_so(so_id, "PRODUCT")
    }


def should_include_entity_ids(text):
    t = (text or "").lower()
    return any(k in t for k in ["which", "list", "show", "what are", "give me", "also show"])


def list_entity_for_so(so_id, entity):
    entity = (entity or "").upper()
    trace_result = trace_so(so_id)

    if entity == "DELIVERY":
        return sorted(trace_result.get("DELIVERY", []))
    if entity == "INVOICE":
        return sorted(trace_result.get("INVOICE", []))
    if entity == "JOURNAL":
        return sorted(trace_result.get("JOURNAL", []))
    if entity == "PRODUCT":
        if so_id not in G:
            return []
        return sorted([n for n in G.neighbors(so_id) if n.startswith("PROD_")])
    return []


def is_domain_question(query):
    text = query.lower()
    keywords = [
        "sales order", "order", "delivery", "invoice", "billing", "journal",
        "payment", "product", "material", "flow", "document", "customer",
        "dataset", "graph", "schema", "table", "entity", "column", "relationship"
    ]
    return any(k in text for k in keywords) or bool(re.search(r"\b(?:so|inv|del|je)_?\d+\b", text, re.IGNORECASE))


def extract_prefixed_id(query, prefix):
    m = re.search(rf"\b{prefix}_?(\d+)\b", query, re.IGNORECASE)
    if not m:
        return ""
    return f"{prefix.upper()}_{m.group(1)}"


def normalize_id(id_value):
    raw = (id_value or "").strip()
    if not raw:
        return ""
    m = re.match(r"^(SO|INV)_?(\d+)$", raw, re.IGNORECASE)
    if m:
        return f"{m.group(1).upper()}_{m.group(2)}"
    return raw

# -------- LLM INTENT ROUTER --------
# -------- MULTI-ENTITY DETECTION --------
def infer_entities_from_text(text):
    t = text.lower()
    entities = []

    if any(k in t for k in ["delivery", "deliveries", "del"]):
        entities.append("DELIVERY")

    if any(k in t for k in ["invoice", "invoices", "billing", "bill"]):
        entities.append("INVOICE")

    if any(k in t for k in ["journal", "journals", "je"]):
        entities.append("JOURNAL")

    if any(k in t for k in ["product", "products", "material"]):
        entities.append("PRODUCT")

    return entities


# -------- MAIN LLM ROUTER --------
def llm_to_query(user_query):
    query = user_query.lower().strip()

    # Extract IDs
    so_id = extract_prefixed_id(query, "SO")
    inv_id = extract_prefixed_id(query, "INV")

    # Detect entities
    entities = infer_entities_from_text(query)

    # Get last SO for follow-up
    last_so = st.session_state.get("last_so_id", "")

    # -------- SALES ORDER --------
    if so_id:
        return {
            "action": "COUNT_ENTITY_SO_MULTI" if entities else "TRACE_FLOW_SO",
            "id": so_id,
            "entities": entities,
            "include_ids": True
        }

    # -------- INVOICE --------
    if inv_id:
        return {"action": "TRACE_FLOW_INV", "id": inv_id}

    # -------- FOLLOW-UP (FIXED) --------
    if not so_id and not inv_id and last_so:

        # Multi-entity follow-up
        if entities:
            return {
                "action": "COUNT_ENTITY_SO_MULTI",
                "id": last_so,
                "entities": entities,
                "include_ids": True
            }

        # Status follow-up
        if any(k in query for k in ["status", "process", "state"]):
            return {"action": "TRACE_FLOW_SO", "id": last_so}

        # Vague follow-up
        followup_keywords = ["also", "and", "what about", "then", "next"]
        if any(k in query for k in followup_keywords):
            return {"action": "TRACE_FLOW_SO", "id": last_so}

    # -------- GENERAL --------
    if "top products" in query:
        return {"action": "TOP_PRODUCTS_BY_BILLING"}

    if "broken" in query or "issue" in query:
        return {"action": "BROKEN_FLOWS"}

    if "dataset" in query or "schema" in query:
        return {"action": "DATASET_OVERVIEW"}

    if "summary" in query or "graph" in query:
        return {"action": "GRAPH_SUMMARY"}

    # -------- FALLBACK TO LLM --------
    if client:
        try:
            prompt = f"""
            Convert user query into JSON.

            Actions:
            TRACE_FLOW_SO, TRACE_FLOW_INV, COUNT_ENTITY_SO_MULTI,
            TOP_PRODUCTS_BY_BILLING, BROKEN_FLOWS,
            DATASET_OVERVIEW, GRAPH_SUMMARY

            Query: "{user_query}"

            Output JSON only.
            """

            response = client.chat.completions.create(
                model="llama3-70b-8192",
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )

            return json.loads(response.choices[0].message.content)

        except:
            pass

    # -------- DEFAULT --------
    return {"action": "GRAPH_SUMMARY"}
# -------- UI --------
# -------- UI --------
st.title("🚀 Order-to-Cash Graph AI")
st.write(f"Nodes: {len(G.nodes())}, Edges: {len(G.edges())}")

# Initialize session state
if "last_so_id" not in st.session_state:
    st.session_state["last_so_id"] = ""

if "highlight_nodes" not in st.session_state:
    st.session_state["highlight_nodes"] = []

col1, col2 = st.columns([3, 1])

with col1:
    st.subheader("Graph")
    highlight_nodes = st.session_state.get("highlight_nodes", [])
    st.write("Highlight nodes:", highlight_nodes)
    draw_graph(highlight_nodes)

with col2:
    st.subheader("Chat with Graph")
    st.markdown("🟢 Dodge AI is awaiting instructions")

    query = st.text_input(
        "Ask your query",
        key="chat_input",
        placeholder="e.g. Give me invoices and journals of SO_740510"
    )

    if st.button("Send", key="send_btn"):
        if not query or not query.strip():
            st.warning("Please enter a question.")
        else:
            with st.spinner("Thinking..."):
                try:
                    # ✅ LLM call
                    q = llm_to_query(query)
                    action = q.get("action", "")

                    # 🔥 Save last SO
                    if action in ["COUNT_ENTITY_SO_MULTI", "TRACE_FLOW_SO"]:
                        if q.get("id"):
                            st.session_state["last_so_id"] = q["id"]

                    # -------- TRACE SO --------
                    if action == "TRACE_FLOW_SO":
                        so = q.get("id", "")
                        if so:
                            result = trace_so(so)
                            st.success(summarize_so_status(result))

                            if st.checkbox("Show raw result"):
                                st.json(result)

                    # -------- MULTI-ENTITY --------
                    elif action == "COUNT_ENTITY_SO_MULTI":
                        so = q.get("id", "")
                        entities = q.get("entities", [])

                        if so and entities:
                            st.session_state["last_so_id"] = so

                            results = []

                            for entity in entities:
                                total = count_entity_for_so(so, entity)
                                ids = list_entity_for_so(so, entity)

                                if ids:
                                    if total == 1:
                                        results.append(f"1 {entity.lower()} → {ids[0]}")
                                    else:
                                        results.append(f"{total} {entity.lower()}s → {', '.join(ids)}")
                                else:
                                    results.append(f"No {entity.lower()} found")

                            trace = trace_so(so)
                            status = summarize_so_status(trace)

                            final_response = (
                                f"Here’s the breakdown for {so}:\n\n"
                                + "\n".join(results)
                                + f"\n\n👉 {status}"
                            )

                            st.success(final_response)

                    # -------- SINGLE ENTITY --------
                    elif action == "COUNT_ENTITY_SO":
                        so = q.get("id", "")
                        entity = (q.get("entity", "") or "").upper()

                        if so:
                            st.session_state["last_so_id"] = so

                            total = count_entity_for_so(so, entity)
                            ids = list_entity_for_so(so, entity)

                            if ids:
                                st.success(
                                    f"{so} has {total} {entity.lower()}(s): {', '.join(ids)}"
                                )
                            else:
                                st.warning(f"No {entity.lower()} found for {so}")

                    # -------- TRACE INVOICE --------
                    elif action == "TRACE_FLOW_INV":
                        inv = q.get("id", "")
                        if inv:
                            result = trace_invoice(inv)
                            st.success(summarize_invoice_status(result))

                            journals = result.get("JOURNAL", [])

                            if journals:
                                je_number = journals[0].replace("JE_", "")

                                st.success(
                                    f"The journal entry number linked to billing document {inv.replace('INV_', '')} is {je_number}."
                                )

                                # ✅ Highlight node
                                st.session_state["highlight_nodes"] = journals
                                
                    # -------- ANALYTICS --------
                    elif action == "TOP_PRODUCTS_BY_BILLING":
                        data = top_products_by_billing(limit=10)
                        st.success("Top 10 Products by Billing Documents")
                        st.dataframe(data)

                    elif action == "BROKEN_FLOWS":
                        data = broken_or_incomplete_flows(limit=20)
                        st.success("Potentially Broken or Incomplete Flows")
                        st.write(data)

                    # -------- DATASET --------
                    elif action == "DATASET_OVERVIEW":
                        st.success("Dataset Overview")
                        st.write(dataset_overview())

                    elif action == "GRAPH_SUMMARY":
                        summary = graph_summary()
                        st.success(
                            f"Graph Summary: {summary['total_nodes']} nodes, {summary['total_edges']} edges"
                        )
                        st.write(summary)

                    # -------- FALLBACK --------
                    else:
                        st.info("Try: Give me invoices and journals of SO_740510")

                except Exception as e:
                    st.error(f"Error: {str(e)}")