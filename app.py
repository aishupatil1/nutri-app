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
from reportlab.lib.enums import TA_LEFT

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
            details TEXT
        )
    """)
    con.commit()
    con.close()

init_db()

# ------------------------------
# PASSWORD HASH
# ------------------------------
def hash_pass(p):
    return hashlib.sha256(p.encode()).hexdigest()

# ------------------------------
# SESSION
# ------------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""

# ------------------------------
# API KEY
# ------------------------------
load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# ------------------------------
# PAGE CONFIG
# ------------------------------
st.set_page_config("NutriVision", "🥗")

# ------------------------------
# DARK CSS
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
    font-size:18px;
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
# AUTH
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
                st.rerun()
            else:
                st.error("Invalid username or password")

    with t2:
        nu = st.text_input("New Username")
        np = st.text_input("New Password", type="password")
        cp = st.text_input("Confirm Password", type="password")
        if st.button("Create Account"):
            if not nu or not np:
                st.warning("All fields required")
            elif np != cp:
                st.error("Passwords do not match")
            else:
                try:
                    con = db(); cur = con.cursor()
                    cur.execute("INSERT INTO users VALUES (?,?)",
                                (nu, hash_pass(np)))
                    con.commit(); con.close()
                    st.success("Account created! Login now.")
                except:
                    st.error("Username already exists")

    st.stop()

# ------------------------------
# SIDEBAR
# ------------------------------
st.sidebar.title("📤 Upload Food")
img = st.sidebar.file_uploader("Food Image", ["jpg","jpeg","png"])
qty = st.sidebar.text_input("Quantity", "100g")

if st.sidebar.button("🚪 Logout"):
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.rerun()

# ------------------------------
# HEADER
# ------------------------------
st.markdown("# 🥗 NutriVision")
st.markdown(f"### Welcome, {st.session_state.username}")

if img:
    st.image(Image.open(img), use_container_width=True)

# ------------------------------
# HELPERS
# ------------------------------
def clean_text(t):
    t = re.sub(r'\*\*(.*?)\*\*', r'\1', t)
    t = re.sub(r'__', '', t)
    return t

def extract_macros(text):
    try:
        p = re.search(r'protein[:\s]+(\d+)', text, re.I)
        c = re.search(r'carb\w*[:\s]+(\d+)', text, re.I)
        f = re.search(r'fat\w*[:\s]+(\d+)', text, re.I)
        if not (p and c and f):
            return None, None, None
        return int(p.group(1)), int(c.group(1)), int(f.group(1))
    except:
        return None, None, None

def ai(prompt, image):
    model = genai.GenerativeModel("models/gemini-2.5-flash")
    return model.generate_content([prompt, image]).text

# ------------------------------
# PDF
# ------------------------------
def generate_pdf(text):
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=40, rightMargin=40,
        topMargin=50, bottomMargin=50
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        "Body", fontSize=11, leading=15, alignment=TA_LEFT
    ))
    story = []
    for line in text.split("\n"):
        if line.strip():
            story.append(Paragraph(line, styles["Body"]))
        else:
            story.append(Spacer(1, 10))
    doc.build(story)
    buf.seek(0)
    return buf

# ------------------------------
# PROMPT
# ------------------------------
prompt = f"""
You are a nutritionist.
Quantity: {qty}

Meal Name:
Ingredients and Calories:
Macronutrient Profile:
Protein: X
Carbs: X
Fats: X
Fiber: X grams
Healthiness:
Recommendation:
"""

# ------------------------------
# ANALYSIS
# ------------------------------
if st.button("Analyse Food"):
    if not img:
        st.warning("Upload an image first")
    else:
        image_data = {"mime_type": img.type, "data": img.getvalue()}
        raw = ai(prompt, image_data)
        text = clean_text(raw)

        # Save history
        con = db(); cur = con.cursor()
        cur.execute("""
            INSERT INTO history(username,date,meal,details)
            VALUES (?,?,?,?)
        """, (
            st.session_state.username,
            datetime.now().strftime("%d-%m-%Y %H:%M"),
            text.split("\n")[0],
            text
        ))
        con.commit(); con.close()

        st.markdown(f"<div class='food-box'>{text}</div>", unsafe_allow_html=True)

        # ------------------------------
        # PIE CHART (GUARANTEED)
        # ------------------------------
        p, c, f = extract_macros(text)

        if all(v is not None for v in [p, c, f]) and (p + c + f) > 0:
            fig, ax = plt.subplots(figsize=(5,5), facecolor="#121212")
            ax.set_facecolor("#121212")
            ax.pie(
                [p, c, f],
                labels=["Protein", "Carbs", "Fat"],
                autopct="%1.1f%%",
                startangle=90,
                textprops={"color": "white"}
            )
            ax.set_title("Macronutrient Distribution", color="white")
            st.pyplot(fig)
        else:
            st.warning("⚠ Macronutrient data not detected – pie chart unavailable")

        st.download_button(
            "📄 Download PDF",
            generate_pdf(text),
            "nutrivision_report.pdf"
        )

# ------------------------------
# HISTORY
# ------------------------------
st.markdown("## 📜 History")

con = db(); cur = con.cursor()
cur.execute("""
    SELECT date, meal, details
    FROM history
    WHERE username=?
    ORDER BY id DESC
""", (st.session_state.username,))
rows = cur.fetchall()
con.close()

for d, m, det in rows:
    with st.expander(f"{m} | {d}"):
        st.text(det)
