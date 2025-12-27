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
# DARK UI (RESTORED)
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

if st.session_state.daily_used > daily_limit:
    st.error("⚠ Daily calorie limit exceeded!")

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

def extract_health(text):
    m = re.search(r'Healthiness:\s*(Healthy|Moderate|Unhealthy)', text, re.I)
    return m.group(1) if m else "Unknown"

def extract_kids(text, health):
    if re.search(r'Kids.*No', text, re.I):
        return "No"
    if health.lower() == "unhealthy":
        return "No"
    if any(x in text.lower() for x in ["coffee", "tea", "caffeine"]):
        return "No"
    return "Yes"

def extract_calories(text):
    m = re.search(r'(\d+)\s*kcal', text.lower())
    return int(m.group(1)) if m else 0

def ai(prompt, image):
    model = genai.GenerativeModel("models/gemini-2.5-flash")
    return model.generate_content([prompt, image]).text

# ------------------------------
# PDF (FIXED – NO KEYERROR)
# ------------------------------
def generate_pdf(text, username):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            rightMargin=40,leftMargin=40,
                            topMargin=50,bottomMargin=40)

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="MyTitle",
        fontSize=18,
        spaceAfter=20,
        alignment=1
    ))

    story = []
    story.append(Paragraph("🥗 NutriVision – Nutrition Report", styles["MyTitle"]))
    story.append(Paragraph(f"<b>User:</b> {username}", styles["Normal"]))
    story.append(Paragraph(f"<b>Date:</b> {datetime.now().strftime('%d-%m-%Y %H:%M')}", styles["Normal"]))
    story.append(Spacer(1, 12))

    for line in text.split("\n"):
        if line.strip():
            story.append(Paragraph(line, styles["Normal"]))
            story.append(Spacer(1, 6))

    story.append(Spacer(1, 20))
    story.append(Paragraph("<i>Generated by NutriVision</i>", styles["Normal"]))

    doc.build(story)
    buf.seek(0)
    return buf

# ------------------------------
# AI PROMPT
# ------------------------------
prompt = f"""
You are an expert nutritionist.

RULES:
- Follow format strictly
- Use ONLY numbers for macros
- Mention calories in kcal
- Decide health clearly
- If unhealthy, suggest ingredient alternatives
- ALWAYS mention kids suitability
- Support beverages like tea, coffee, milk

Quantity: {qty}

Meal Name:

Ingredients and Calories:
1. Ingredient - calories

Total Calories: 0 kcal

Macronutrient Profile:
Protein: 0
Carbs: 0
Fat: 0
Fiber: 0

Healthiness:
Healthy / Moderate / Unhealthy

If Unhealthy – Ingredient Alternatives:
-

Is it Suitable for Kids:
Yes / No with reason

Recommendation:
"""

# ------------------------------
# ANALYSIS
# ------------------------------
if st.button("Analyse Food"):
    if not img:
        st.warning("Upload image first")
    else:
        with st.spinner("Analyzing..."):
            image_data = {"mime_type": img.type, "data": img.getvalue()}
            text = ai(prompt, image_data)

        calories = extract_calories(text)
        st.session_state.daily_used += calories

        health = extract_health(text)
        if health.lower() == "unhealthy":
            st.error("🔴 Unhealthy Food")
        elif health.lower() == "moderate":
            st.warning("🟡 Consume in Moderation")
        else:
            st.success("🟢 Healthy Choice")

        kids = extract_kids(text, health)
        if kids == "No":
            st.warning("🚫 Not suitable for kids")
        else:
            st.success("👶 Suitable for kids")

        st.markdown(f"<div class='food-box'>{text}</div>", unsafe_allow_html=True)

        p, c, f = extract_macros(text)
        if p is not None and c is not None and f is not None and (p+c+f) > 0:
            fig, ax = plt.subplots()
            ax.pie([p,c,f], labels=["Protein","Carbs","Fat"], autopct="%1.1f%%", startangle=90)
            ax.set_title("Macronutrient Distribution")
            st.pyplot(fig)

        con = db(); cur = con.cursor()
        cur.execute("""
            INSERT INTO history(username,date,meal,details,calories)
            VALUES (?,?,?,?,?)
        """, (
            st.session_state.username,
            datetime.now().strftime("%d-%m-%Y %H:%M"),
            text.split("\n")[0],
            text,
            calories
        ))
        con.commit(); con.close()

        st.download_button(
            "📄 Download PDF Report",
            generate_pdf(text, st.session_state.username),
            "nutrivision_report.pdf"
        )

# ------------------------------
# HISTORY
# ------------------------------
st.markdown("## 📜 History")
con = db(); cur = con.cursor()
cur.execute("""
    SELECT date, meal, calories, details
    FROM history
    WHERE username=?
    ORDER BY id DESC
""", (st.session_state.username,))
rows = cur.fetchall()
con.close()

for d, m, cal, det in rows:
    with st.expander(f"{m} | {d} | {cal} kcal"):
        st.text(det)
