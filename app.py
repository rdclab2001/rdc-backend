# -------------------------------
# Core Flask
# -------------------------------
from flask import (
    Flask,
    request,
    render_template,
    redirect,
    url_for,
    session,
    send_file,
    jsonify
)

# -------------------------------
# Flask Extensions
# -------------------------------
# from flask_mail import Mail, Message
from flask_cors import CORS

# -------------------------------
# Standard Library
# -------------------------------
import os
import random
import sqlite3
import img2pdf
import requests

# -------------------------------
# Third-party Libraries
# -------------------------------
import pandas as pd


# -------------------------------
# Werkzeug
# -------------------------------
from werkzeug.utils import secure_filename

# -------------------------------
# SQLite Error Handling
# -------------------------------
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta

from sqlite3 import Error
from dotenv import load_dotenv
load_dotenv()

from datetime import datetime



from sib_api_v3_sdk import Configuration, ApiClient
from sib_api_v3_sdk.api import transactional_emails_api
from sib_api_v3_sdk.models import SendSmtpEmail, SendSmtpEmailTo


# Configure Brevo API key
configuration = Configuration()
configuration.api_key['api-key'] = os.environ.get('BREVO_API_KEY')
api_instance = transactional_emails_api.TransactionalEmailsApi(ApiClient(configuration))




BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": message
    }
    requests.post(url, data=data)

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL")
ADMIN_PASS = os.environ.get("ADMIN_PASS")

if not ADMIN_EMAIL or not ADMIN_PASS:
    print("WARNING: ADMIN_EMAIL or ADMIN_PASS not set")




def init_admin():
    conn = sqlite3.connect("rdc.db")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password TEXT
        )
    """)
    conn.commit()

    # insert admin only if not exists
    cur.execute("SELECT * FROM admin WHERE email=?", (ADMIN_EMAIL,))
    if not cur.fetchone():
        hashed_password = generate_password_hash(ADMIN_PASS)

        cur.execute(
            "INSERT INTO admin (email, password) VALUES (?, ?)",
            (ADMIN_EMAIL, hashed_password)
        )

        conn.commit()

    conn.close()







otp_store = {}
# ------------------------------------------------------
# FLASK SETUP
# ------------------------------------------------------
app = Flask(__name__, static_folder="static")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "fallback_dev_key")

@app.route("/health")
def health():
    return {"status": "ok"}, 200


CORS(app)


if ADMIN_EMAIL and ADMIN_PASS:
    init_admin()
else:
    print("Skipping init_admin(): ADMIN credentials not set")


# # ------------------------------------------------------
# # MAIL CONFIG
# # ------------------------------------------------------
# app.config['MAIL_SERVER'] = 'smtp.gmail.com'
# app.config['MAIL_PORT'] = 587
# app.config['MAIL_USE_TLS'] = True
# app.config['MAIL_USERNAME'] = os.environ.get("MAIL_USERNAME")
# app.config['MAIL_PASSWORD'] = os.environ.get("MAIL_PASSWORD")

# mail = Mail(app)


def ensure_table(table_name, columns):
    conn = sqlite3.connect("rdc.db")
    cur = conn.cursor()

    # Check if table exists
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    table_exists = cur.fetchone()

    if not table_exists:
        cols_sql = ", ".join([f"{name} {typ}" for name, typ in columns])
        cur.execute(
            f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY AUTOINCREMENT, {cols_sql})"
        )
        conn.commit()
        conn.close()
        return

    # Table exists → add missing columns
    cur.execute(f"PRAGMA table_info({table_name})")
    existing_cols = [col[1] for col in cur.fetchall()]

    for name, typ in columns:
        if name not in existing_cols:
            cur.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {name} {typ}"
            )

    conn.commit()
    conn.close()



# ------------------------------------------------------
# TABLE SCHEMA
# ------------------------------------------------------
tables_to_fix = {
    "website_leads": [
        ("name", "TEXT"),
        ("mobile", "TEXT"),
        ("email", "TEXT"),
        ("test_name", "TEXT"),
        ("message", "TEXT"),
        ("status", "TEXT DEFAULT 'pending'")
    ],
    "appointments": [
        ("name", "TEXT"),
        ("mobile", "TEXT"),
        ("email", "TEXT"),
        ("test_name", "TEXT"),
        ("message", "TEXT"),
        ("status", "TEXT DEFAULT 'pending'")
    ],
    "bookings": [
        ("name", "TEXT"),
        ("mobile", "TEXT"),
        ("email", "TEXT"),
        ("test_name", "TEXT"),
        ("message", "TEXT"),
        ("status", "TEXT DEFAULT 'pending'")

    ]
}



for table, cols in tables_to_fix.items():
    ensure_table(table, cols)

# ------------------------------------------------------
# DATABASE FUNCTION
# ------------------------------------------------------
def get_data(table):
    conn = sqlite3.connect("rdc.db")
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    col_names = [col[1] for col in cur.fetchall()]
    col_list = ", ".join(col_names)
    cur.execute(f"SELECT {col_list} FROM {table}")
    rows = cur.fetchall()
    conn.close()

    data = []
    for r in rows:
        row_dict = {col: r[i] for i, col in enumerate(col_names)}
        data.append(row_dict)
    return data

# ------------------------------------------------------
# ROUTES (Login, Forgot, OTP, Dashboard, etc.)
# ------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def login():
    message = ""

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        conn = sqlite3.connect("rdc.db")
        cur = conn.cursor()

        cur.execute("SELECT password FROM admin WHERE email=?", (email,))
        row = cur.fetchone()
        conn.close()

        if row and check_password_hash(row[0], password):
            session["user"] = email
            return redirect(url_for("dashboard"))
        else:
            message = "❌ Invalid Email or Password"

    return render_template("login.html", message=message)




@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    message = ""

    if request.method == "POST":
        email = request.form.get("email")

        if not email or email != ADMIN_EMAIL:
            message = "❌ Email not registered"
            return render_template("forgot.html", message=message)

        otp = random.randint(100000, 999999)
        otp_store[email] = {
            "otp": otp,
            "time": datetime.now()
        }

        session["reset_email"] = email

        try:
            html = f"""
            <p>Dear Administrator,</p>

            <p>We received a request to reset your RDC Admin password.</p>

            <p><strong>Your One Time Password (OTP) is:</strong></p>
            <h2>{otp}</h2>

            <p>This OTP is valid for 5 minutes.</p>

            <p>If you did not request this, please ignore this email.</p>

            <p>Regards,<br>
            Ragavendra Diagnosis Center</p>
            """

            send_brevo_email(
                email,
                "Admin",
                "RDC Admin Password Reset – OTP",
                html
            )

            return redirect(url_for("verify_otp"))

        except Exception as e:
            print("❌ OTP Email Error:", e)
            message = "❌ Unable to send OTP. Please try again later."

    return render_template("forgot.html", message=message)




@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    email = session.get("reset_email")

    if not email:
        return redirect(url_for("forgot"))

    message = ""
    success = False

    if request.method == "POST":
        entered_otp = request.form.get("otp")

        stored = otp_store.get(email)

        if stored:
            otp_value = stored["otp"]
            otp_time = stored["time"]

            if datetime.now() - otp_time > timedelta(minutes=5):
                otp_store.pop(email)
                message = "❌ OTP expired"
            elif str(otp_value) == entered_otp:
                otp_store.pop(email)
                session["reset_allowed"] = True
                return redirect(url_for("reset_password"))
            else:
                message = "❌ Invalid OTP"
        else:
            message = "❌ OTP not found"


    return render_template(
        "verify-otp.html",
        message=message,
        success=success
    )

@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if not session.get("reset_allowed"):
        return redirect(url_for("forgot"))

    message = ""
    success = False

    if request.method == "POST":
        password = request.form.get("password")
        confirm = request.form.get("confirm")

        if password != confirm:
            message = "❌ Passwords do not match"
        else:
            conn = sqlite3.connect("rdc.db")
            cur = conn.cursor()
            hashed_password = generate_password_hash(password)

            cur.execute(
                "UPDATE admin SET password=? WHERE email=?",
                (hashed_password, ADMIN_EMAIL)
            )

            conn.commit()
            conn.close()

            session.pop("reset_allowed")
            message = "✅ Password reset successfully"
            success = True

    return render_template("reset-password.html", message=message, success=success)




@app.route("/dashboard")
def dashboard():
    if not session.get("user"):
        return redirect(url_for("login"))
    stats = {
        "appointments": len(get_data("appointments")),
        "leads": len(get_data("website_leads")),
        "alerts": 3
    }
    return render_template("dashboard.html", stats=stats, user=session.get("user"))

@app.route("/appointments")
def appointments():
    if not session.get("user"):
        return redirect(url_for("login"))

    data = get_data("appointments")
    return render_template("appointments.html", appointments=data)


# Add new appointment manually
@app.route('/add-appointment', methods=['POST'])
def add_appointment():
    data = request.get_json() or {}

    name = data.get("name", "").strip()
    mobile = data.get("mobile", "").strip()
    email = data.get("email", "").strip()
    test_name = data.get("test_name", "").strip()
    message   = data.get("message", "").strip()

    if not name or not mobile or not test_name:
        return jsonify({"success": False, "error": "All fields are required"}), 400

    conn = sqlite3.connect("rdc.db")
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO appointments (name, mobile, email, test_name, message, status)
        VALUES (?, ?, ?, ?, ?, ?)

    """, (name, mobile, email, test_name, message, "pending"))

    conn.commit()
    conn.close()

    return jsonify({"success": True})



# Update Appointment Status
@app.route('/update-appointment-status', methods=['POST'])
def update_appointment_status():
    data = request.get_json()
    appt_id = data['id']
    status = data['status']  # expected: pending / done / cancelled

    conn = sqlite3.connect("rdc.db")
    cur = conn.cursor()

    cur.execute("UPDATE appointments SET status=? WHERE id=?", (status, appt_id))

    conn.commit()
    conn.close()

    return {"success": True}


@app.route("/website-leads")
def website_leads():
    if not session.get("user"):
        return redirect(url_for("login"))

    data = get_data("website_leads")
    return render_template("website-leads.html", website_leads=data)



@app.route("/download-excel")
def download_excel():
    if not session.get("user"):
        return redirect(url_for("login"))

    appointments = pd.DataFrame(get_data("appointments"))
    leads = pd.DataFrame(get_data("website_leads"))
    file_path = "RDC_Data.xlsx"
    with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
        appointments.to_excel(writer, sheet_name="Appointments", index=False)
        leads.to_excel(writer, sheet_name="Website Leads", index=False)
    return send_file(file_path, as_attachment=True)

@app.route("/send-whatsapp")
def send_whatsapp():
    return redirect("https://wa.me/")

@app.route('/update-lead-status', methods=['POST'])
def update_lead_status():
    data = request.get_json()
    lead_id = data.get("id")
    status = data.get("status")

    if not lead_id or not status:
        return jsonify({"success": False})

    conn = sqlite3.connect("rdc.db")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE website_leads SET status=? WHERE id=?",
        (status, lead_id)
    )
    conn.commit()
    conn.close()

    return jsonify({"success": True})






UPLOAD_FOLDER = "uploads"
PDF_FOLDER = "pdfs"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PDF_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

import base64

def send_report_email(name, email, pdf_path):
    try:
        with open(pdf_path, "rb") as f:
            encoded_file = base64.b64encode(f.read()).decode()

        send_smtp_email = SendSmtpEmail(
            to=[SendSmtpEmailTo(email=email, name=name)],
            sender={"email": "rdclab2201@gmail.com", "name": "RDC"},
            subject="Your Lab Test Report - Ragavendra Diagnosis Center",
            html_content=f"""
            <p>Dear {name},</p>

            <p>Thank you for visiting Ragavendra Diagnosis Center.</p>

            <p>Your lab test report is attached with this email.</p>

            <p>Regards,<br>
            Ragavendra Diagnosis Center</p>
            """,
            attachment=[{
                "content": encoded_file,
                "name": os.path.basename(pdf_path)
            }]
        )

        api_instance.send_transac_email(send_smtp_email)
        print("✅ Report email sent to", email)

    except Exception as e:
        print("❌ Report email failed:", e)



def send_brevo_email(to_email, to_name, subject, html):
    send_smtp_email = SendSmtpEmail(
        to=[SendSmtpEmailTo(email=to_email, name=to_name)],
        sender={"email": "rdclab2201@gmail.com", "name": "RDC"},
        subject=subject,
        html_content=html
    )
    api_instance.send_transac_email(send_smtp_email)



@app.route("/convert-and-send-report", methods=["POST"])
def convert_and_send_report():
    """
    Upload images → convert to PDF → auto-send email with PDF attachment
    """
    try:
        name = request.form.get("name", "Patient").strip()
        email = request.form.get("email", "").strip()

        if not email:
            return jsonify({"error": "Email required"}), 400

        files = request.files.getlist("images")
        if not files:
            return jsonify({"error": "No images uploaded"}), 400

        image_paths = []

        for f in files:
            if f and allowed_file(f.filename):
                filename = secure_filename(f.filename)
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
                temp_name = f"{timestamp}_{filename}"

                path = os.path.join(UPLOAD_FOLDER, temp_name)
                f.save(path)
                image_paths.append(path)

        if not image_paths:
            return jsonify({"error": "No valid images"}), 400

        # Create PDF
        pdf_filename = f"Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        pdf_path = os.path.join(PDF_FOLDER, pdf_filename)

        with open(pdf_path, "wb") as out:
            out.write(img2pdf.convert(image_paths))

        # Cleanup images
        for p in image_paths:
            try:
                os.remove(p)
            except:
                pass

        # 🔑 SEND EMAIL AUTOMATICALLY (NO MAILTO)
        import threading
        threading.Thread(
            target=send_report_email,
            args=(name, email, pdf_path),
            daemon=True
        ).start()

        return jsonify({
            "success": True,
            "message": "Report sent to patient email successfully",
            "pdf_url": url_for("download_pdf", filename=pdf_filename)
        })

    except Exception as e:
        print("❌ convert-and-send-report ERROR:", e)
        return jsonify({"error": "Server error"}), 500


@app.route("/send-email-page")
def send_email_page():
    # Renders the page where staff can select patient, upload images and prepare email
    if not session.get("user"):
        return redirect(url_for("login"))
    return render_template("send-email.html")


@app.route("/get-all-patients")
def get_all_patients():
    """
    Returns merged list of patients from appointments and website_leads.
    Each item: { id: "appt_1" or "lead_2", name, mobile, email }
    """
    conn = sqlite3.connect("rdc.db")
    cur = conn.cursor()

    # Fetch appointments
    try:
        cur.execute("PRAGMA table_info(appointments)")
        appt_cols = [c[1] for c in cur.fetchall()]
        if "email" in appt_cols:
            cur.execute("SELECT id, name, mobile, email FROM appointments")
            appts = cur.fetchall()
        else:
            cur.execute("SELECT id, name, mobile FROM appointments")
            appts = cur.fetchall()
    except Exception:
        appts = []

    # Fetch website leads
    try:
        cur.execute("PRAGMA table_info(website_leads)")
        lead_cols = [c[1] for c in cur.fetchall()]
        if "email" in lead_cols:
            cur.execute("SELECT id, name, mobile, email FROM website_leads")
            leads = cur.fetchall()
        else:
            cur.execute("SELECT id, name, mobile, message FROM website_leads")
            leads = cur.fetchall()
    except Exception:
        leads = []

    conn.close()

    merged = []
    # Appointments rows -> normalize to 4-tuple
    for r in appts:
        if len(r) == 4:
            _id, name, mobile, email = r
        else:
            _id, name, mobile = r
            email = ""
        merged.append({
            "id": f"appt_{_id}",
            "name": name or "",
            "mobile": mobile or "",
            "email": email or ""
        })

    # Leads rows -> message may contain email or not
    for r in leads:
        if len(r) == 4:
            _id, name, mobile, maybe_email = r
            # try to detect email in the field (simple)
            if "@" in (maybe_email or "") and " " not in maybe_email:
                email = maybe_email
            else:
                email = ""
        else:
            _id, name, mobile = r
            email = ""
        merged.append({
            "id": f"lead_{_id}",
            "name": name or "",
            "mobile": mobile or "",
            "email": email or ""
        })

    return jsonify(merged)


@app.route("/download-pdf/<filename>")
def download_pdf(filename):
    pdf_path = os.path.join(PDF_FOLDER, filename)
    return send_file(pdf_path, as_attachment=True)




@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

# -------------------------------
# Database connection helper
# -------------------------------
def get_db_connection():
    try:
        conn = sqlite3.connect("rdc.db")  # path to your SQLite DB
        conn.row_factory = sqlite3.Row
        return conn
    except Error as e:
        print("Database connection error:", e)
        return None


def send_booking_email(name, email, test_name):
    html = f"""
    <h3>Booking Confirmation</h3>
    <p>Dear {name},</p>
    <p>Your booking for <b>{test_name}</b> has been received.</p>
    <p>Our team will contact you shortly.</p>
    <br>
    <p>Regards,<br>Ragavendra Diagnosis Center</p>
    """
    send_brevo_email(email, name, "RDC Booking Confirmation", html)






@app.route('/book-test', methods=['POST'])
def book_test():
    try:
        data = request.get_json(silent=True) or {}

        name = data.get("name")
        mobile = data.get("mobile")
        email = data.get("email")
        test_name = data.get("test_name")
        message = data.get("message")


        if not name or not mobile or not test_name:
            return jsonify({"status": "error", "message": "Missing required fields"}), 400

        conn = sqlite3.connect("rdc.db")
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO website_leads (name, mobile, email, test_name, message, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, mobile, email, test_name, message, "pending"))

        conn.commit()
        conn.close()


        # 🔔 TELEGRAM ALERT
        send_telegram_alert(
            "🚨 NEW WEBSITE LEAD\n\n"
            f"👤 Name: {name}\n"
            f"📞 Phone: {mobile}\n"
            f"🧪 Test: {test_name}\n"
            f"🕒 Source: Website"
        )

        # ✅ RESPOND IMMEDIATELY
        response = jsonify({
            "status": "success",
            "message": "Booking saved successfully!"
        })

        # ✅ SEND EMAIL AFTER RESPONSE (NON-BLOCKING)
        import threading

        if email:
            threading.Thread(
                target=send_booking_email,
                args=(name, email, test_name),
                daemon=True
            ).start()


        return response

    except Exception as e:
        print("❌ Backend error:", e)
        return jsonify({"status": "error", "message": "Server error"}), 500




@app.route('/send-email', methods=['POST'])
def send_email_brevo():
    data = request.json
    email = data.get('email')
    name = data.get('name', 'User')

    if not email:
        return jsonify({"error": "Email is required"}), 400

    send_smtp_email = SendSmtpEmail(
        to=[SendSmtpEmailTo(email=email, name=name)],
        sender={"email": "rdclab2201@gmail.com", "name": "RDC App"},
        subject="Test Email from RDC App",
        html_content=f"<html><body><h1>Hello {name}!</h1><p>This is a test email via Brevo.</p></body></html>"
    )

    try:
        api_response = api_instance.send_transac_email(send_smtp_email)
        return jsonify({"message": "Email sent successfully", "response": str(api_response)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500




if __name__ == "__main__":
    pass


