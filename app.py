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
# AUTH
# ------------------------------
def hash_pass(p):
    return hashlib.sha256(p.encode()).hexdigest()

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
# UI CONFIG
# ------------------------------
st.set_page_config("NutriVision", "🥗")

# ------------------------------
# LOGIN
# ------------------------------
if not st.session_state.logged_in:
    st.title("🔐 NutriVision Authentication")
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
                st.error("Invalid credentials")

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
                    st.success("Account created")
                except:
                    st.error("Username already exists")

    st.stop()

# ------------------------------
# SIDEBAR
# ------------------------------
st.sidebar.title("📤 Upload Food")
img = st.sidebar.file_uploader("Food Image", ["jpg","jpeg","png"])
qty = st.sidebar.text_input("Quantity", "100g")

if st.sidebar.button("Logout"):
    st.session_state.logged_in = False
    st.rerun()

# ------------------------------
# MAIN UI
# ------------------------------
st.title("🥗 NutriVision")
st.write(f"Welcome **{st.session_state.username}**")

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

def ai(prompt, image):
    model = genai.GenerativeModel("models/gemini-2.5-flash")
    return model.generate_content([prompt, image]).text

# ------------------------------
# ENHANCED PDF
# ------------------------------
def generate_pdf(text, username):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            rightMargin=40,leftMargin=40,
                            topMargin=50,bottomMargin=40)

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("Title", fontSize=18, spaceAfter=20, alignment=1))
    styles.add(ParagraphStyle("Header", fontSize=12, spaceAfter=10))

    story = []
    story.append(Paragraph("🥗 NutriVision – Food Nutrition Report", styles["Title"]))
    story.append(Paragraph(f"<b>User:</b> {username}", styles["Header"]))
    story.append(Paragraph(
        f"<b>Date:</b> {datetime.now().strftime('%d-%m-%Y %H:%M')}",
        styles["Header"]
    ))
    story.append(Spacer(1, 12))

    health = extract_health(text)
    story.append(Paragraph(f"<b>Health Status:</b> {health}", styles["Normal"]))
    story.append(Spacer(1, 10))

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

IMPORTANT:
- Follow format strictly
- Use ONLY numbers for macros
- Decide health clearly
- If unhealthy, suggest ingredient alternatives
- Say if suitable for kids or not

Quantity: {qty}

Meal Name:

Ingredients and Calories:
1. Ingredient - calories
2. Ingredient - calories

Macronutrient Profile:
Protein: 0
Carbs: 0
Fat: 0
Fiber: 0

Healthiness:
Healthy / Moderate / Unhealthy

If Unhealthy – Ingredient Alternatives:
- (write alternatives or Not required)

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

        # Health indicator
        health = extract_health(text)
        if health.lower() == "unhealthy":
            st.error("🔴 Unhealthy Food")
        elif health.lower() == "moderate":
            st.warning("🟡 Consume in Moderation")
        else:
            st.success("🟢 Healthy Choice")

        st.markdown(text)

        # Pie chart
        p, c, f = extract_macros(text)
        if all(v is not None for v in [p, c, f]) and p+c+f > 0:
            fig, ax = plt.subplots()
            ax.pie([p,c,f],
                   labels=["Protein","Carbs","Fat"],
                   autopct="%1.1f%%",
                   startangle=90)
            ax.set_title("Macronutrient Distribution")
            st.pyplot(fig)

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

        # PDF
        st.download_button(
            "📄 Download PDF Report",
            generate_pdf(text, st.session_state.username),
            "nutrivision_report.pdf"
        )

# ------------------------------
# HISTORY
# ------------------------------
st.subheader("📜 History")
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
