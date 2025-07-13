# app.py
import streamlit as st
import joblib

# Load trained model
model = joblib.load("model/category_predictor.pkl")

st.set_page_config(page_title="Smart Finance Categorizer", layout="centered")

st.title("🔮 Smart Expense Categorizer")
st.markdown("Enter a transaction description and get a predicted category.")

# Input field
user_input = st.text_input("Transaction Description", placeholder="e.g. Uber ride, Starbucks coffee")

# Predict button
if st.button("Predict Category") and user_input:
    predicted = model.predict([user_input])[0]
    st.success(f"📌 Predicted Category: **{predicted}**")
