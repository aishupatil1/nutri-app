import streamlit as st
from dotenv import load_dotenv
import os, re, sqlite3, hashlib
import google.generativeai as genai
from PIL import Image
from io import BytesIO
from datetime import datetime
import matplotlib.pyplot as plt

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet

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
if "daily_cal" not in st.session_state:
    st.session_state.daily_cal = 0

# ------------------------------
# API
# ------------------------------
load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# ------------------------------
# UI
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
        if st.button("Create"):
            if np != cp:
                st.error("Passwords mismatch")
            else:
                try:
                    con = db(); cur = con.cursor()
                    cur.execute("INSERT INTO users VALUES (?,?)", (nu, hash_pass(np)))
                    con.commit(); con.close()
                    st.success("Account created")
                except:
                    st.error("Username exists")

    st.stop()

# ------------------------------
# SIDEBAR
# ------------------------------
st.sidebar.title("🍽 Food Input")
img = st.sidebar.file_uploader("Upload food image", ["jpg","png","jpeg"])
qty = st.sidebar.text_input("Quantity", "100g")
daily_limit = st.sidebar.number_input("Daily Calorie Limit", 1200, 3000, 2000)

if st.sidebar.button("Logout"):
    st.session_state.logged_in = False
    st.rerun()

# ------------------------------
# MAIN
# ------------------------------
st.title("🥗 NutriVision")
st.write(f"Welcome **{st.session_state.username}**")
st.info(f"🔥 Daily Calories Used: {st.session_state.daily_cal} / {daily_limit}")

if img:
    st.image(Image.open(img), use_container_width=True)

# ------------------------------
# HELPERS
# ------------------------------
def extract_macros(t):
    try:
        p = int(re.search(r'Protein:\s*(\d+)', t).group(1))
        c = int(re.search(r'Carbs:\s*(\d+)', t).group(1))
        f = int(re.search(r'Fat:\s*(\d+)', t).group(1))
        return p, c, f
    except:
        return None, None, None

def ai(prompt, image):
    model = genai.GenerativeModel("models/gemini-2.5-flash")
    return model.generate_content([prompt, image]).text

def pdf(text):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    for l in text.split("\n"):
        story.append(Paragraph(l, styles["Normal"]))
        story.append(Spacer(1, 8))
    doc.build(story)
    buf.seek(0)
    return buf

# ------------------------------
# PROMPT (ALL FEATURES)
# ------------------------------
prompt = f"""
You are a nutritionist.

RULES:
- Use only numbers for macros
- Be short and clear
- Always decide health status
- Give allergy warning
- Suggest healthier alternative if unhealthy
- Decide age suitability
- Suggest best time to eat

Quantity: {qty}

Meal Name:
Food Category:
Calories:
Macronutrient Profile:
Protein: 0
Carbs: 0
Fat: 0
Fiber: 0

Health Benefits:
-

Is it Healthy:
Healthy / Moderate / Unhealthy with reason

Allergy Warning:
-

If Unhealthy – Ingredient Improvement:
-

Healthier Alternative Dish:
-

Suitable For:
Kids:
Teens:
Adults:
Elderly:

Best Time to Eat:
Recommendation:
"""

# ------------------------------
# ANALYSIS
# ------------------------------
if st.button("Analyse Food"):
    if not img:
        st.warning("Upload an image")
    else:
        data = {"mime_type": img.type, "data": img.getvalue()}
        text = ai(prompt, data)

        # Save calories
        cal = re.search(r'Calories:\s*(\d+)', text)
        if cal:
            st.session_state.daily_cal += int(cal.group(1))

        # Health indicator
        if "Unhealthy" in text:
            st.error("🔴 Unhealthy Food")
        elif "Moderate" in text:
            st.warning("🟡 Consume in Moderation")
        else:
            st.success("🟢 Healthy Choice")

        st.markdown(text)

        p, c, f = extract_macros(text)
        if p and c and f:
            fig, ax = plt.subplots()
            ax.pie([p,c,f], labels=["Protein","Carbs","Fat"], autopct="%1.1f%%")
            ax.set_title("Macronutrient Distribution")
            st.pyplot(fig)

        st.download_button("📄 Download PDF", pdf(text), "nutrivision_report.pdf")

        con = db(); cur = con.cursor()
        cur.execute("INSERT INTO history VALUES (NULL,?,?,?,?)",
                    (st.session_state.username,
                     datetime.now().strftime("%d-%m-%Y %H:%M"),
                     text.splitlines()[0],
                     text))
        con.commit(); con.close()

# ------------------------------
# HISTORY
# ------------------------------
st.subheader("📜 History")
con = db(); cur = con.cursor()
cur.execute("SELECT date, meal, details FROM history WHERE username=? ORDER BY id DESC",
            (st.session_state.username,))
for d,m,t in cur.fetchall():
    with st.expander(f"{m} | {d}"):
        st.text(t)
con.close()
