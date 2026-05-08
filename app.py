"""
=====================================================
SHARIF MEDICAL CENTER - Flask Backend (Vercel + PostgreSQL)
=====================================================
Updated for:
- Vercel serverless deployment
- Supabase PostgreSQL database (permanent data)
- All features included
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
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

# ===== CONFIGURATION =====
app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'sharif-medical-secret-change-me')

# DATABASE: PostgreSQL (Supabase) for permanent data
# Falls back to SQLite for local development
DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
if DATABASE_URL:
    # Fix for SQLAlchemy postgres:// → postgresql://
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
else:
    # Fallback to SQLite (for local testing)
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, 'clinic.db')}"

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
}

db = SQLAlchemy(app)

EMAIL_ENABLED = os.getenv('EMAIL_ENABLED', 'false').lower() == 'true'
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USER = os.getenv('EMAIL_USER', '')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', '')
CLINIC_EMAIL = os.getenv('CLINIC_EMAIL', '')
WHATSAPP_ENABLED = os.getenv('WHATSAPP_ENABLED', 'false').lower() == 'true'
WHATSAPP_PHONE = os.getenv('WHATSAPP_PHONE', '')
WHATSAPP_API_KEY = os.getenv('WHATSAPP_API_KEY', '')


# ===== DATABASE MODELS =====
class Admin(db.Model):
    __tablename__ = 'admins'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)


class Appointment(db.Model):
    __tablename__ = 'appointments'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(40), nullable=False)
    doctor = db.Column(db.String(200), nullable=False)
    date = db.Column(db.String(40), nullable=True)
    message = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), default='pending')
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


# ===== NOTIFICATIONS =====
def send_email_notification(appointment):
    if not EMAIL_ENABLED or not EMAIL_USER or not CLINIC_EMAIL:
        return False
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"🏥 New Appointment - {appointment.name}"
        msg['From'] = EMAIL_USER
        msg['To'] = CLINIC_EMAIL
        html = f"""<html><body style="font-family:Arial;background:#f5f5f5;padding:20px;">
<div style="max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;">
<div style="background:#d32f2f;color:#fff;padding:25px;text-align:center;">
<h1 style="margin:0;">Sharif Medical Center</h1><p>New Appointment Request</p></div>
<div style="padding:30px;"><h2 style="color:#d32f2f;">📋 Appointment Details</h2>
<p><b>Name:</b> {appointment.name}</p><p><b>Phone:</b> {appointment.phone}</p>
<p><b>Doctor:</b> {appointment.doctor}</p><p><b>Date:</b> {appointment.date or 'Not specified'}</p>
<p><b>Message:</b> {appointment.message or '-'}</p></div></div></body></html>"""
        msg.attach(MIMEText(html, 'html'))
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Email failed: {e}")
        return False


def send_whatsapp_notification(appointment):
    if not WHATSAPP_ENABLED or not WHATSAPP_PHONE or not WHATSAPP_API_KEY:
        return False
    try:
        message = (f"🏥 *Sharif Medical Center*\n📋 *New Appointment*\n\n"
                   f"👤 *Name:* {appointment.name}\n📞 *Phone:* {appointment.phone}\n"
                   f"👨‍⚕️ *Doctor:* {appointment.doctor}\n📅 *Date:* {appointment.date or 'Not specified'}\n"
                   f"💬 *Message:* {appointment.message or '-'}")
        requests.get("https://api.callmebot.com/whatsapp.php",
                     params={'phone': WHATSAPP_PHONE, 'text': message, 'apikey': WHATSAPP_API_KEY},
                     timeout=10)
        return True
    except Exception as e:
        print(f"WhatsApp error: {e}")
        return False


# ===== AUTH =====
def create_token(admin_id):
    return jwt.encode({'admin_id': admin_id, 'exp': datetime.utcnow() + timedelta(days=7)},
                      app.config['SECRET_KEY'], algorithm='HS256')


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Authentication required'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            if not Admin.query.get(data['admin_id']):
                return jsonify({'error': 'Invalid token'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except Exception:
            return jsonify({'error': 'Invalid token'}), 401
        return f(*args, **kwargs)
    return decorated


# ===== INIT DATABASE =====
_db_initialized = False

def init_db():
    """Initialize database tables and default admin."""
    global _db_initialized
    if _db_initialized:
        return
    try:
        with app.app_context():
            db.create_all()
            if not Admin.query.first():
                default_admin = Admin(
                    username='sharifcenter2026',
                    password_hash=generate_password_hash('shafaqshahid123')
                )
                db.session.add(default_admin)
                db.session.commit()
                print("✅ Default admin created")
            _db_initialized = True
    except Exception as e:
        print(f"DB init error: {e}")


# ===== FRONTEND HTML =====
FRONTEND_HTML = r'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Sharif Medical Center - Lahore</title><style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--primary:#d32f2f;--primary-dark:#9a0007;--primary-light:#ff6659;--dark:#1a1a1a;--gray:#555;--light-gray:#f5f5f5;--white:#fff;--shadow:0 4px 20px rgba(0,0,0,.08)}
body{font-family:'Segoe UI',Tahoma,sans-serif;line-height:1.6;color:var(--dark);background:var(--white)}
a{text-decoration:none;color:inherit;cursor:pointer}
.page{display:none}.page.active{display:block}
.top-bar{background:var(--primary);color:var(--white);padding:8px 0;font-size:.9rem}
.top-bar-content{display:flex;justify-content:space-between;align-items:center;max-width:1200px;margin:0 auto;padding:0 20px;flex-wrap:wrap;gap:10px}
.top-bar-info{display:flex;gap:25px;flex-wrap:wrap}
.header{background:var(--white);box-shadow:var(--shadow);position:sticky;top:0;z-index:1000}
.navbar{display:flex;justify-content:space-between;align-items:center;padding:15px 20px;max-width:1200px;margin:0 auto}
.logo{display:flex;align-items:center;gap:12px;cursor:pointer}
.logo-icon{width:50px;height:50px;background:var(--primary);border-radius:12px;position:relative;box-shadow:0 4px 12px rgba(211,47,47,.3)}
.logo-icon::before,.logo-icon::after{content:'';position:absolute;background:var(--white);border-radius:3px;top:50%;left:50%;transform:translate(-50%,-50%)}
.logo-icon::before{width:28px;height:6px}.logo-icon::after{width:6px;height:28px}
.logo-text{font-size:1.2rem;font-weight:700;color:var(--primary);line-height:1.2}
.logo-text span{display:block;font-size:.7rem;color:var(--gray);font-weight:400}
.nav-menu{display:flex;list-style:none;gap:30px}
.nav-menu a{font-weight:500;color:var(--dark);position:relative;padding:5px 0}
.nav-menu a:hover,.nav-menu a.active{color:var(--primary)}
.nav-menu a.active::after{content:'';position:absolute;bottom:-5px;left:0;width:100%;height:3px;background:var(--primary);border-radius:3px}
.menu-toggle{display:none;background:none;border:none;font-size:1.6rem;cursor:pointer;color:var(--primary)}
.admin-link{color:var(--primary)!important;font-weight:600!important;border:1.5px solid var(--primary);padding:6px 14px!important;border-radius:50px}
.hero{background:linear-gradient(135deg,#fff5f5,#ffe8e8);padding:80px 20px}
.hero-content{max-width:1200px;margin:0 auto;display:grid;grid-template-columns:1fr 1fr;gap:50px;align-items:center}
.hero-text h1{font-size:3rem;margin-bottom:20px;line-height:1.2}.hero-text h1 span{color:var(--primary)}
.hero-text p{font-size:1.1rem;color:var(--gray);margin-bottom:30px}
.hero-buttons{display:flex;gap:15px;flex-wrap:wrap}
.btn{display:inline-block;padding:14px 32px;border-radius:50px;font-weight:600;cursor:pointer;border:none;font-size:1rem;font-family:inherit}
.btn-primary{background:var(--primary);color:var(--white)}
.btn-primary:hover{background:var(--primary-dark)}
.btn-outline{background:transparent;color:var(--primary);border:2px solid var(--primary)}
.btn-outline:hover{background:var(--primary);color:var(--white)}
.hero-image{background:var(--white);border-radius:20px;padding:40px;box-shadow:var(--shadow);text-align:center}
.big-plus{width:150px;height:150px;background:var(--primary);margin:0 auto 20px;border-radius:25px;position:relative}
.big-plus::before,.big-plus::after{content:'';position:absolute;background:var(--white);border-radius:8px;top:50%;left:50%;transform:translate(-50%,-50%)}
.big-plus::before{width:80px;height:18px}.big-plus::after{width:18px;height:80px}
.hero-image h3{color:var(--primary);font-size:1.5rem;margin-bottom:10px}
.discount-banner{background:linear-gradient(90deg,var(--primary),var(--primary-light));color:var(--white);padding:25px 20px;text-align:center}
.discount-banner h2{font-size:1.8rem;margin-bottom:5px}
.section{padding:80px 20px}
.section-header{text-align:center;margin-bottom:50px}
.section-header h2{font-size:2.4rem;margin-bottom:15px}.section-header h2 span{color:var(--primary)}
.section-header p{color:var(--gray);max-width:600px;margin:0 auto}
.services-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:25px;max-width:1200px;margin:0 auto}
.service-card{background:var(--white);padding:35px 25px;border-radius:16px;box-shadow:var(--shadow);text-align:center;border-top:4px solid var(--primary)}
.service-icon{width:70px;height:70px;background:linear-gradient(135deg,#ffebee,#ffcdd2);border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 20px;font-size:1.8rem}
.service-card h3{font-size:1.3rem;margin-bottom:10px}.service-card p{color:var(--gray);font-size:.95rem}
.doctors-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:30px;max-width:1100px;margin:0 auto}
.doctor-card{background:var(--white);border-radius:20px;overflow:hidden;box-shadow:var(--shadow)}
.doctor-image{background:linear-gradient(135deg,var(--primary),var(--primary-light));height:200px;display:flex;align-items:center;justify-content:center;color:var(--white);font-size:5rem}
.doctor-info{padding:30px}.doctor-info h3{font-size:1.4rem;margin-bottom:5px}
.doctor-info .specialty{color:var(--primary);font-weight:600;margin-bottom:15px}
.doctor-info .qualifications{color:var(--gray);font-size:.95rem;margin-bottom:15px;line-height:1.7}
.doctor-info .timing{background:var(--light-gray);padding:10px 15px;border-radius:8px;font-size:.9rem;border-left:4px solid var(--primary)}
.features{background:var(--light-gray)}
.features-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:25px;max-width:1200px;margin:0 auto}
.feature-box{background:var(--white);padding:30px;border-radius:16px;text-align:center}
.feature-icon{width:60px;height:60px;background:var(--primary);color:var(--white);border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 15px;font-size:1.5rem}
.feature-box h3{margin-bottom:10px}.feature-box p{color:var(--gray);font-size:.95rem}
.saturday-special{background:linear-gradient(135deg,var(--primary),var(--primary-dark));color:var(--white);padding:60px 20px;text-align:center}
.saturday-special h2{font-size:2.5rem;margin-bottom:15px}.saturday-special p{font-size:1.2rem;margin-bottom:25px}
.highlight{display:inline-block;background:var(--white);color:var(--primary);padding:8px 20px;border-radius:50px;font-weight:700;margin:5px}
.contact-section{display:grid;grid-template-columns:1fr 1fr;gap:40px;max-width:1100px;margin:0 auto}
.contact-info{background:linear-gradient(135deg,var(--primary),var(--primary-dark));color:var(--white);padding:40px;border-radius:20px}
.contact-info h2{font-size:1.8rem;margin-bottom:20px}
.contact-item{display:flex;gap:15px;margin-bottom:25px}
.contact-item-icon{width:45px;height:45px;background:rgba(255,255,255,.2);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:1.2rem;flex-shrink:0}
.appointment-form{background:var(--white);padding:40px;border-radius:20px;box-shadow:var(--shadow)}
.appointment-form h2{margin-bottom:25px}
.form-group{margin-bottom:20px}
.form-group label{display:block;margin-bottom:8px;font-weight:500}
.form-group input,.form-group select,.form-group textarea{width:100%;padding:12px 15px;border:2px solid #e0e0e0;border-radius:8px;font-size:1rem;font-family:inherit}
.form-group input:focus,.form-group select:focus,.form-group textarea:focus{outline:none;border-color:var(--primary)}
.form-group textarea{resize:vertical;min-height:100px}
.success-msg{background:#4caf50;color:#fff;padding:12px;border-radius:8px;margin-bottom:15px;text-align:center;display:none}
.error-msg{background:#f44336;color:#fff;padding:12px;border-radius:8px;margin-bottom:15px;text-align:center;display:none}
.footer{background:var(--dark);color:var(--white);padding:50px 20px 20px}
.footer-content{max-width:1200px;margin:0 auto;display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:30px;margin-bottom:30px}
.footer-col h3{margin-bottom:20px;color:var(--primary-light)}
.footer-col p,.footer-col a{color:#bbb;margin-bottom:10px;display:block;font-size:.95rem}
.footer-bottom{text-align:center;padding-top:20px;border-top:1px solid #333;color:#999;font-size:.9rem}
.page-banner{background:linear-gradient(135deg,var(--primary),var(--primary-dark));color:var(--white);padding:60px 20px;text-align:center}
.page-banner h1{font-size:2.8rem;margin-bottom:10px}
.about-content{max-width:1100px;margin:0 auto;display:grid;grid-template-columns:1fr 1fr;gap:50px;align-items:center}
.about-text h2{font-size:2rem;margin-bottom:20px}.about-text h2 span{color:var(--primary)}
.about-text p{color:var(--gray);margin-bottom:15px}
.about-text ul{list-style:none;margin-top:20px}
.about-text ul li{padding:10px 0;display:flex;align-items:center;gap:10px}
.about-text ul li::before{content:'✓';width:25px;height:25px;background:var(--primary);color:var(--white);border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:.85rem}
.about-image{background:linear-gradient(135deg,#fff5f5,#ffe8e8);border-radius:20px;padding:50px;text-align:center}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:25px;max-width:1100px;margin:50px auto 0}
.stat-box{background:var(--white);padding:30px;border-radius:16px;text-align:center;box-shadow:var(--shadow);border-bottom:4px solid var(--primary)}
.stat-box h3{font-size:2.5rem;color:var(--primary);margin-bottom:5px}
.map-section{padding:60px 20px;background:var(--light-gray)}
.map-container{max-width:1100px;margin:0 auto;border-radius:20px;overflow:hidden;box-shadow:var(--shadow)}
.map-container iframe{width:100%;height:400px;border:none;display:block}
.admin-bg{min-height:100vh;background:linear-gradient(135deg,#fff5f5,#ffe8e8);display:flex;align-items:center;justify-content:center;padding:20px}
.login-box{background:var(--white);padding:50px 40px;border-radius:20px;box-shadow:0 20px 60px rgba(211,47,47,.15);max-width:420px;width:100%}
.login-box .login-logo{text-align:center;margin-bottom:25px}
.login-box .big-plus{width:80px;height:80px;border-radius:18px;margin:0 auto 15px}
.login-box .big-plus::before{width:42px;height:10px}.login-box .big-plus::after{width:10px;height:42px}
.login-box h1{text-align:center;color:var(--primary);font-size:1.8rem;margin-bottom:8px}
.login-box .subtitle{text-align:center;color:var(--gray);margin-bottom:30px;font-size:.95rem}
.login-hint{background:#fff8e1;color:#856404;padding:10px;border-radius:8px;font-size:.85rem;margin-top:15px;text-align:center;border-left:3px solid #ffc107}
.admin-layout{display:flex;min-height:100vh;background:var(--light-gray)}
.sidebar{width:260px;background:var(--dark);color:var(--white);padding:25px 0;flex-shrink:0}
.sidebar-logo{padding:0 25px 25px;border-bottom:1px solid #333;margin-bottom:20px;display:flex;align-items:center;gap:12px}
.sidebar-logo .logo-icon{width:40px;height:40px;border-radius:10px}
.sidebar-logo .logo-icon::before{width:22px;height:5px}.sidebar-logo .logo-icon::after{width:5px;height:22px}
.sidebar-logo .logo-text{color:var(--white);font-size:1rem}.sidebar-logo .logo-text span{color:#999}
.sidebar-menu{list-style:none}
.sidebar-menu a{display:flex;align-items:center;gap:12px;padding:14px 25px;color:#bbb;border-left:4px solid transparent}
.sidebar-menu a:hover,.sidebar-menu a.active{background:rgba(211,47,47,.15);color:var(--white);border-left-color:var(--primary)}
.logout-btn{margin:20px 25px;padding:12px;background:var(--primary);color:#fff;border:none;border-radius:8px;cursor:pointer;width:calc(100% - 50px);font-weight:600;font-family:inherit}
.main-area{flex:1;padding:30px;overflow-x:auto}
.admin-header{margin-bottom:30px}.admin-header h1{font-size:1.8rem}.admin-header .welcome{color:var(--gray)}
.dashboard-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:20px;margin-bottom:30px}
.dash-card{background:var(--white);padding:25px;border-radius:14px;box-shadow:var(--shadow);display:flex;justify-content:space-between;align-items:center;border-left:4px solid var(--primary)}
.dash-card .info h3{font-size:2rem;margin-bottom:5px}.dash-card .info p{color:var(--gray);font-size:.9rem}
.dash-card .icon{width:55px;height:55px;background:linear-gradient(135deg,#ffebee,#ffcdd2);border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:1.6rem}
.data-card{background:var(--white);border-radius:14px;box-shadow:var(--shadow);padding:25px;margin-bottom:25px}
.data-card-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:10px}
.search-box{padding:8px 15px;border:1.5px solid #e0e0e0;border-radius:8px;outline:none;font-family:inherit}
.appt-table{width:100%;border-collapse:collapse;font-size:.92rem}
.appt-table th{background:var(--light-gray);padding:12px;text-align:left;font-weight:600;border-bottom:2px solid #e0e0e0;white-space:nowrap}
.appt-table td{padding:12px;border-bottom:1px solid #eee}
.status-badge{display:inline-block;padding:4px 12px;border-radius:50px;font-size:.8rem;font-weight:600}
.status-pending{background:#fff3cd;color:#856404}.status-confirmed{background:#d4edda;color:#155724}
.status-completed{background:#d1ecf1;color:#0c5460}.status-cancelled{background:#f8d7da;color:#721c24}
.action-btn{padding:6px 12px;border:none;border-radius:6px;cursor:pointer;font-size:.85rem;margin:2px;font-family:inherit}
.btn-confirm{background:#28a745;color:#fff}.btn-complete{background:#17a2b8;color:#fff}
.btn-cancel{background:#dc3545;color:#fff}.btn-delete{background:#6c757d;color:#fff}
.add-form{display:grid;grid-template-columns:1fr 1fr;gap:15px;margin-bottom:15px}
.add-form .full{grid-column:1/-1}
.add-form input,.add-form select,.add-form textarea{width:100%;padding:10px 13px;border:2px solid #e0e0e0;border-radius:8px;font-family:inherit}
.info-grid{display:grid;gap:12px;max-width:600px}
.info-grid div{padding:8px 0;border-bottom:1px solid #eee}
.empty-state{text-align:center;padding:50px 20px;color:var(--gray)}
.empty-state .big-icon{font-size:4rem;margin-bottom:15px;opacity:.3}
.loading{text-align:center;padding:50px;color:var(--gray)}
.toast{position:fixed;top:20px;right:20px;background:#4caf50;color:#fff;padding:14px 24px;border-radius:8px;box-shadow:0 4px 15px rgba(0,0,0,.2);z-index:9999;font-weight:500}
.toast.error{background:#f44336}
@media(max-width:900px){.hero-content,.contact-section,.about-content{grid-template-columns:1fr}.hero-text h1{font-size:2.2rem}.section-header h2{font-size:1.8rem}.page-banner h1{font-size:2rem}}
@media(max-width:768px){.menu-toggle{display:block}.nav-menu{position:absolute;top:100%;left:0;right:0;background:var(--white);flex-direction:column;padding:20px;gap:15px;box-shadow:var(--shadow);display:none}.nav-menu.active{display:flex}.top-bar-content{flex-direction:column;text-align:center}.hero{padding:50px 20px}.section{padding:50px 20px}.admin-layout{flex-direction:column}.sidebar{width:100%}.appt-table{font-size:.82rem}.appt-table th,.appt-table td{padding:8px}.add-form{grid-template-columns:1fr}}
</style></head><body>
<div class="page active" id="home-page">
<div class="top-bar"><div class="top-bar-content"><div class="top-bar-info"><span>📞 0370-0469037</span><span>🕐 12:00 PM - 6:00 PM</span></div><div class="top-bar-info"><span>📍 Sharqpur Road, Lahore</span></div></div></div>
<header class="header"><nav class="navbar"><a class="logo" onclick="showPage('home')"><div class="logo-icon"></div><div class="logo-text">Sharif Medical Center<span>Care You Can Trust</span></div></a>
<ul class="nav-menu" id="nm1"><li><a onclick="showPage('home')" class="active">Home</a></li><li><a onclick="showPage('about')">About</a></li><li><a onclick="showPage('services')">Services</a></li><li><a onclick="showPage('doctors')">Doctors</a></li><li><a onclick="showPage('contact')">Contact</a></li><li><a onclick="showPage('admin-login')" class="admin-link">Admin</a></li></ul>
<button class="menu-toggle" onclick="document.getElementById('nm1').classList.toggle('active')">☰</button></nav></header>
<section class="hero"><div class="hero-content"><div class="hero-text"><h1>Your Health Is Our <span>Top Priority</span></h1><p>Expert care for blood pressure, sugar, uric acid, anemia, typhoid and gastroenterology. Trusted specialists serving Lahore.</p><div class="hero-buttons"><a class="btn btn-primary" onclick="showPage('contact')">Book Appointment</a><a class="btn btn-outline" onclick="showPage('services')">Our Services</a></div></div><div class="hero-image"><div class="big-plus"></div><h3>Sharif Medical Center</h3><p>Quality Healthcare Near You</p></div></div></section>
<div class="discount-banner"><h2>🎉 50% DISCOUNT</h2><p>On all Laboratory Tests &amp; Ultrasound</p></div>
<section class="section"><div class="section-header"><h2>Our <span>Services</span></h2><p>Complete diagnosis and treatment for common health issues</p></div>
<div class="services-grid">
<div class="service-card"><div class="service-icon">🩺</div><h3>Blood Pressure</h3><p>Accurate BP monitoring and management.</p></div>
<div class="service-card"><div class="service-icon">🍬</div><h3>Sugar (Diabetes)</h3><p>Diabetes diagnosis and care.</p></div>
<div class="service-card"><div class="service-icon">⚗️</div><h3>Uric Acid</h3><p>Uric acid testing and treatment.</p></div>
<div class="service-card"><div class="service-icon">🩸</div><h3>Khoon Ki Kami</h3><p>Anemia diagnosis and treatment.</p></div>
<div class="service-card"><div class="service-icon">🌡️</div><h3>Typhoid</h3><p>Typhoid testing and treatment.</p></div>
<div class="service-card"><div class="service-icon">🔬</div><h3>Endoscopy</h3><p>Specialist gastroenterology services.</p></div>
</div></section>
<section class="saturday-special"><h2>🎁 Every Saturday Special</h2><p>Free Medical Checkup &amp; Free Medicine for All Patients</p><span class="highlight">FREE Checkup</span><span class="highlight">FREE Medicine</span></section>
<section class="section features"><div class="section-header"><h2>Why Choose <span>Us</span></h2></div>
<div class="features-grid">
<div class="feature-box"><div class="feature-icon">👨‍⚕️</div><h3>Expert Doctors</h3><p>Qualified specialists with experience</p></div>
<div class="feature-box"><div class="feature-icon">💰</div><h3>50% Discount</h3><p>On all lab tests and ultrasound</p></div>
<div class="feature-box"><div class="feature-icon">🎁</div><h3>Saturday Free</h3><p>Free checkup and medicine every Saturday</p></div>
<div class="feature-box"><div class="feature-icon">🩺</div><h3>Consultant Care</h3><p>Senior consultant care available</p></div>
</div></section>
</div>
<div class="page" id="about-page">
<div class="top-bar"><div class="top-bar-content"><div class="top-bar-info"><span>📞 0370-0469037</span><span>🕐 12:00 PM - 6:00 PM</span></div><div class="top-bar-info"><span>📍 Sharqpur Road, Lahore</span></div></div></div>
<header class="header"><nav class="navbar"><a class="logo" onclick="showPage('home')"><div class="logo-icon"></div><div class="logo-text">Sharif Medical Center<span>Care You Can Trust</span></div></a>
<ul class="nav-menu" id="nm2"><li><a onclick="showPage('home')">Home</a></li><li><a onclick="showPage('about')" class="active">About</a></li><li><a onclick="showPage('services')">Services</a></li><li><a onclick="showPage('doctors')">Doctors</a></li><li><a onclick="showPage('contact')">Contact</a></li><li><a onclick="showPage('admin-login')" class="admin-link">Admin</a></li></ul>
<button class="menu-toggle" onclick="document.getElementById('nm2').classList.toggle('active')">☰</button></nav></header>
<section class="page-banner"><h1>About Our Center</h1><p>Trusted healthcare provider serving Lahore</p></section>
<section class="section"><div class="about-content"><div class="about-text"><h2>Welcome to <span>Sharif Medical Center</span></h2>
<p>We are a trusted healthcare facility located on Sharqpur Road, Lahore, providing quality medical care to the local community.</p>
<p>Our center is dedicated to delivering compassionate care through experienced doctors and modern facilities.</p>
<ul><li>Experienced consultants and specialists</li><li>50% discount on lab tests &amp; ultrasound</li><li>Free medical checkup every Saturday</li><li>Free medicine on Saturdays</li><li>Affordable, transparent pricing</li><li>Modern diagnostic equipment</li></ul></div>
<div class="about-image"><div class="big-plus"></div><h3 style="color:var(--primary);margin-top:20px;">Quality Care</h3><p style="color:var(--gray);">Every Patient. Every Time.</p></div></div>
<div class="stats-grid"><div class="stat-box"><h3>1000+</h3><p>Happy Patients</p></div><div class="stat-box"><h3>2</h3><p>Expert Doctors</p></div><div class="stat-box"><h3>50%</h3><p>Discount on Tests</p></div><div class="stat-box"><h3>6</h3><p>Days a Week</p></div></div></section>
</div>
<div class="page" id="services-page">
<div class="top-bar"><div class="top-bar-content"><div class="top-bar-info"><span>📞 0370-0469037</span><span>🕐 12:00 PM - 6:00 PM</span></div><div class="top-bar-info"><span>📍 Sharqpur Road, Lahore</span></div></div></div>
<header class="header"><nav class="navbar"><a class="logo" onclick="showPage('home')"><div class="logo-icon"></div><div class="logo-text">Sharif Medical Center<span>Care You Can Trust</span></div></a>
<ul class="nav-menu" id="nm3"><li><a onclick="showPage('home')">Home</a></li><li><a onclick="showPage('about')">About</a></li><li><a onclick="showPage('services')" class="active">Services</a></li><li><a onclick="showPage('doctors')">Doctors</a></li><li><a onclick="showPage('contact')">Contact</a></li><li><a onclick="showPage('admin-login')" class="admin-link">Admin</a></li></ul>
<button class="menu-toggle" onclick="document.getElementById('nm3').classList.toggle('active')">☰</button></nav></header>
<section class="page-banner"><h1>Our Services</h1><p>Quality medical care for every condition</p></section>
<div class="discount-banner"><h2>🎉 50% DISCOUNT on Lab Tests &amp; Ultrasound</h2></div>
<section class="section"><div class="section-header"><h2>What We <span>Offer</span></h2></div>
<div class="services-grid">
<div class="service-card"><div class="service-icon">🩺</div><h3>Blood Pressure</h3><p>Accurate monitoring and management.</p></div>
<div class="service-card"><div class="service-icon">🍬</div><h3>Sugar (Diabetes)</h3><p>Diabetes screening and treatment.</p></div>
<div class="service-card"><div class="service-icon">⚗️</div><h3>Uric Acid</h3><p>Testing and management.</p></div>
<div class="service-card"><div class="service-icon">🩸</div><h3>Anemia</h3><p>Diagnosis and treatment.</p></div>
<div class="service-card"><div class="service-icon">🌡️</div><h3>Typhoid</h3><p>Quick testing and treatment.</p></div>
<div class="service-card"><div class="service-icon">🔬</div><h3>Endoscopy</h3><p>Specialist gastroenterology.</p></div>
<div class="service-card"><div class="service-icon">🏥</div><h3>Ultrasound</h3><p>Advanced services with 50% discount.</p></div>
<div class="service-card"><div class="service-icon">🧪</div><h3>Lab Tests</h3><p>Wide range at 50% discount.</p></div>
<div class="service-card"><div class="service-icon">👨‍⚕️</div><h3>Consultant Care</h3><p>Senior consultant care available.</p></div>
</div></section>
<section class="saturday-special"><h2>🎁 Every Saturday Free!</h2><p>Free Medical Checkup &amp; Free Medicine</p><span class="highlight">FREE Checkup</span><span class="highlight">FREE Medicine</span></section>
</div>
<div class="page" id="doctors-page">
<div class="top-bar"><div class="top-bar-content"><div class="top-bar-info"><span>📞 0370-0469037</span><span>🕐 12:00 PM - 6:00 PM</span></div><div class="top-bar-info"><span>📍 Sharqpur Road, Lahore</span></div></div></div>
<header class="header"><nav class="navbar"><a class="logo" onclick="showPage('home')"><div class="logo-icon"></div><div class="logo-text">Sharif Medical Center<span>Care You Can Trust</span></div></a>
<ul class="nav-menu" id="nm4"><li><a onclick="showPage('home')">Home</a></li><li><a onclick="showPage('about')">About</a></li><li><a onclick="showPage('services')">Services</a></li><li><a onclick="showPage('doctors')" class="active">Doctors</a></li><li><a onclick="showPage('contact')">Contact</a></li><li><a onclick="showPage('admin-login')" class="admin-link">Admin</a></li></ul>
<button class="menu-toggle" onclick="document.getElementById('nm4').classList.toggle('active')">☰</button></nav></header>
<section class="page-banner"><h1>Our Doctors</h1><p>Meet our expert medical specialists</p></section>
<section class="section"><div class="doctors-grid">
<div class="doctor-card"><div class="doctor-image">👨‍⚕️</div><div class="doctor-info"><h3>Dr. Ishfaq Ahmed Cheema</h3><div class="specialty">Endoscopy Specialist &amp; Gastroenterologist</div><div class="qualifications"><strong>Assistant Professor</strong><br>MBBS (KE)<br>FCPS (Medicine)<br>Diploma in Gastroenterology (Ireland)</div><div class="timing">🕐 <strong>Timing:</strong> 8:00 PM - 9:00 PM (Night)</div></div></div>
<div class="doctor-card"><div class="doctor-image">👩‍⚕️</div><div class="doctor-info"><h3>Dr. Shaheena Shafaq</h3><div class="specialty">Senior General Physician</div><div class="qualifications">Specialist in BP, Sugar, Uric Acid, Anemia, Typhoid &amp; General Medicine<br>Years of trusted experience</div><div class="timing">🕐 <strong>Timing:</strong> 12:00 PM - 6:00 PM</div></div></div>
</div>
<div style="text-align:center;margin-top:50px;"><p style="color:var(--gray);margin-bottom:20px;font-size:1.1rem;">Consultant Care Also Available</p><a class="btn btn-primary" onclick="showPage('contact')">Book Appointment</a></div></section>
</div>
<div class="page" id="contact-page">
<div class="top-bar"><div class="top-bar-content"><div class="top-bar-info"><span>📞 0370-0469037</span><span>🕐 12:00 PM - 6:00 PM</span></div><div class="top-bar-info"><span>📍 Sharqpur Road, Lahore</span></div></div></div>
<header class="header"><nav class="navbar"><a class="logo" onclick="showPage('home')"><div class="logo-icon"></div><div class="logo-text">Sharif Medical Center<span>Care You Can Trust</span></div></a>
<ul class="nav-menu" id="nm5"><li><a onclick="showPage('home')">Home</a></li><li><a onclick="showPage('about')">About</a></li><li><a onclick="showPage('services')">Services</a></li><li><a onclick="showPage('doctors')">Doctors</a></li><li><a onclick="showPage('contact')" class="active">Contact</a></li><li><a onclick="showPage('admin-login')" class="admin-link">Admin</a></li></ul>
<button class="menu-toggle" onclick="document.getElementById('nm5').classList.toggle('active')">☰</button></nav></header>
<section class="page-banner"><h1>Contact Us</h1><p>Book your appointment or get in touch</p></section>
<section class="section"><div class="contact-section">
<div class="contact-info"><h2>Get In Touch</h2>
<div class="contact-item"><div class="contact-item-icon">📍</div><div><h4>Address</h4><p>Near Al Rehman Garden Phase 2, Opposite Clinix Pharmacy, Sharqpur Road, Lahore</p></div></div>
<div class="contact-item"><div class="contact-item-icon">📞</div><div><h4>Phone</h4><p>0370-0469037</p></div></div>
<div class="contact-item"><div class="contact-item-icon">🕐</div><div><h4>Center Timing</h4><p>12:00 PM - 6:00 PM (Daily)<br>Endoscopy: 8:00 PM - 9:00 PM</p></div></div>
<div class="contact-item"><div class="contact-item-icon">🎁</div><div><h4>Saturday Special</h4><p>Free Checkup &amp; Free Medicine</p></div></div></div>
<div class="appointment-form"><h2>Book Appointment</h2>
<div class="success-msg" id="successMsg">✅ Thank you! Your appointment has been submitted.</div>
<div class="error-msg" id="formError"></div>
<form id="apForm" onsubmit="submitAppointment(event)">
<div class="form-group"><label>Full Name *</label><input type="text" id="ap-name" required></div>
<div class="form-group"><label>Phone *</label><input type="tel" id="ap-phone" required></div>
<div class="form-group"><label>Select Doctor</label><select id="ap-doctor"><option>Dr. Shaheena Shafaq (General Physician)</option><option>Dr. Ishfaq Ahmed Cheema (Endoscopy Specialist)</option></select></div>
<div class="form-group"><label>Preferred Date</label><input type="date" id="ap-date"></div>
<div class="form-group"><label>Message</label><textarea id="ap-message" placeholder="Describe your problem..."></textarea></div>
<button type="submit" class="btn btn-primary" style="width:100%;" id="submitBtn">Submit Request</button>
</form></div></div></section>
<section class="map-section"><div class="section-header"><h2>Find <span>Us</span></h2></div>
<div class="map-container"><iframe src="https://www.google.com/maps?q=Al+Rehman+Garden+Phase+2+Sharqpur+Road+Lahore&output=embed" loading="lazy"></iframe></div></section>
</div>
<div class="page" id="admin-login-page">
<div class="admin-bg"><div class="login-box"><div class="login-logo"><div class="big-plus"></div></div>
<h1>Admin Login</h1><p class="subtitle">Sharif Medical Center Management Panel</p>
<div class="error-msg" id="loginError"></div>
<form onsubmit="adminLogin(event)">
<div class="form-group"><label>Username</label><input type="text" id="login-user" required placeholder="Enter username"></div>
<div class="form-group"><label>Password</label><input type="password" id="login-pass" required placeholder="Enter password"></div>
<button type="submit" class="btn btn-primary" style="width:100%;" id="loginBtn">Login</button>
</form>
<div class="login-hint"><strong>🔒 Secure Admin Access</strong><br>Authorized personnel only</div>
<div style="text-align:center;margin-top:20px;"><a onclick="showPage('home')" style="color:var(--primary);font-size:.9rem;">← Back to Website</a></div>
</div></div></div>
<div class="page" id="admin-dashboard-page">
<div class="admin-layout"><aside class="sidebar">
<div class="sidebar-logo"><div class="logo-icon"></div><div class="logo-text">Sharif Medical<span>Admin Panel</span></div></div>
<ul class="sidebar-menu">
<li><a class="active" onclick="showAdminTab('dashboard',this)"><span>📊</span> Dashboard</a></li>
<li><a onclick="showAdminTab('appointments',this)"><span>📅</span> Appointments</a></li>
<li><a onclick="showAdminTab('add',this)"><span>➕</span> Add Appointment</a></li>
<li><a onclick="showAdminTab('patients',this)"><span>👥</span> Patients</a></li>
<li><a onclick="showAdminTab('settings',this)"><span>⚙️</span> Settings</a></li>
</ul><button class="logout-btn" onclick="adminLogout()">🚪 Logout</button></aside>
<main class="main-area"><div class="admin-header"><h1 id="admin-tab-title">Dashboard</h1><p class="welcome">Welcome back, Admin 👋</p></div>
<div id="tab-dashboard" class="admin-tab">
<div class="dashboard-stats">
<div class="dash-card"><div class="info"><h3 id="stat-total">0</h3><p>Total Appointments</p></div><div class="icon">📅</div></div>
<div class="dash-card"><div class="info"><h3 id="stat-pending">0</h3><p>Pending</p></div><div class="icon">⏳</div></div>
<div class="dash-card"><div class="info"><h3 id="stat-confirmed">0</h3><p>Confirmed</p></div><div class="icon">✅</div></div>
<div class="dash-card"><div class="info"><h3 id="stat-completed">0</h3><p>Completed</p></div><div class="icon">🎯</div></div>
</div>
<div class="data-card"><div class="data-card-header"><h2>Recent Appointments</h2></div><div id="recent-table"><div class="loading">Loading...</div></div></div>
</div>
<div id="tab-appointments" class="admin-tab" style="display:none;">
<div class="data-card"><div class="data-card-header"><h2>All Appointments</h2><input type="text" class="search-box" placeholder="🔍 Search..." oninput="filterAppointments(this.value)"></div>
<div id="appointments-table"><div class="loading">Loading...</div></div></div>
</div>
<div id="tab-add" class="admin-tab" style="display:none;">
<div class="data-card"><div class="data-card-header"><h2>Add New Appointment</h2></div>
<div class="add-form">
<input type="text" id="new-name" placeholder="Patient Full Name *">
<input type="tel" id="new-phone" placeholder="Phone Number *">
<select id="new-doctor"><option>Dr. Shaheena Shafaq (General Physician)</option><option>Dr. Ishfaq Ahmed Cheema (Endoscopy Specialist)</option></select>
<input type="date" id="new-date">
<textarea class="full" id="new-message" placeholder="Notes / Problem description..."></textarea>
</div><button class="btn btn-primary" onclick="addNewAppointment()">+ Add Appointment</button></div>
</div>
<div id="tab-patients" class="admin-tab" style="display:none;">
<div class="data-card"><div class="data-card-header"><h2>Patient List (Unique by phone)</h2></div><div id="patients-table"><div class="loading">Loading...</div></div></div>
</div>
<div id="tab-settings" class="admin-tab" style="display:none;">
<div class="data-card"><div class="data-card-header"><h2>Center Information</h2></div>
<div class="info-grid">
<div><strong>Center Name:</strong> Sharif Medical Center</div>
<div><strong>Address:</strong> Near Al Rehman Garden Phase 2, Opposite Clinix Pharmacy, Sharqpur Road, Lahore</div>
<div><strong>Phone:</strong> 0370-0469037</div>
<div><strong>Daily Timing:</strong> 12:00 PM - 6:00 PM</div>
<div><strong>Endoscopy Timing:</strong> 8:00 PM - 9:00 PM</div>
<div><strong>Discount:</strong> 50% on lab tests &amp; ultrasound</div>
<div><strong>Saturday Special:</strong> Free checkup &amp; free medicine</div>
</div></div>
<div class="data-card"><div class="data-card-header"><h2>Danger Zone</h2></div>
<button class="action-btn btn-cancel" onclick="clearAllAppointments()">🗑 Clear All Appointments</button></div>
</div>
</main></div></div>
<div id="footer-template" style="display:none;">
<footer class="footer"><div class="footer-content">
<div class="footer-col"><h3>Sharif Medical Center</h3><p>Trusted healthcare in Lahore.</p></div>
<div class="footer-col"><h3>Quick Links</h3><a onclick="showPage('home')">Home</a><a onclick="showPage('about')">About</a><a onclick="showPage('services')">Services</a><a onclick="showPage('doctors')">Doctors</a><a onclick="showPage('contact')">Contact</a></div>
<div class="footer-col"><h3>Contact</h3><p>📞 0370-0469037</p><p>📍 Sharqpur Road, Lahore</p><p>🕐 12:00 PM - 6:00 PM</p></div>
</div><div class="footer-bottom">© 2026 Sharif Medical Center. All Rights Reserved.</div></footer>
</div>
<script>
const API_BASE = window.location.origin + '/api';
let allAppointments = [];
function getToken(){return localStorage.getItem('admin_token');}
function setToken(t){localStorage.setItem('admin_token',t);}
function clearToken(){localStorage.removeItem('admin_token');}
async function api(endpoint, options={}){
  const headers = {'Content-Type':'application/json',...(options.headers||{})};
  const token = getToken();
  if(token) headers['Authorization']='Bearer '+token;
  const res = await fetch(API_BASE+endpoint,{...options,headers});
  const data = await res.json();
  if(!res.ok){
    if(data.error&&(data.error.includes('Token expired')||data.error.includes('Authentication required'))){clearToken();showPage('admin-login');}
    throw new Error(data.error||'Request failed');
  }
  return data;
}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function showToast(msg,error=false){const t=document.createElement('div');t.className='toast'+(error?' error':'');t.textContent=msg;document.body.appendChild(t);setTimeout(()=>t.remove(),3000);}
function showPage(page){
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  if(page==='admin-dashboard'&&!getToken()){page='admin-login';}
  document.getElementById(page+'-page').classList.add('active');
  window.scrollTo(0,0);
  if(page==='admin-dashboard'){loadDashboard();loadAppointments();}
  const pub=['home','about','services','doctors','contact'];
  if(pub.includes(page)){const cur=document.getElementById(page+'-page');if(!cur.querySelector('.footer')){cur.insertAdjacentHTML('beforeend',document.getElementById('footer-template').innerHTML);}}
}
async function submitAppointment(e){
  e.preventDefault();
  const btn=document.getElementById('submitBtn');btn.disabled=true;btn.textContent='Submitting...';
  document.getElementById('formError').style.display='none';
  document.getElementById('successMsg').style.display='none';
  try{
    await api('/appointments',{method:'POST',body:JSON.stringify({
      name:document.getElementById('ap-name').value,phone:document.getElementById('ap-phone').value,
      doctor:document.getElementById('ap-doctor').value,date:document.getElementById('ap-date').value,
      message:document.getElementById('ap-message').value})});
    document.getElementById('successMsg').style.display='block';
    document.getElementById('apForm').reset();
    showToast('✅ Appointment booked!');
    setTimeout(()=>document.getElementById('successMsg').style.display='none',6000);
  }catch(err){const e1=document.getElementById('formError');e1.textContent='❌ '+err.message;e1.style.display='block';}
  finally{btn.disabled=false;btn.textContent='Submit Request';}
}
async function adminLogin(e){
  e.preventDefault();
  const btn=document.getElementById('loginBtn');btn.disabled=true;btn.textContent='Logging in...';
  document.getElementById('loginError').style.display='none';
  try{
    const data=await api('/admin/login',{method:'POST',body:JSON.stringify({
      username:document.getElementById('login-user').value,password:document.getElementById('login-pass').value})});
    setToken(data.token);
    document.getElementById('login-user').value='';document.getElementById('login-pass').value='';
    showPage('admin-dashboard');showToast('✅ Welcome admin!');
  }catch(err){const e1=document.getElementById('loginError');e1.textContent='❌ '+err.message;e1.style.display='block';}
  finally{btn.disabled=false;btn.textContent='Login';}
}
function adminLogout(){clearToken();showPage('home');showToast('👋 Logged out');}
function showAdminTab(tab,el){
  document.querySelectorAll('.sidebar-menu a').forEach(a=>a.classList.remove('active'));
  if(el)el.classList.add('active');
  document.querySelectorAll('.admin-tab').forEach(t=>t.style.display='none');
  document.getElementById('tab-'+tab).style.display='block';
  const titles={dashboard:'Dashboard',appointments:'Appointments',add:'Add Appointment',patients:'Patients',settings:'Settings'};
  document.getElementById('admin-tab-title').textContent=titles[tab];
  if(tab==='dashboard')loadDashboard();
  if(tab==='appointments')loadAppointments();
  if(tab==='patients')loadPatients();
}
async function loadDashboard(){
  try{
    const stats=await api('/admin/stats');
    document.getElementById('stat-total').textContent=stats.total;
    document.getElementById('stat-pending').textContent=stats.pending;
    document.getElementById('stat-confirmed').textContent=stats.confirmed;
    document.getElementById('stat-completed').textContent=stats.completed;
    const list=await api('/admin/appointments');
    document.getElementById('recent-table').innerHTML=buildTable(list.slice(0,5));
  }catch(err){showToast(err.message,true);}
}
async function loadAppointments(){
  try{allAppointments=await api('/admin/appointments');document.getElementById('appointments-table').innerHTML=buildTable(allAppointments,true);}
  catch(err){showToast(err.message,true);}
}
function filterAppointments(filter){
  if(!filter){document.getElementById('appointments-table').innerHTML=buildTable(allAppointments,true);return;}
  const f=filter.toLowerCase();
  const filtered=allAppointments.filter(a=>a.name.toLowerCase().includes(f)||a.phone.includes(filter));
  document.getElementById('appointments-table').innerHTML=buildTable(filtered,true);
}
async function loadPatients(){
  try{
    const list=await api('/admin/patients');
    if(list.length===0){document.getElementById('patients-table').innerHTML='<div class="empty-state"><div class="big-icon">👥</div><h3>No patients yet</h3></div>';return;}
    let html='<div style="overflow-x:auto;"><table class="appt-table"><thead><tr><th>Name</th><th>Phone</th><th>Visits</th><th>Last Visit</th></tr></thead><tbody>';
    list.forEach(p=>{html+=`<tr><td><strong>${esc(p.name)}</strong></td><td>${esc(p.phone)}</td><td>${p.visits}</td><td>${esc(p.lastVisit)}</td></tr>`;});
    document.getElementById('patients-table').innerHTML=html+'</tbody></table></div>';
  }catch(err){showToast(err.message,true);}
}
function buildTable(list,full=false){
  if(list.length===0)return '<div class="empty-state"><div class="big-icon">📭</div><h3>No appointments yet</h3></div>';
  let html='<div style="overflow-x:auto;"><table class="appt-table"><thead><tr><th>#</th><th>Patient</th><th>Phone</th><th>Doctor</th><th>Date</th><th>Status</th>'+(full?'<th>Actions</th>':'')+'</tr></thead><tbody>';
  list.forEach(a=>{
    html+=`<tr><td>${a.id}</td><td><strong>${esc(a.name)}</strong></td><td>${esc(a.phone)}</td><td>${esc(a.doctor.split('(')[0])}</td><td>${esc(a.date)}</td><td><span class="status-badge status-${a.status}">${a.status}</span></td>`;
    if(full){
      html+=`<td>${a.status==='pending'?`<button class="action-btn btn-confirm" onclick="updateStatus(${a.id},'confirmed')">Confirm</button>`:''}${a.status==='confirmed'?`<button class="action-btn btn-complete" onclick="updateStatus(${a.id},'completed')">Complete</button>`:''}${a.status!=='cancelled'&&a.status!=='completed'?`<button class="action-btn btn-cancel" onclick="updateStatus(${a.id},'cancelled')">Cancel</button>`:''}<button class="action-btn btn-delete" onclick="deleteAppointment(${a.id})">Delete</button></td>`;
    }
    html+='</tr>';
  });
  return html+'</tbody></table></div>';
}
async function updateStatus(id,status){
  try{await api('/admin/appointments/'+id,{method:'PUT',body:JSON.stringify({status})});showToast('✅ Updated to '+status);loadDashboard();loadAppointments();}
  catch(err){showToast(err.message,true);}
}
async function deleteAppointment(id){
  if(!confirm('Delete this appointment?'))return;
  try{await api('/admin/appointments/'+id,{method:'DELETE'});showToast('🗑 Deleted');loadDashboard();loadAppointments();loadPatients();}
  catch(err){showToast(err.message,true);}
}
async function clearAllAppointments(){
  if(!confirm('Delete ALL appointments?'))return;
  try{await api('/admin/appointments',{method:'DELETE'});showToast('🗑 All cleared');loadDashboard();loadAppointments();loadPatients();}
  catch(err){showToast(err.message,true);}
}
async function addNewAppointment(){
  const name=document.getElementById('new-name').value.trim();
  const phone=document.getElementById('new-phone').value.trim();
  if(!name||!phone){showToast('❌ Name and phone required',true);return;}
  try{
    await api('/admin/appointments',{method:'POST',body:JSON.stringify({
      name,phone,doctor:document.getElementById('new-doctor').value,
      date:document.getElementById('new-date').value,message:document.getElementById('new-message').value})});
    document.getElementById('new-name').value='';document.getElementById('new-phone').value='';
    document.getElementById('new-date').value='';document.getElementById('new-message').value='';
    showToast('✅ Added!');loadDashboard();
  }catch(err){showToast(err.message,true);}
}
showPage('home');
</script></body></html>'''


# Initialize DB on each request (for serverless)
@app.before_request
def ensure_db():
    init_db()


# ===== ROUTES =====
@app.route('/')
def home():
    return FRONTEND_HTML


@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'service': 'Sharif Medical Center API'})


@app.route('/api/appointments', methods=['POST'])
def create_appointment():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    phone = (data.get('phone') or '').strip()
    if not name or not phone:
        return jsonify({'error': 'Name and phone are required'}), 400
    appointment = Appointment(
        name=name, phone=phone,
        doctor=data.get('doctor') or 'Not specified',
        date=data.get('date') or 'Not specified',
        message=data.get('message') or '-',
        status='pending')
    db.session.add(appointment)
    db.session.commit()
    try: send_email_notification(appointment)
    except: pass
    try: send_whatsapp_notification(appointment)
    except: pass
    return jsonify({'success': True, 'message': 'Appointment booked!', 'appointment': appointment.to_dict()}), 201


@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json() or {}
    admin = Admin.query.filter_by(username=data.get('username', '').strip()).first()
    if not admin or not check_password_hash(admin.password_hash, data.get('password', '')):
        return jsonify({'error': 'Invalid username or password'}), 401
    return jsonify({'success': True, 'token': create_token(admin.id), 'username': admin.username})


@app.route('/api/admin/appointments', methods=['GET'])
@token_required
def get_appointments():
    return jsonify([a.to_dict() for a in Appointment.query.order_by(Appointment.created_at.desc()).all()])


@app.route('/api/admin/appointments', methods=['POST'])
@token_required
def admin_add_appointment():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    phone = (data.get('phone') or '').strip()
    if not name or not phone:
        return jsonify({'error': 'Name and phone are required'}), 400
    appointment = Appointment(
        name=name, phone=phone,
        doctor=data.get('doctor') or 'Not specified',
        date=data.get('date') or 'Not specified',
        message=data.get('message') or '-',
        status='pending')
    db.session.add(appointment)
    db.session.commit()
    return jsonify({'success': True, 'appointment': appointment.to_dict()}), 201


@app.route('/api/admin/appointments/<int:apt_id>', methods=['PUT'])
@token_required
def update_appointment(apt_id):
    appointment = Appointment.query.get_or_404(apt_id)
    data = request.get_json() or {}
    if 'status' in data: appointment.status = data['status']
    db.session.commit()
    return jsonify({'success': True, 'appointment': appointment.to_dict()})


@app.route('/api/admin/appointments/<int:apt_id>', methods=['DELETE'])
@token_required
def delete_appointment(apt_id):
    appointment = Appointment.query.get_or_404(apt_id)
    db.session.delete(appointment)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/admin/appointments', methods=['DELETE'])
@token_required
def clear_appointments():
    Appointment.query.delete()
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/admin/stats', methods=['GET'])
@token_required
def get_stats():
    return jsonify({
        'total': Appointment.query.count(),
        'pending': Appointment.query.filter_by(status='pending').count(),
        'confirmed': Appointment.query.filter_by(status='confirmed').count(),
        'completed': Appointment.query.filter_by(status='completed').count(),
        'cancelled': Appointment.query.filter_by(status='cancelled').count()
    })


@app.route('/api/admin/patients', methods=['GET'])
@token_required
def get_patients():
    appointments = Appointment.query.order_by(Appointment.created_at.desc()).all()
    unique = {}
    for a in appointments:
        if a.phone not in unique:
            unique[a.phone] = {'name': a.name, 'phone': a.phone, 'visits': 1, 'lastVisit': a.date or '-'}
        else:
            unique[a.phone]['visits'] += 1
    return jsonify(list(unique.values()))


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=False)
