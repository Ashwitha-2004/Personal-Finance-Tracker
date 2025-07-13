import streamlit as st
import pandas as pd
import sqlite3
import joblib
from datetime import date
from io import BytesIO
import openpyxl
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
from PIL import Image

# Load ML model
model = joblib.load("model/category_predictor.pkl")

# Connect to SQLite DB
conn = sqlite3.connect("data/expenses.db", check_same_thread=False)
c = conn.cursor()

# Create tables if not exist
c.execute('''CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    description TEXT,
    amount REAL,
    category TEXT,
    mood TEXT
)''')
c.execute('''CREATE TABLE IF NOT EXISTS incomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    source TEXT,
    amount REAL
)''')
c.execute("DROP TABLE IF EXISTS shared_goals")
c.execute('''CREATE TABLE IF NOT EXISTS shared_goals (
    name TEXT, target REAL, saved REAL
)''')
conn.commit()

# Helper functions
def add_expense(date, description, amount, category, mood):
    c.execute("INSERT INTO expenses (date, description, amount, category, mood) VALUES (?, ?, ?, ?, ?)",
              (date, description, amount, category, mood))
    conn.commit()

def add_income(date, source, amount):
    c.execute("INSERT INTO incomes (date, source, amount) VALUES (?, ?, ?)",
              (date, source, amount))
    conn.commit()

def get_expenses():
    return pd.read_sql_query("SELECT * FROM expenses ORDER BY date DESC", conn)

def get_incomes():
    return pd.read_sql_query("SELECT * FROM incomes ORDER BY date DESC", conn)

def get_balance():
    income = pd.read_sql("SELECT SUM(amount) AS total FROM incomes", conn)["total"].values[0]
    expense = pd.read_sql("SELECT SUM(amount) AS total FROM expenses", conn)["total"].values[0]
    return (income or 0) - (expense or 0)

# Streamlit UI
st.set_page_config(page_title="🧠 Mood-Based Finance Tracker", layout="centered")
st.title(" Personal Finance Tracker")

# Dashboard summary
col1, col2, col3 = st.columns(3)
with col1:
    total_income = pd.read_sql("SELECT SUM(amount) as total FROM incomes", conn)["total"].values[0] or 0
    st.metric("Total Income", f"₹{total_income:,.2f}")
with col2:
    total_expense = pd.read_sql("SELECT SUM(amount) as total FROM expenses", conn)["total"].values[0] or 0
    st.metric("Total Expenses", f"₹{total_expense:,.2f}")
with col3:
    st.metric("Balance", f"₹{get_balance():,.2f}", delta_color="inverse")

st.divider()

# Add Income
with st.expander("➕ Add Income"):
    with st.form("income_form"):
        income_date = st.date_input("Income Date", value=date.today())
        income_source = st.text_input("Source")
        income_amount = st.number_input("Amount (₹)", min_value=1.0)
        submitted = st.form_submit_button("Add Income")
        if submitted and income_source:
            add_income(str(income_date), income_source, income_amount)
            st.success("✅ Income added!")

# Add Expense
with st.expander("➖ Add Expense"):
    with st.form("expense_form"):
        expense_date = st.date_input("Expense Date", value=date.today())
        description = st.text_input("Description")
        amount = st.number_input("Amount (₹)", min_value=1.0)
        mood = st.selectbox("Mood", ["🙂", "😐", "😞"])
        submitted = st.form_submit_button("Add Expense")
        if submitted and description:
            predicted_category = model.predict([description])[0]
            add_expense(str(expense_date), description, amount, predicted_category, mood)

            # Impulse spending detector
            c.execute("SELECT COUNT(*) FROM expenses WHERE date = ?", (str(expense_date),))
            count_today = c.fetchone()[0]
            if count_today >= 3:
                st.warning("⚠️ Multiple expenses today. Are you impulse spending? Try a 10-minute lockout.")

            st.success(f"✅ Added under: {predicted_category}")

# Scan Bill and Add Expense
with st.expander("🗞 Scan Paid Bill to Add Expense"):
    uploaded_image = st.file_uploader("Upload Bill Image", type=["png", "jpg", "jpeg"])
    if uploaded_image:
        image = Image.open(uploaded_image)
        extracted_text = pytesseract.image_to_string(image)
        st.text_area("Extracted Text", extracted_text, height=150)

        # Simple parsing for amount and description (demo purpose)
        import re
        amount_match = re.search(r'\₹?\s?(\d+[.,]?\d*)', extracted_text)
        found_amount = float(amount_match.group(1).replace(',', '')) if amount_match else 0.0

        description_guess = extracted_text.splitlines()[0] if extracted_text else "Bill Scan"

        if st.button("Add from Bill"):
            predicted_category = model.predict([description_guess])[0]
            add_expense(str(date.today()), description_guess, found_amount, predicted_category, mood="🙂")
            st.success("✅ Expense added from scanned bill!")

# Load data
df_exp = get_expenses()
df_inc = get_incomes()

# Mood-based insights
st.subheader("🧠 Mood-Based Insights")
if not df_exp.empty:
    selected_mood = st.selectbox("Filter Mood", ["All", "🙂", "😐", "😞"])
    df_filtered = df_exp if selected_mood == "All" else df_exp[df_exp["mood"] == selected_mood]
    st.markdown(f"### Transactions ({selected_mood})")
    st.dataframe(df_filtered.drop(columns=["id"]), use_container_width=True)

    st.markdown("### Spend by Mood")
    mood_chart = df_exp.groupby("mood")["amount"].sum()
    st.bar_chart(mood_chart)

    top_mood = mood_chart.idxmax()
    st.info(f"You spend most when you're feeling {top_mood}.")

    st.markdown("### Mood Over Time")
    mood_time = df_exp.groupby(["date", "mood"])["amount"].sum().unstack().fillna(0)
    st.line_chart(mood_time)

# Tables
st.subheader("📋 Transactions")
col1, col2 = st.columns(2)
with col1:
    st.markdown("#### Income")
    st.dataframe(df_inc.drop(columns=["id"]), use_container_width=True)
with col2:
    st.markdown("#### Expenses")
    st.dataframe(df_exp.drop(columns=["id"]), use_container_width=True)

# Delete Data
st.subheader("🗑️ Manage Data")

with st.expander("Delete Expenses"):
    expense_ids = df_exp["id"].tolist()
    if expense_ids:
        delete_exp_id = st.selectbox("Select Expense ID to delete", expense_ids)
        if st.button("Delete Selected Expense"):
            c.execute("DELETE FROM expenses WHERE id = ?", (delete_exp_id,))
            conn.commit()
            st.success(f"✅ Deleted expense with ID {delete_exp_id}")

with st.expander("Delete Incomes"):
    income_ids = df_inc["id"].tolist()
    if income_ids:
        delete_inc_id = st.selectbox("Select Income ID to delete", income_ids)
        if st.button("Delete Selected Income"):
            c.execute("DELETE FROM incomes WHERE id = ?", (delete_inc_id,))
            conn.commit()
            st.success(f"✅ Deleted income with ID {delete_inc_id}")

# Shared Goals Section
st.subheader("🌟 Shared Goals with Friends")

with st.form("shared_goal_form"):
    goal_name = st.text_input("Goal Name", placeholder="e.g. Goa Trip with Rahul")
    goal_target = st.number_input("Target Amount ₹", min_value=0.0, format="%.2f")
    goal_saved = st.number_input("Already Saved ₹", min_value=0.0, format="%.2f")
    goal_submit = st.form_submit_button("Save Goal")
    if goal_submit and goal_name:
        c.execute("INSERT INTO shared_goals VALUES (?, ?, ?)", (goal_name, goal_target, goal_saved))
        conn.commit()
        st.success("✅ Goal added/updated.")

goals_df = pd.read_sql("SELECT * FROM shared_goals", conn)
for _, row in goals_df.iterrows():
    st.markdown(f"**{row['name']}** — ₹{row['saved']} of ₹{row['target']}")
    st.progress(min(row['saved'] / row['target'], 1.0))

with st.expander("Delete Shared Goal"):
    goal_names = [row["name"] for _, row in goals_df.iterrows()]
    if goal_names:
        selected_goal = st.selectbox("Select Goal to Delete", goal_names)
        if st.button("Delete Goal"):
            c.execute("DELETE FROM shared_goals WHERE name = ?", (selected_goal,))
            conn.commit()
            st.success(f"✅ Deleted goal '{selected_goal}'")

# Export Shared Goals
st.subheader("📅 Export Shared Goals")
if not goals_df.empty:
    output_goals = BytesIO()
    with pd.ExcelWriter(output_goals, engine="openpyxl") as writer:
        goals_df.to_excel(writer, index=False, sheet_name="SharedGoals")
    st.download_button("⬇️ Download Goals Excel", data=output_goals.getvalue(),
                       file_name="shared_goals.xlsx", mime="application/vnd.ms-excel")
else:
    st.info("No shared goals to export.")
