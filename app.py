import streamlit as st
from dotenv import load_dotenv
import os, re, sqlite3, hashlib
import google.generativeai as genai
from PIL import Image
from io import BytesIO
from datetime import datetime
import matplotlib.pyplot as plt

# PDF
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ------------------------------
# PAGE CONFIG
# ------------------------------
st.set_page_config(page_title="NutriVision", page_icon="🥗", layout="wide")

# ------------------------------
# DARK UI
# ------------------------------
st.markdown("""
<style>
html, body, [class*="css"] {
    background:#0E1117 !important;
    color:#EAEAEA !important;
}
.stApp {
    background: linear-gradient(135deg,#0f2027,#203a43,#2c5364);
}
section[data-testid="stSidebar"] {
    background:#000;
}
section[data-testid="stSidebar"] * {
    color:#EAEAEA !important;
}
input {
    background:#1E1E1E !important;
    color:#EAEAEA !important;
}
.stButton>button {
    background:linear-gradient(90deg,#00c6ff,#0072ff);
    color:white !important;
    font-size:16px;
    font-weight:700;
    border-radius:14px;
}
.food-box {
    background:#121212;
    padding:25px;
    border-radius:18px;
    box-shadow:0 0 25px rgba(0,255,255,.2);
    white-space:pre-wrap;
}
</style>
""", unsafe_allow_html=True)

# ------------------------------
# DATABASE
# ------------------------------
DB = "nutrivision.db"

def db():
    return sqlite3.connect(DB)

def init_db():
    con = db()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            username TEXT PRIMARY KEY,
            password TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            date TEXT,
            meal TEXT,
            details TEXT,
            calories INTEGER
        )
    """)
    con.commit()
    con.close()

init_db()

# ------------------------------
# AUTH
# ------------------------------
def hash_pass(p):
    return hashlib.sha256(p.encode()).hexdigest()

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""
if "daily_used" not in st.session_state:
    st.session_state.daily_used = 0

# ------------------------------
# API KEY
# ------------------------------
load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# ------------------------------
# LOGIN
# ------------------------------
if not st.session_state.logged_in:
    st.markdown("## 🔐 NutriVision Authentication")
    t1, t2 = st.tabs(["Login", "Create Account"])

    with t1:
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Login"):
            con = db(); cur = con.cursor()
            cur.execute("SELECT password FROM users WHERE username=?", (u,))
            r = cur.fetchone(); con.close()
            if r and r[0] == hash_pass(p):
                st.session_state.logged_in = True
                st.session_state.username = u
                st.session_state.daily_used = 0
                st.rerun()
            else:
                st.error("Invalid username or password")

    with t2:
        nu = st.text_input("New Username")
        np = st.text_input("New Password", type="password")
        cp = st.text_input("Confirm Password", type="password")
        if st.button("Create Account"):
            if np != cp:
                st.error("Passwords do not match")
            else:
                try:
                    con = db(); cur = con.cursor()
                    cur.execute("INSERT INTO users VALUES (?,?)", (nu, hash_pass(np)))
                    con.commit(); con.close()
                    st.success("Account created! Login now.")
                except:
                    st.error("Username already exists")

    st.stop()

# ==========================================================
# ================== MAIN APP (AFTER LOGIN) =================
# ==========================================================

# ------------------------------
# SIDEBAR
# ------------------------------
st.sidebar.title("📤 Upload Food / Beverage")
img = st.sidebar.file_uploader("Food Image", ["jpg","jpeg","png"])
qty = st.sidebar.text_input("Quantity", "100g")

daily_limit = st.sidebar.number_input(
    "🔥 Daily Calorie Limit",
    min_value=1000,
    max_value=4000,
    value=2000,
    step=100
)

if st.sidebar.button("🚪 Logout"):
    st.session_state.logged_in = False
    st.rerun()

# ------------------------------
# HEADER
# ------------------------------
st.markdown("# 🥗 NutriVision")
st.markdown(f"### Welcome, {st.session_state.username}")

st.info(f"🔥 Calories Consumed Today: {st.session_state.daily_used} / {daily_limit} kcal")

if img:
    st.image(Image.open(img), use_container_width=True)

# ------------------------------
# HELPERS
# ------------------------------
def extract_macros(text):
    try:
        p = int(re.search(r'Protein:\s*(\d+)', text).group(1))
        c = int(re.search(r'Carbs:\s*(\d+)', text).group(1))
        f = int(re.search(r'Fat:\s*(\d+)', text).group(1))
        return p, c, f
    except:
        return None, None, None

def extract_calories(text):
    m = re.search(r'(\d+)\s*kcal', text.lower())
    return int(m.group(1)) if m else 0

def ai(prompt, image):
    model = genai.GenerativeModel("models/gemini-2.5-flash")
    return model.generate_content([prompt, image]).text

# ------------------------------
# PDF GENERATION
# ------------------------------
def generate_pdf(text, username):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()

    if "MyTitle" not in styles:
        styles.add(ParagraphStyle(
            name="MyTitle",
            fontSize=18,
            alignment=1,
            spaceAfter=20
        ))

    story = []
    story.append(Paragraph("NutriVision – Nutrition Analysis Report", styles["MyTitle"]))
    story.append(Paragraph(f"User: {username}", styles["Normal"]))
    story.append(Paragraph(f"Date: {datetime.now().strftime('%d-%m-%Y %H:%M')}", styles["Normal"]))
    story.append(Spacer(1, 12))

    for line in text.split("\n"):
        if line.strip():
            story.append(Paragraph(line, styles["Normal"]))
            story.append(Spacer(1, 6))

    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "<i>Note: Nutritional values are estimated using AI-based analysis.</i>",
        styles["Normal"]
    ))

    doc.build(story)
    buf.seek(0)
    return buf

# ------------------------------
# PROMPT
# ------------------------------
prompt = f"""
You are an expert nutritionist.

Quantity: {qty}

Meal Name:

Ingredients and Calories:
1. Ingredient - calories

Total Calories: 0 kcal

Macronutrient Profile:
Protein: 0
Carbs: 0
Fat: 0

Healthiness:
Healthy / Moderate / Unhealthy

Is it Suitable for Kids:
Yes / No
"""

# ------------------------------
# ANALYSIS
# ------------------------------
if st.button("Analyse Food"):
    if not img:
        st.warning("Upload image first")
    else:
        image_data = {"mime_type": img.type, "data": img.getvalue()}
        text = ai(prompt, image_data)

        calories = extract_calories(text)
        st.session_state.daily_used += calories

        st.markdown(f"<div class='food-box'>{text}</div>", unsafe_allow_html=True)

        p, c, f = extract_macros(text)
        if p is not None and c is not None and f is not None:
            fig, ax = plt.subplots()
            ax.pie([p, c, f],
                   labels=["Protein", "Carbs", "Fat"],
                   autopct="%1.1f%%",
                   startangle=90)
            ax.set_title("Macronutrient Distribution")
            st.pyplot(fig)

        # ------------------------------
        # DOWNLOAD PDF
        # ------------------------------
        st.download_button(
            "📄 Download Nutrition Analysis Report (PDF)",
            generate_pdf(text, st.session_state.username),
            "nutrivision_analysis_report.pdf"
        )

        # ------------------------------
        # SHARE ON WHATSAPP (PROFESSIONAL TEXT)
        # ------------------------------
        whatsapp_text = f"""
🥗 NutriVision – Nutrition Analysis Report

User: {st.session_state.username}
Estimated Calories: {calories} kcal

This report was generated using an AI-Based Food Calorie Estimation System
developed as a Final Year Project.

Department of Information Science & Engineering
PDA College of Engineering © 2025
"""

        st.markdown(f"""
        <div style="text-align:center; margin-top:12px;">
            <a href="https://wa.me/?text={whatsapp_text.replace(' ', '%20').replace(chr(10), '%0A')}"
               target="_blank">
                <button style="
                    background:#25D366;
                    color:white;
                    border:none;
                    padding:10px 18px;
                    border-radius:14px;
                    font-size:15px;
                    font-weight:600;
                    cursor:pointer;">
                    📤 Share Report on WhatsApp
                </button>
            </a>
        </div>
        """, unsafe_allow_html=True)

# ------------------------------
# FOOTER (AFTER LOGIN ONLY)
# ------------------------------
st.markdown("""
<hr style="border:1px solid #2e3b4e; margin-top:40px;">

<div style="text-align:center; color:#B0BEC5; font-size:14px; line-height:1.6;">
    <b>Developed By</b><br>
    Aishwarya Patil · C. G. Balasubramanyam Singh · Madhushree · Pradeep S<br>
    Final Year – Information Science & Engineering<br>
    PDA College of Engineering © 2025
</div>
""", unsafe_allow_html=True)
