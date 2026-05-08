"""
=====================================================
SHARIF MEDICAL CENTER - Flask Backend
=====================================================
Complete professional backend system with:
- SQLite Database (auto-created)
- JWT Authentication for Admin
- Email Notifications (Gmail SMTP)
- WhatsApp Notifications (CallMeBot - FREE)
- REST API endpoints
- Public website + Admin panel served from same app
=====================================================
"""

import os
import smtplib
import requests
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import wraps

import jwt
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ===================================================
# APP CONFIGURATION
# ===================================================
app = Flask(__name__)
CORS(app)  # Allow cross-origin requests

# Secret key for JWT (CHANGE IN PRODUCTION!)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'sharif-medical-center-secret-key-change-me')

# Database (SQLite - file-based, no setup needed)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, 'clinic.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Email & WhatsApp config (set in .env file)
EMAIL_ENABLED = os.getenv('EMAIL_ENABLED', 'false').lower() == 'true'
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USER = os.getenv('EMAIL_USER', '')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', '')  # Gmail App Password
CLINIC_EMAIL = os.getenv('CLINIC_EMAIL', '')      # Where to send notifications

WHATSAPP_ENABLED = os.getenv('WHATSAPP_ENABLED', 'false').lower() == 'true'
WHATSAPP_PHONE = os.getenv('WHATSAPP_PHONE', '')        # Clinic WhatsApp number (with country code, e.g. 923700469037)
WHATSAPP_API_KEY = os.getenv('WHATSAPP_API_KEY', '')    # CallMeBot API key

# ===================================================
# DATABASE MODELS
# ===================================================
class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(40), nullable=False)
    doctor = db.Column(db.String(200), nullable=False)
    date = db.Column(db.String(40), nullable=True)
    message = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), default='pending')  # pending, confirmed, completed, cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
            'doctor': self.doctor,
            'date': self.date or 'Not specified',
            'message': self.message or '-',
            'status': self.status,
            'createdAt': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else None
        }


# ===================================================
# NOTIFICATIONS
# ===================================================
def send_email_notification(appointment):
    """Send email to clinic when new appointment is booked."""
    if not EMAIL_ENABLED or not EMAIL_USER or not CLINIC_EMAIL:
        return False
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"🏥 New Appointment - {appointment.name}"
        msg['From'] = EMAIL_USER
        msg['To'] = CLINIC_EMAIL

        html = f"""
        <html><body style="font-family:Arial,sans-serif;background:#f5f5f5;padding:20px;">
            <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);">
                <div style="background:#d32f2f;color:#fff;padding:25px;text-align:center;">
                    <h1 style="margin:0;">Sharif Medical Center</h1>
                    <p style="margin:5px 0 0;">New Appointment Request</p>
                </div>
                <div style="padding:30px;">
                    <h2 style="color:#d32f2f;">📋 Appointment Details</h2>
                    <table style="width:100%;border-collapse:collapse;">
                        <tr><td style="padding:10px;border-bottom:1px solid #eee;"><b>Patient Name:</b></td><td style="padding:10px;border-bottom:1px solid #eee;">{appointment.name}</td></tr>
                        <tr><td style="padding:10px;border-bottom:1px solid #eee;"><b>Phone:</b></td><td style="padding:10px;border-bottom:1px solid #eee;">{appointment.phone}</td></tr>
                        <tr><td style="padding:10px;border-bottom:1px solid #eee;"><b>Doctor:</b></td><td style="padding:10px;border-bottom:1px solid #eee;">{appointment.doctor}</td></tr>
                        <tr><td style="padding:10px;border-bottom:1px solid #eee;"><b>Preferred Date:</b></td><td style="padding:10px;border-bottom:1px solid #eee;">{appointment.date or 'Not specified'}</td></tr>
                        <tr><td style="padding:10px;border-bottom:1px solid #eee;"><b>Message:</b></td><td style="padding:10px;border-bottom:1px solid #eee;">{appointment.message or '-'}</td></tr>
                    </table>
                    <p style="margin-top:25px;color:#666;">Login to the admin panel to confirm or manage this appointment.</p>
                </div>
                <div style="background:#1a1a1a;color:#999;padding:15px;text-align:center;font-size:12px;">
                    © 2026 Sharif Medical Center
                </div>
            </div>
        </body></html>
        """
        msg.attach(MIMEText(html, 'html'))

        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.send_message(msg)
        print(f"✅ Email sent to {CLINIC_EMAIL}")
        return True
    except Exception as e:
        print(f"❌ Email failed: {e}")
        return False


def send_whatsapp_notification(appointment):
    """Send WhatsApp message via CallMeBot (FREE)."""
    if not WHATSAPP_ENABLED or not WHATSAPP_PHONE or not WHATSAPP_API_KEY:
        return False
    try:
        message = (
            f"🏥 *Sharif Medical Center*\n"
            f"📋 *New Appointment*\n\n"
            f"👤 *Name:* {appointment.name}\n"
            f"📞 *Phone:* {appointment.phone}\n"
            f"👨‍⚕️ *Doctor:* {appointment.doctor}\n"
            f"📅 *Date:* {appointment.date or 'Not specified'}\n"
            f"💬 *Message:* {appointment.message or '-'}\n\n"
            f"🔐 Login to admin panel to confirm."
        )
        url = "https://api.callmebot.com/whatsapp.php"
        params = {
            'phone': WHATSAPP_PHONE,
            'text': message,
            'apikey': WHATSAPP_API_KEY
        }
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            print(f"✅ WhatsApp sent to {WHATSAPP_PHONE}")
            return True
        print(f"❌ WhatsApp failed: {response.text}")
        return False
    except Exception as e:
        print(f"❌ WhatsApp error: {e}")
        return False


# ===================================================
# AUTHENTICATION (JWT)
# ===================================================
def create_token(admin_id):
    """Create JWT token valid for 7 days."""
    payload = {
        'admin_id': admin_id,
        'exp': datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')


def token_required(f):
    """Decorator to protect admin routes."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Authentication required'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            admin = Admin.query.get(data['admin_id'])
            if not admin:
                return jsonify({'error': 'Invalid token'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired, please login again'}), 401
        except Exception:
            return jsonify({'error': 'Invalid token'}), 401
        return f(*args, **kwargs)
    return decorated


# ===================================================
# API ROUTES
# ===================================================

@app.route('/')
def home():
    """Serve the frontend HTML."""
    return render_template('index.html')


@app.route('/api/health')
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok', 'service': 'Sharif Medical Center API'})


# ----- PUBLIC: Submit appointment -----
@app.route('/api/appointments', methods=['POST'])
def create_appointment():
    """Public endpoint - patients book appointments here."""
    data = request.get_json() or {}

    name = (data.get('name') or '').strip()
    phone = (data.get('phone') or '').strip()
    if not name or not phone:
        return jsonify({'error': 'Name and phone are required'}), 400

    appointment = Appointment(
        name=name,
        phone=phone,
        doctor=data.get('doctor') or 'Not specified',
        date=data.get('date') or 'Not specified',
        message=data.get('message') or '-',
        status='pending'
    )
    db.session.add(appointment)
    db.session.commit()

    # Send notifications (non-blocking, don't fail if these fail)
    try:
        send_email_notification(appointment)
    except Exception as e:
        print(f"Email notification failed: {e}")
    try:
        send_whatsapp_notification(appointment)
    except Exception as e:
        print(f"WhatsApp notification failed: {e}")

    return jsonify({
        'success': True,
        'message': 'Appointment booked successfully! We will contact you soon.',
        'appointment': appointment.to_dict()
    }), 201


# ----- ADMIN: Login -----
@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    admin = Admin.query.filter_by(username=username).first()
    if not admin or not check_password_hash(admin.password_hash, password):
        return jsonify({'error': 'Invalid username or password'}), 401

    token = create_token(admin.id)
    return jsonify({
        'success': True,
        'token': token,
        'username': admin.username
    })


# ----- ADMIN: Get all appointments -----
@app.route('/api/admin/appointments', methods=['GET'])
@token_required
def get_appointments():
    appointments = Appointment.query.order_by(Appointment.created_at.desc()).all()
    return jsonify([a.to_dict() for a in appointments])


# ----- ADMIN: Add appointment manually -----
@app.route('/api/admin/appointments', methods=['POST'])
@token_required
def admin_add_appointment():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    phone = (data.get('phone') or '').strip()
    if not name or not phone:
        return jsonify({'error': 'Name and phone are required'}), 400

    appointment = Appointment(
        name=name,
        phone=phone,
        doctor=data.get('doctor') or 'Not specified',
        date=data.get('date') or 'Not specified',
        message=data.get('message') or '-',
        status='pending'
    )
    db.session.add(appointment)
    db.session.commit()
    return jsonify({'success': True, 'appointment': appointment.to_dict()}), 201


# ----- ADMIN: Update appointment status -----
@app.route('/api/admin/appointments/<int:apt_id>', methods=['PUT'])
@token_required
def update_appointment(apt_id):
    appointment = Appointment.query.get_or_404(apt_id)
    data = request.get_json() or {}
    if 'status' in data:
        appointment.status = data['status']
    db.session.commit()
    return jsonify({'success': True, 'appointment': appointment.to_dict()})


# ----- ADMIN: Delete appointment -----
@app.route('/api/admin/appointments/<int:apt_id>', methods=['DELETE'])
@token_required
def delete_appointment(apt_id):
    appointment = Appointment.query.get_or_404(apt_id)
    db.session.delete(appointment)
    db.session.commit()
    return jsonify({'success': True})


# ----- ADMIN: Clear all appointments -----
@app.route('/api/admin/appointments', methods=['DELETE'])
@token_required
def clear_appointments():
    Appointment.query.delete()
    db.session.commit()
    return jsonify({'success': True, 'message': 'All appointments cleared'})


# ----- ADMIN: Stats / Dashboard -----
@app.route('/api/admin/stats', methods=['GET'])
@token_required
def get_stats():
    total = Appointment.query.count()
    pending = Appointment.query.filter_by(status='pending').count()
    confirmed = Appointment.query.filter_by(status='confirmed').count()
    completed = Appointment.query.filter_by(status='completed').count()
    cancelled = Appointment.query.filter_by(status='cancelled').count()
    return jsonify({
        'total': total,
        'pending': pending,
        'confirmed': confirmed,
        'completed': completed,
        'cancelled': cancelled
    })


# ----- ADMIN: Patient list (unique by phone) -----
@app.route('/api/admin/patients', methods=['GET'])
@token_required
def get_patients():
    appointments = Appointment.query.order_by(Appointment.created_at.desc()).all()
    unique = {}
    for a in appointments:
        if a.phone not in unique:
            unique[a.phone] = {
                'name': a.name,
                'phone': a.phone,
                'visits': 1,
                'lastVisit': a.date or '-'
            }
        else:
            unique[a.phone]['visits'] += 1
    return jsonify(list(unique.values()))


# ===================================================
# DATABASE INITIALIZATION
# ===================================================
def init_db():
    """Create tables and a default admin if none exists."""
    with app.app_context():
        db.create_all()
        if not Admin.query.first():
            default_admin = Admin(
                username='admin',
                password_hash=generate_password_hash('admin123')
            )
            db.session.add(default_admin)
            db.session.commit()
            print("✅ Default admin created: username='admin', password='admin123'")
            print("⚠️  Please change this password after first login!")


# ===================================================
# RUN APP
# ===================================================
if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
else:
    # When deployed (not running directly), still init DB
    init_db()
