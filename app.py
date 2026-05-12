"""
=====================================================
SHARIF MEDICAL CENTER - Flask Backend (Vercel + SQLite)
=====================================================
Professional Hospital Theme - Redesigned
- Vercel serverless deployment
- SQLite database (writable /tmp)
- All features included
- 3 Doctors, expanded services, multiple offers
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

# DATABASE: SQLite in /tmp directory (writable on Vercel serverless)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/clinic.db'
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
        msg['Subject'] = f"New Appointment - {appointment.name}"
        msg['From'] = EMAIL_USER
        msg['To'] = CLINIC_EMAIL
        html = f"""<html><body style="font-family:Arial;background:#f5f5f5;padding:20px;">
<div style="max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;">
<div style="background:#0a2540;color:#fff;padding:25px;text-align:center;">
<h1 style="margin:0;">Sharif Medical Center</h1><p>New Appointment Request</p></div>
<div style="padding:30px;"><h2 style="color:#0a2540;">Appointment Details</h2>
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
        message = (f"*Sharif Medical Center*\n*New Appointment*\n\n"
                   f"*Name:* {appointment.name}\n*Phone:* {appointment.phone}\n"
                   f"*Doctor:* {appointment.doctor}\n*Date:* {appointment.date or 'Not specified'}\n"
                   f"*Message:* {appointment.message or '-'}")
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
                print("Default admin created")
            _db_initialized = True
    except Exception as e:
        print(f"DB init error: {e}")


# ===== FRONTEND HTML =====
FRONTEND_HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Sharif Medical Center - Consultant Care | Lahore</title>
<meta name="description" content="Trusted healthcare in Lahore. Expert consultants for Blood Pressure, Diabetes, Gastroenterology, Endoscopy. 50% off lab tests & ultrasound. Free Saturday & Sunday medical camps.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700;9..144,800&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --navy:#0a2540;--navy-light:#143a5e;--navy-dark:#051a30;
  --teal:#0d8b8b;--teal-light:#14b8a6;--teal-bg:#e6f7f7;
  --gold:#c9a55c;--gold-light:#e6c98f;
  --red:#dc2626;--red-dark:#991b1b;--red-bg:#fef2f2;
  --rose:#9f1239;--rose-light:#be123c;--rose-bg:#fff1f2;
  --emerald-deep:#064e3b;--emerald:#065f46;--emerald-light:#047857;
  --sea-deep:#0c4a6e;--sea:#0369a1;--sea-light:#0891b2;--sea-glow:#22d3ee;
  --bg:#fafbfc;--bg-alt:#f3f6f9;--white:#fff;
  --text:#0f172a;--text-soft:#475569;--text-mute:#94a3b8;
  --border:#e2e8f0;--border-soft:#eef2f6;
  --shadow-sm:0 1px 2px rgba(10,37,64,.04),0 1px 3px rgba(10,37,64,.06);
  --shadow:0 4px 6px -1px rgba(10,37,64,.06),0 10px 25px -5px rgba(10,37,64,.08);
  --shadow-lg:0 10px 15px -3px rgba(10,37,64,.08),0 25px 50px -12px rgba(10,37,64,.18);
  --radius:14px;--radius-lg:20px;--radius-sm:8px;
  --serif:'Fraunces',Georgia,serif;
  --sans:'Plus Jakarta Sans',-apple-system,system-ui,sans-serif;
  --ease:cubic-bezier(.4,0,.2,1);
}
html{scroll-behavior:smooth}
body{font-family:var(--sans);line-height:1.65;color:var(--text);background:var(--bg);overflow-x:hidden;-webkit-font-smoothing:antialiased}
a{text-decoration:none;color:inherit;cursor:pointer}
img{max-width:100%;display:block}
button{font-family:inherit;cursor:pointer;border:none;background:none}

.page{display:none;animation:pageIn .5s var(--ease)}
.page.active{display:block}
@keyframes pageIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}

.top-bar{background:linear-gradient(90deg,var(--navy-dark),var(--navy),var(--navy-dark));color:#cbd5e1;padding:10px 0;font-size:.84rem;font-weight:500;letter-spacing:.02em;border-bottom:1px solid rgba(255,255,255,.04)}
.top-bar-content{display:flex;justify-content:space-between;align-items:center;max-width:1280px;margin:0 auto;padding:0 24px;flex-wrap:wrap;gap:10px}
.top-bar-info{display:flex;gap:24px;flex-wrap:wrap;align-items:center}
.top-bar-info span{display:inline-flex;align-items:center;gap:7px}
.top-bar-info .dot{width:6px;height:6px;background:var(--teal-light);border-radius:50%;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}

.header{background:rgba(255,255,255,.92);backdrop-filter:saturate(180%) blur(14px);-webkit-backdrop-filter:saturate(180%) blur(14px);box-shadow:0 1px 0 rgba(10,37,64,.06);position:sticky;top:0;z-index:100;transition:box-shadow .3s var(--ease)}
.header.scrolled{box-shadow:0 4px 20px rgba(10,37,64,.08)}
.navbar{display:flex;justify-content:space-between;align-items:center;padding:14px 24px;max-width:1280px;margin:0 auto}
.logo{display:flex;align-items:center;gap:14px;cursor:pointer}
.logo-mark{width:48px;height:48px;background:linear-gradient(135deg,var(--navy),var(--teal));border-radius:12px;position:relative;box-shadow:0 6px 18px rgba(13,139,139,.28);flex-shrink:0;transition:transform .3s var(--ease)}
.logo:hover .logo-mark{transform:rotate(-4deg) scale(1.05)}
.logo-mark::before,.logo-mark::after{content:'';position:absolute;background:var(--white);border-radius:3px;top:50%;left:50%;transform:translate(-50%,-50%)}
.logo-mark::before{width:24px;height:6px}
.logo-mark::after{width:6px;height:24px}
.logo-text{font-family:var(--serif);font-size:1.18rem;font-weight:700;color:var(--navy);line-height:1.1;letter-spacing:-.01em}
.logo-text span{display:block;font-family:var(--sans);font-size:.7rem;color:var(--teal);font-weight:600;letter-spacing:.12em;text-transform:uppercase;margin-top:3px}
.nav-menu{display:flex;list-style:none;gap:6px;align-items:center}
.nav-menu a{font-weight:500;color:var(--text);padding:9px 16px;border-radius:8px;font-size:.94rem;transition:all .25s var(--ease)}
.nav-menu a:hover{color:var(--teal);background:var(--teal-bg)}
.nav-menu a.active{color:var(--teal);background:var(--teal-bg)}
.menu-toggle{display:none;background:none;border:1.5px solid var(--border);font-size:1.4rem;cursor:pointer;color:var(--navy);width:42px;height:42px;border-radius:10px;align-items:center;justify-content:center}
.admin-link{color:var(--white)!important;background:var(--navy)!important;font-weight:600!important;padding:9px 18px!important;letter-spacing:.02em}
.admin-link:hover{background:var(--navy-light)!important;color:var(--white)!important}

.hero{position:relative;overflow:hidden;padding:90px 24px 100px;background:linear-gradient(135deg,#f0f9f9 0%,#fafbfc 50%,#fef9f0 100%)}
.hero::before{content:'';position:absolute;top:-200px;right:-200px;width:600px;height:600px;background:radial-gradient(circle,rgba(13,139,139,.12),transparent 70%);border-radius:50%;animation:floatA 18s ease-in-out infinite}
.hero::after{content:'';position:absolute;bottom:-150px;left:-150px;width:500px;height:500px;background:radial-gradient(circle,rgba(201,165,92,.1),transparent 70%);border-radius:50%;animation:floatB 22s ease-in-out infinite}
@keyframes floatA{0%,100%{transform:translate(0,0) scale(1)}50%{transform:translate(-30px,40px) scale(1.05)}}
@keyframes floatB{0%,100%{transform:translate(0,0) scale(1)}50%{transform:translate(40px,-30px) scale(1.08)}}
.hero-content{position:relative;z-index:1;max-width:1280px;margin:0 auto;display:grid;grid-template-columns:1.1fr .9fr;gap:60px;align-items:center}
.hero-badge{display:inline-flex;align-items:center;gap:8px;background:rgba(13,139,139,.08);border:1px solid rgba(13,139,139,.2);color:var(--teal);padding:7px 14px;border-radius:50px;font-size:.82rem;font-weight:600;margin-bottom:24px;letter-spacing:.04em;animation:slideUp .6s var(--ease) both}
.hero-badge .dot{width:7px;height:7px;background:var(--teal);border-radius:50%;animation:pulse 2s infinite}
.hero h1{font-family:var(--serif);font-size:clamp(2.2rem,4.6vw,3.8rem);font-weight:600;line-height:1.08;letter-spacing:-.02em;color:var(--navy);margin-bottom:22px;animation:slideUp .7s var(--ease) .1s both}
.hero h1 em{font-style:italic;color:var(--teal);font-weight:500;position:relative}
.hero h1 em::after{content:'';position:absolute;left:0;right:0;bottom:-2px;height:8px;background:rgba(201,165,92,.25);z-index:-1;border-radius:4px}
.hero-sub{font-size:1.1rem;color:var(--text-soft);margin-bottom:32px;max-width:560px;animation:slideUp .7s var(--ease) .2s both}
.hero-cta{display:flex;gap:14px;flex-wrap:wrap;animation:slideUp .7s var(--ease) .3s both}
@keyframes slideUp{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}

.btn{display:inline-flex;align-items:center;gap:9px;padding:14px 28px;border-radius:50px;font-weight:600;font-size:.97rem;letter-spacing:.01em;transition:all .3s var(--ease);font-family:var(--sans);cursor:pointer;border:none;white-space:nowrap}
.btn-primary{background:linear-gradient(135deg,var(--teal),var(--teal-light));color:var(--white);box-shadow:0 4px 14px rgba(13,139,139,.32)}
.btn-primary:hover{transform:translateY(-2px);box-shadow:0 10px 25px rgba(13,139,139,.45)}
.btn-dark{background:var(--navy);color:var(--white);box-shadow:0 4px 14px rgba(10,37,64,.28)}
.btn-dark:hover{background:var(--navy-light);transform:translateY(-2px);box-shadow:0 10px 25px rgba(10,37,64,.4)}
.btn-outline{background:transparent;color:var(--navy);border:1.5px solid var(--border)}
.btn-outline:hover{border-color:var(--teal);color:var(--teal);background:var(--teal-bg)}

.hero-card{position:relative;background:var(--white);border-radius:24px;padding:36px 32px;box-shadow:var(--shadow-lg);border:1px solid var(--border-soft);animation:slideUp .8s var(--ease) .2s both}
.hero-card-decor{position:absolute;top:-12px;right:-12px;background:linear-gradient(135deg,var(--gold),var(--gold-light));color:var(--navy);padding:8px 16px;border-radius:30px;font-size:.78rem;font-weight:700;letter-spacing:.05em;box-shadow:0 6px 18px rgba(201,165,92,.4);text-transform:uppercase}
.hero-card-badge{width:88px;height:88px;background:linear-gradient(135deg,var(--navy),var(--teal));border-radius:22px;margin:0 auto 22px;position:relative;box-shadow:0 12px 30px rgba(13,139,139,.3);animation:bob 3s ease-in-out infinite}
@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}
.hero-card-badge::before,.hero-card-badge::after{content:'';position:absolute;background:var(--white);border-radius:6px;top:50%;left:50%;transform:translate(-50%,-50%)}
.hero-card-badge::before{width:44px;height:10px}
.hero-card-badge::after{width:10px;height:44px}
.hero-card h3{font-family:var(--serif);font-size:1.5rem;color:var(--navy);text-align:center;margin-bottom:6px;font-weight:600}
.hero-card .tag{text-align:center;color:var(--teal);font-size:.86rem;font-weight:600;letter-spacing:.1em;text-transform:uppercase;margin-bottom:24px}
.hero-card-stats{display:grid;grid-template-columns:1fr 1fr;gap:14px;padding-top:22px;border-top:1px solid var(--border-soft)}
.hcs-item{text-align:center;padding:10px}
.hcs-item .num{font-family:var(--serif);font-size:1.8rem;font-weight:700;color:var(--navy);line-height:1}
.hcs-item .lbl{font-size:.78rem;color:var(--text-mute);margin-top:4px;font-weight:500;letter-spacing:.04em;text-transform:uppercase}

/* Hero image (new) */
.hero-image-wrap{position:relative;border-radius:var(--radius-lg);overflow:visible;animation:slideUp .9s var(--ease) both;min-height:480px}
.hero-image{width:100%;height:480px;object-fit:cover;border-radius:var(--radius-lg);display:block;box-shadow:0 30px 80px -20px rgba(10,37,64,.35),0 12px 40px -10px rgba(10,37,64,.2)}
.hero-image-overlay{position:absolute;inset:0;border-radius:var(--radius-lg);background:linear-gradient(135deg,rgba(10,37,64,.15) 0%,transparent 50%,rgba(13,139,139,.18) 100%);pointer-events:none}
.hero-float{position:absolute;background:var(--white);border-radius:18px;padding:18px 22px;box-shadow:0 20px 50px -15px rgba(10,37,64,.28),0 8px 20px -8px rgba(10,37,64,.15);border:1px solid var(--border-soft);backdrop-filter:blur(12px);animation:floatPulse 4s ease-in-out infinite}
.hero-float-stats{bottom:30px;left:-30px;display:flex;gap:22px;align-items:center;animation-delay:.5s}
.hf-row{text-align:left}
.hf-num{font-family:var(--serif);font-size:1.7rem;font-weight:700;color:var(--navy);line-height:1;letter-spacing:-.02em}
.hf-num span{color:var(--teal)}
.hf-lbl{font-size:.7rem;color:var(--text-mute);margin-top:4px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;line-height:1.3}
.hero-float-discount{top:30px;right:-20px;display:flex;gap:12px;align-items:center;background:linear-gradient(135deg,var(--navy) 0%,var(--navy-light) 100%);color:var(--white);border-color:transparent;animation-delay:1s}
.hf-discount-icon{width:42px;height:42px;border-radius:12px;background:rgba(201,165,92,.22);display:flex;align-items:center;justify-content:center;color:var(--gold-light);flex-shrink:0}
.hf-discount-num{font-family:var(--serif);font-size:1.15rem;font-weight:700;color:var(--gold-light);letter-spacing:.01em}
.hf-discount-sub{font-size:.72rem;color:#cbd5e1;margin-top:2px;letter-spacing:.03em}
@keyframes floatPulse{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}

/* Featured Doctors strip */
.featured-docs{padding:80px 24px;background:linear-gradient(180deg,var(--bg-alt) 0%,var(--white) 100%);position:relative;overflow:hidden}
.featured-docs::before{content:'';position:absolute;top:-100px;right:-100px;width:400px;height:400px;background:radial-gradient(circle,rgba(13,139,139,.06),transparent 60%);border-radius:50%}
.fd-grid{max-width:1280px;margin:0 auto;display:grid;grid-template-columns:repeat(4,1fr);gap:24px;position:relative}
.fd-card{background:var(--white);border:1px solid var(--border-soft);border-radius:var(--radius);padding:32px 22px 26px;text-align:center;transition:all .4s var(--ease);cursor:pointer;position:relative;overflow:hidden}
.fd-card::after{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--teal),var(--navy));transform:scaleX(0);transform-origin:left;transition:transform .5s var(--ease)}
.fd-card:hover{transform:translateY(-6px);box-shadow:var(--shadow-lg);border-color:transparent}
.fd-card:hover::after{transform:scaleX(1)}
.fd-avatar{width:78px;height:78px;border-radius:50%;margin:0 auto 18px;display:flex;align-items:center;justify-content:center;color:var(--white);font-family:var(--serif);font-size:1.7rem;font-weight:600;letter-spacing:.02em;box-shadow:0 12px 28px -6px rgba(10,37,64,.25);transition:transform .4s var(--ease)}
.fd-card:hover .fd-avatar{transform:scale(1.08) rotate(-4deg)}
.fd-avatar.av-teal{background:linear-gradient(135deg,#0d8b8b,#14b8a6)}
.fd-avatar.av-navy{background:linear-gradient(135deg,#1e3a8a,#0a2540)}
.fd-avatar.av-gold{background:linear-gradient(135deg,#b8860b,#d97706)}
.fd-avatar.av-emerald{background:linear-gradient(135deg,#047857,#10b981)}
.fd-name{font-family:var(--serif);font-size:1.1rem;font-weight:600;color:var(--navy);margin-bottom:5px;letter-spacing:-.01em}
.fd-spec{color:var(--teal);font-size:.82rem;font-weight:600;margin-bottom:10px;letter-spacing:.01em}
.fd-time{font-size:.78rem;color:var(--text-mute);padding-top:12px;border-top:1px solid var(--border-soft);margin-top:8px}

/* Our Facility section */
.facility-section{padding:90px 24px;background:var(--white)}
.facility-grid{max-width:1280px;margin:0 auto;display:grid;grid-template-columns:1fr 1fr;gap:60px;align-items:center}
.facility-image-wrap{position:relative;border-radius:var(--radius-lg);overflow:hidden;aspect-ratio:5/4;box-shadow:0 30px 60px -15px rgba(10,37,64,.25)}
.facility-image-wrap img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .8s var(--ease)}
.facility-image-wrap:hover img{transform:scale(1.05)}
.facility-image-wrap::after{content:'';position:absolute;inset:0;background:linear-gradient(135deg,transparent 60%,rgba(10,37,64,.2))}
.facility-badge{position:absolute;bottom:24px;left:24px;background:var(--white);padding:14px 20px;border-radius:14px;display:flex;align-items:center;gap:12px;box-shadow:var(--shadow-md);z-index:2}
.facility-badge-icon{width:38px;height:38px;border-radius:10px;background:linear-gradient(135deg,var(--teal-bg),var(--white));color:var(--teal);display:flex;align-items:center;justify-content:center}
.facility-badge-txt strong{display:block;color:var(--navy);font-family:var(--serif);font-size:1rem;font-weight:600}
.facility-badge-txt span{color:var(--text-mute);font-size:.78rem;letter-spacing:.02em}
.facility-content h2{font-family:var(--serif);font-size:clamp(1.8rem,3vw,2.4rem);font-weight:600;color:var(--navy);line-height:1.2;margin-bottom:18px;letter-spacing:-.02em}
.facility-content h2 em{font-style:italic;color:var(--teal);font-weight:500}
.facility-content > p{color:var(--text-soft);font-size:1.02rem;margin-bottom:28px;line-height:1.75}
.facility-features{display:grid;gap:14px}
.fac-feat{display:flex;gap:14px;align-items:flex-start;padding:14px;background:var(--bg-alt);border-radius:12px;transition:all .3s var(--ease)}
.fac-feat:hover{background:var(--teal-bg);transform:translateX(6px)}
.fac-feat-icon{width:38px;height:38px;border-radius:10px;background:var(--white);color:var(--teal);display:flex;align-items:center;justify-content:center;flex-shrink:0;box-shadow:var(--shadow-sm)}
.fac-feat-txt strong{display:block;color:var(--navy);font-weight:600;margin-bottom:3px;font-size:.95rem}
.fac-feat-txt span{color:var(--text-soft);font-size:.85rem;line-height:1.5}

.trust-strip{background:var(--navy);color:var(--white);padding:50px 24px;position:relative;overflow:hidden}
.trust-strip::before{content:'';position:absolute;inset:0;background:radial-gradient(800px circle at 80% 50%,rgba(13,139,139,.18),transparent 50%)}
.trust-grid{position:relative;max-width:1280px;margin:0 auto;display:grid;grid-template-columns:repeat(4,1fr);gap:30px;text-align:center}
.trust-item{padding:10px 5px;border-right:1px solid rgba(255,255,255,.08)}
.trust-item:last-child{border-right:none}
.trust-item .num{font-family:var(--serif);font-size:2.6rem;font-weight:700;color:var(--gold);line-height:1;letter-spacing:-.02em}
.trust-item .num .plus{color:var(--teal-light)}
.trust-item .lbl{color:#cbd5e1;font-size:.88rem;margin-top:6px;font-weight:500;letter-spacing:.04em}

.section{padding:90px 24px}
.section-head{text-align:center;max-width:680px;margin:0 auto 60px}
.eyebrow{display:inline-block;color:var(--teal);font-size:.82rem;font-weight:700;letter-spacing:.18em;text-transform:uppercase;margin-bottom:14px;position:relative;padding:0 28px}
.eyebrow::before,.eyebrow::after{content:'';position:absolute;top:50%;width:18px;height:1.5px;background:var(--teal);border-radius:1px}
.eyebrow::before{left:0}
.eyebrow::after{right:0}
.section-head h2{font-family:var(--serif);font-size:clamp(1.9rem,3.4vw,2.8rem);font-weight:600;color:var(--navy);line-height:1.15;letter-spacing:-.02em;margin-bottom:14px}
.section-head h2 em{font-style:italic;color:var(--teal);font-weight:500}
.section-head p{color:var(--text-soft);font-size:1.05rem}

.services-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:22px;max-width:1280px;margin:0 auto}
.service-card{background:var(--white);padding:32px 26px;border-radius:var(--radius-lg);border:1px solid var(--border-soft);transition:all .35s var(--ease);position:relative;overflow:hidden}
.service-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--teal),var(--gold));transform:scaleX(0);transform-origin:left;transition:transform .4s var(--ease)}
.service-card:hover{transform:translateY(-6px);box-shadow:var(--shadow-lg);border-color:var(--teal-bg)}
.service-card:hover::before{transform:scaleX(1)}
.service-icon{width:60px;height:60px;background:linear-gradient(135deg,var(--teal-bg),#fff);border-radius:14px;display:flex;align-items:center;justify-content:center;margin-bottom:20px;color:var(--teal);border:1px solid rgba(13,139,139,.12);transition:all .35s var(--ease)}
.service-card:hover .service-icon{background:linear-gradient(135deg,var(--teal),var(--teal-light));color:var(--white);transform:rotate(-5deg) scale(1.05)}
.service-icon svg{width:30px;height:30px}
.service-card h3{font-family:var(--serif);font-size:1.25rem;font-weight:600;color:var(--navy);margin-bottom:10px;letter-spacing:-.01em}
.service-card p{color:var(--text-soft);font-size:.93rem;line-height:1.6}
.service-card .tag{display:inline-block;margin-top:14px;padding:4px 12px;border-radius:30px;font-size:.74rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase}
.tag-discount{background:var(--rose-bg);color:var(--rose);border:1px solid #fecdd3}
.tag-free{background:#f0fdf4;color:#15803d}
.tag-new{background:#fef3c7;color:#92400e}

.offers-section{padding:80px 24px;background:linear-gradient(135deg,var(--sea-deep) 0%,var(--sea) 55%,var(--sea-light) 100%);color:var(--white);position:relative;overflow:hidden}
.offers-section::before{content:'';position:absolute;inset:0;background-image:radial-gradient(circle at 20% 30%,rgba(34,211,238,.22),transparent 45%),radial-gradient(circle at 80% 70%,rgba(201,165,92,.18),transparent 45%),radial-gradient(circle at 50% 100%,rgba(255,255,255,.08),transparent 55%);pointer-events:none}
.offers-grid{position:relative;max-width:1280px;margin:0 auto;display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:22px}
.offer-card{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.1);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border-radius:18px;padding:28px;transition:all .35s var(--ease);position:relative;overflow:hidden}
.offer-card:hover{transform:translateY(-4px);background:rgba(255,255,255,.07);border-color:var(--teal-light)}
.offer-card .price-tag{position:absolute;top:18px;right:18px;background:var(--gold);color:var(--navy);padding:4px 12px;border-radius:30px;font-size:.76rem;font-weight:800;letter-spacing:.04em}
.offer-card .offer-icon{width:50px;height:50px;background:linear-gradient(135deg,var(--teal),var(--teal-light));border-radius:12px;display:flex;align-items:center;justify-content:center;margin-bottom:18px;color:var(--white)}
.offer-card .offer-icon svg{width:24px;height:24px}
.offer-card h4{font-family:var(--serif);font-size:1.2rem;font-weight:600;margin-bottom:8px;color:var(--white)}
.offer-card p{font-size:.92rem;color:#cbd5e1;margin-bottom:14px;line-height:1.55}
.offer-card .offer-meta{font-size:.82rem;color:var(--gold-light);font-weight:600;letter-spacing:.04em;display:flex;align-items:center;gap:6px}

.doctors-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:30px;max-width:1200px;margin:0 auto}
.doctor-card{background:var(--white);border-radius:var(--radius-lg);overflow:hidden;border:1px solid var(--border-soft);transition:all .4s var(--ease);position:relative}
.doctor-card:hover{transform:translateY(-8px);box-shadow:var(--shadow-lg)}
.doctor-banner{height:200px;background:linear-gradient(135deg,var(--navy) 0%,var(--teal) 100%);position:relative;display:flex;align-items:flex-end;justify-content:center;overflow:hidden}
.doctor-banner::before{content:'';position:absolute;inset:0;background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><g fill='none' stroke='white' stroke-opacity='.12' stroke-width='.6'><circle cx='20' cy='25' r='8'/><path d='M16 25h8M20 21v8'/><circle cx='75' cy='70' r='6'/><path d='M72 70h6M75 67v6'/><path d='M10 75q5-8 12-3t10 5' /><path d='M65 20q5-5 10 0t8 8'/><circle cx='50' cy='50' r='1.5' fill='white' fill-opacity='.18'/></g></svg>");background-size:240px;background-repeat:repeat;opacity:.9;pointer-events:none}
.doctor-banner::after{content:'';position:absolute;top:-50%;right:-30%;width:300px;height:300px;background:radial-gradient(circle,rgba(201,165,92,.22),transparent 60%);border-radius:50%}
.doctor-avatar{position:absolute;bottom:-48px;width:104px;height:104px;border-radius:50%;background:linear-gradient(135deg,#0d8b8b,#14b8a6);border:5px solid var(--white);box-shadow:0 16px 40px -8px rgba(10,37,64,.32),0 6px 16px -4px rgba(10,37,64,.18);display:flex;align-items:center;justify-content:center;color:var(--white);z-index:2;font-family:var(--serif);font-size:2.3rem;font-weight:700;letter-spacing:.03em;transition:transform .5s var(--ease)}
.doctor-card:hover .doctor-avatar{transform:scale(1.05) rotate(-3deg)}
.doctor-avatar.av-teal{background:linear-gradient(135deg,#0d8b8b,#14b8a6)}
.doctor-avatar.av-navy{background:linear-gradient(135deg,#1e3a8a,#0a2540)}
.doctor-avatar.av-gold{background:linear-gradient(135deg,#b8860b,#d97706)}
.doctor-avatar.av-emerald{background:linear-gradient(135deg,#047857,#10b981)}
.doctor-info{padding:60px 28px 28px;text-align:center}
.doctor-info h3{font-family:var(--serif);font-size:1.45rem;font-weight:600;color:var(--navy);margin-bottom:6px;letter-spacing:-.01em}
.specialty{color:var(--teal);font-weight:600;margin-bottom:18px;font-size:.94rem;letter-spacing:.01em}
.qualifications{color:var(--text-soft);font-size:.9rem;margin-bottom:20px;line-height:1.75;padding:16px;background:var(--bg-alt);border-radius:12px;text-align:left}
.qualifications strong{color:var(--navy);display:block;margin-bottom:6px;font-size:.92rem}
.qualifications .qual-line{display:block;padding-left:14px;position:relative}
.qualifications .qual-line::before{content:'';position:absolute;left:0;top:9px;width:6px;height:6px;background:var(--teal);border-radius:50%}
.timing{background:linear-gradient(135deg,var(--teal-bg),#f0fdfa);padding:14px 18px;border-radius:12px;font-size:.9rem;border-left:3px solid var(--teal);text-align:left;color:var(--navy);font-weight:500}
.timing strong{color:var(--teal)}
.doctor-card .specialties-list{margin:18px 0;display:flex;flex-wrap:wrap;gap:6px;justify-content:center}
.spec-chip{background:var(--bg-alt);color:var(--text);padding:5px 12px;border-radius:30px;font-size:.78rem;font-weight:500;border:1px solid var(--border-soft)}

/* === Hero visual (image) === */
.hero-visual{position:relative;animation:slideUp .8s var(--ease) .25s both}
.hero-visual-main{position:relative;aspect-ratio:4/5;border-radius:24px;overflow:hidden;box-shadow:var(--shadow-lg);background:linear-gradient(135deg,var(--navy),var(--teal))}
.hero-visual-main img{width:100%;height:100%;object-fit:cover;display:block;transition:transform 1s var(--ease)}
.hero-visual:hover .hero-visual-main img{transform:scale(1.04)}
.hero-visual-main::after{content:'';position:absolute;inset:0;background:linear-gradient(180deg,transparent 50%,rgba(10,37,64,.32) 100%);pointer-events:none}
.hero-float-card{position:absolute;background:rgba(255,255,255,.97);backdrop-filter:saturate(180%) blur(18px);-webkit-backdrop-filter:saturate(180%) blur(18px);padding:14px 18px;border-radius:14px;box-shadow:0 14px 36px rgba(10,37,64,.18);display:flex;align-items:center;gap:12px;z-index:2;animation:bob 4s ease-in-out infinite;border:1px solid rgba(255,255,255,.6)}
.hero-float-card.fc-top{top:34px;right:-18px}
.hero-float-card.fc-bot{bottom:34px;left:-18px;animation-delay:1.6s}
.hero-float-icon{width:42px;height:42px;background:linear-gradient(135deg,var(--teal),var(--teal-light));color:var(--white);border-radius:12px;display:flex;align-items:center;justify-content:center;flex-shrink:0;box-shadow:0 6px 14px rgba(13,139,139,.32)}
.hero-float-icon.fc-gold{background:linear-gradient(135deg,#b8860b,#d97706);box-shadow:0 6px 14px rgba(184,134,11,.32)}
.hero-float-icon svg{width:22px;height:22px}
.hero-float-text strong{display:block;color:var(--navy);font-size:.96rem;font-weight:700;line-height:1.1}
.hero-float-text span{color:var(--text-mute);font-size:.74rem;letter-spacing:.06em;text-transform:uppercase;font-weight:600}

/* === Featured Specialists section === */
.specialists-section{padding:90px 24px;background:var(--bg);position:relative;overflow:hidden}
.specialists-section::before{content:'';position:absolute;top:0;right:0;width:400px;height:400px;background:radial-gradient(circle,rgba(13,139,139,.08),transparent 70%);border-radius:50%;pointer-events:none}
.specialists-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:22px;max-width:1280px;margin:0 auto;position:relative}
.specialist-mini{background:var(--white);border-radius:var(--radius-lg);padding:36px 22px 28px;text-align:center;border:1px solid var(--border-soft);transition:all .4s var(--ease);position:relative;overflow:hidden}
.specialist-mini::before{content:'';position:absolute;top:0;left:0;right:0;height:5px;background:linear-gradient(90deg,var(--teal),var(--gold));transform:scaleX(0);transform-origin:left;transition:transform .5s var(--ease)}
.specialist-mini:hover{transform:translateY(-8px);box-shadow:var(--shadow-lg);border-color:var(--teal-bg)}
.specialist-mini:hover::before{transform:scaleX(1)}
.specialist-avatar{width:84px;height:84px;border-radius:50%;background:linear-gradient(135deg,var(--navy),var(--teal));margin:0 auto 18px;display:flex;align-items:center;justify-content:center;color:var(--white);font-family:var(--serif);font-size:1.65rem;font-weight:600;letter-spacing:.03em;box-shadow:0 10px 22px rgba(13,139,139,.3);transition:transform .4s var(--ease)}
.specialist-mini:hover .specialist-avatar{transform:scale(1.06) rotate(-4deg)}
.specialist-avatar.av-teal{background:linear-gradient(135deg,#0d8b8b,#14b8a6);box-shadow:0 10px 22px rgba(13,139,139,.32)}
.specialist-avatar.av-navy{background:linear-gradient(135deg,#1e3a8a,#0a2540);box-shadow:0 10px 22px rgba(10,37,64,.3)}
.specialist-avatar.av-gold{background:linear-gradient(135deg,#b8860b,#d97706);box-shadow:0 10px 22px rgba(184,134,11,.3)}
.specialist-avatar.av-emerald{background:linear-gradient(135deg,#047857,#10b981);box-shadow:0 10px 22px rgba(4,120,87,.3)}
.specialist-mini h4{font-family:var(--serif);font-size:1.12rem;font-weight:600;color:var(--navy);margin-bottom:5px;line-height:1.25;letter-spacing:-.01em}
.specialist-mini .role{color:var(--teal);font-size:.85rem;font-weight:600;margin-bottom:14px;letter-spacing:.01em}
.specialist-mini .time-pill{display:inline-block;background:var(--bg-alt);color:var(--text);font-size:.78rem;padding:6px 12px;border-radius:30px;font-weight:500;border:1px solid var(--border-soft)}
@media (max-width:1024px){.specialists-grid{grid-template-columns:repeat(2,1fr)}}
@media (max-width:560px){.specialists-grid{grid-template-columns:1fr;gap:16px}}

/* === About Preview (image split) === */
.about-preview{padding:100px 24px;background:var(--white);position:relative}
.about-preview-inner{max-width:1280px;margin:0 auto;display:grid;grid-template-columns:1fr 1fr;gap:60px;align-items:center}
.about-preview-img{position:relative;border-radius:22px;overflow:hidden;aspect-ratio:5/4;box-shadow:var(--shadow-lg);background:linear-gradient(135deg,var(--navy),var(--teal))}
.about-preview-img img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .9s var(--ease)}
.about-preview-img:hover img{transform:scale(1.05)}
.about-preview-img::after{content:'';position:absolute;inset:0;background:linear-gradient(160deg,transparent 40%,rgba(10,37,64,.35) 100%);pointer-events:none}
.about-float-stat{position:absolute;bottom:22px;left:22px;right:22px;background:rgba(255,255,255,.97);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);padding:18px 22px;border-radius:14px;display:flex;gap:24px;align-items:center;z-index:2;box-shadow:0 14px 36px rgba(10,37,64,.2);border:1px solid rgba(255,255,255,.7)}
.about-float-stat .stat{flex:1;text-align:center;border-right:1px solid var(--border-soft);padding-right:18px}
.about-float-stat .stat:last-child{border-right:none;padding-right:0}
.about-float-stat .stat .n{font-family:var(--serif);font-size:1.5rem;color:var(--navy);font-weight:700;line-height:1;letter-spacing:-.02em}
.about-float-stat .stat .l{font-size:.74rem;color:var(--text-mute);letter-spacing:.05em;text-transform:uppercase;margin-top:4px;font-weight:600}
.about-preview-content h2{font-family:var(--serif);font-size:clamp(1.9rem,3.2vw,2.7rem);font-weight:600;color:var(--navy);line-height:1.15;letter-spacing:-.02em;margin-bottom:20px}
.about-preview-content h2 em{font-style:italic;color:var(--teal);font-weight:500}
.about-preview-content p.lead{color:var(--text-soft);font-size:1.06rem;margin-bottom:28px;line-height:1.7}
.about-features{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:30px}
.about-feature{display:flex;gap:12px;align-items:flex-start}
.about-feature-icon{width:40px;height:40px;background:linear-gradient(135deg,var(--teal-bg),#fff);border:1px solid rgba(13,139,139,.18);color:var(--teal);border-radius:11px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.about-feature-icon svg{width:20px;height:20px}
.about-feature-text strong{color:var(--navy);font-size:.96rem;font-weight:600;display:block;margin-bottom:3px}
.about-feature-text span{color:var(--text-soft);font-size:.85rem;line-height:1.5}
@media (max-width:900px){.about-preview-inner{grid-template-columns:1fr;gap:40px}.about-features{grid-template-columns:1fr}}

.why-section{background:var(--bg-alt);padding:90px 24px}
.why-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:24px;max-width:1280px;margin:0 auto}
.why-box{background:var(--white);padding:36px 28px;border-radius:var(--radius-lg);text-align:center;border:1px solid var(--border-soft);transition:all .35s var(--ease);position:relative;overflow:hidden}
.why-box:hover{transform:translateY(-4px);box-shadow:var(--shadow)}
.why-icon{width:64px;height:64px;background:linear-gradient(135deg,var(--navy),var(--teal));color:var(--white);border-radius:18px;display:flex;align-items:center;justify-content:center;margin:0 auto 20px;box-shadow:0 8px 20px rgba(13,139,139,.25)}
.why-icon svg{width:30px;height:30px}
.why-box h3{font-family:var(--serif);font-size:1.2rem;font-weight:600;color:var(--navy);margin-bottom:10px}
.why-box p{color:var(--text-soft);font-size:.92rem;line-height:1.6}

.camp-banner{background:linear-gradient(135deg,var(--emerald-deep) 0%,var(--emerald) 55%,var(--emerald-light) 100%);color:var(--white);padding:60px 24px;text-align:center;position:relative;overflow:hidden}
.camp-banner::before{content:'';position:absolute;inset:0;background-image:repeating-linear-gradient(45deg,transparent,transparent 30px,rgba(255,255,255,.025) 30px,rgba(255,255,255,.025) 60px);pointer-events:none}
.camp-banner-inner{position:relative;max-width:900px;margin:0 auto}
.camp-banner .tag{display:inline-block;background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.2);padding:6px 16px;border-radius:30px;font-size:.78rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;margin-bottom:16px}
.camp-banner h2{font-family:var(--serif);font-size:clamp(1.8rem,3.2vw,2.6rem);font-weight:600;line-height:1.15;margin-bottom:14px;letter-spacing:-.01em}
.camp-banner p{font-size:1.08rem;margin-bottom:26px;opacity:.95;max-width:600px;margin-left:auto;margin-right:auto}
.camp-pills{display:flex;justify-content:center;gap:12px;flex-wrap:wrap}
.camp-pill{background:var(--white);color:var(--emerald-deep);padding:10px 22px;border-radius:50px;font-weight:700;font-size:.92rem;letter-spacing:.02em;box-shadow:0 6px 18px rgba(0,0,0,.18)}

.about-content{max-width:1200px;margin:0 auto;display:grid;grid-template-columns:1fr 1fr;gap:64px;align-items:center}
.about-text h2{font-family:var(--serif);font-size:clamp(1.9rem,3.4vw,2.6rem);font-weight:600;color:var(--navy);margin-bottom:20px;line-height:1.15;letter-spacing:-.02em}
.about-text h2 em{font-style:italic;color:var(--teal);font-weight:500}
.about-text p{color:var(--text-soft);margin-bottom:16px;font-size:1rem;line-height:1.75}
.about-text ul{list-style:none;margin-top:24px;display:grid;gap:12px}
.about-text ul li{padding:14px 18px;background:var(--white);border-radius:12px;border:1px solid var(--border-soft);display:flex;align-items:center;gap:14px;font-weight:500;color:var(--navy);transition:all .25s var(--ease)}
.about-text ul li:hover{border-color:var(--teal);transform:translateX(4px)}
.about-text ul li::before{content:'';width:24px;height:24px;background:var(--teal);border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='20 6 9 17 4 12'%3E%3C/polyline%3E%3C/svg%3E");background-size:14px;background-repeat:no-repeat;background-position:center}
.about-visual{position:relative}
.about-card{background:linear-gradient(135deg,var(--white) 0%,var(--bg-alt) 100%);border-radius:var(--radius-lg);padding:50px 40px;box-shadow:var(--shadow-lg);border:1px solid var(--border-soft);text-align:center;position:relative;overflow:hidden}
.about-card::before{content:'';position:absolute;top:-50px;right:-50px;width:200px;height:200px;background:radial-gradient(circle,rgba(13,139,139,.08),transparent 70%);border-radius:50%}
.about-card-mark{width:120px;height:120px;background:linear-gradient(135deg,var(--navy),var(--teal));border-radius:28px;margin:0 auto 24px;position:relative;box-shadow:0 16px 40px rgba(13,139,139,.3)}
.about-card-mark::before,.about-card-mark::after{content:'';position:absolute;background:var(--white);border-radius:8px;top:50%;left:50%;transform:translate(-50%,-50%)}
.about-card-mark::before{width:60px;height:14px}
.about-card-mark::after{width:14px;height:60px}
.about-card h3{font-family:var(--serif);font-size:1.6rem;color:var(--navy);margin-bottom:8px;font-weight:600}
.about-card .tag{color:var(--teal);font-size:.86rem;font-weight:600;letter-spacing:.1em;text-transform:uppercase}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:22px;max-width:1200px;margin:70px auto 0}
.stat-box{background:var(--white);padding:32px 24px;border-radius:var(--radius-lg);text-align:center;border:1px solid var(--border-soft);position:relative;overflow:hidden;transition:all .35s var(--ease)}
.stat-box::before{content:'';position:absolute;left:0;top:0;bottom:0;width:4px;background:linear-gradient(to bottom,var(--teal),var(--gold));transform:scaleY(0);transform-origin:top;transition:transform .4s var(--ease)}
.stat-box:hover{transform:translateY(-4px);box-shadow:var(--shadow)}
.stat-box:hover::before{transform:scaleY(1)}
.stat-box h3{font-family:var(--serif);font-size:2.4rem;color:var(--navy);margin-bottom:6px;font-weight:700;letter-spacing:-.02em}
.stat-box h3 .plus{color:var(--teal)}
.stat-box p{color:var(--text-soft);font-size:.92rem;font-weight:500}

.page-banner{background:linear-gradient(135deg,var(--navy) 0%,var(--navy-light) 50%,var(--teal) 100%);color:var(--white);padding:80px 24px;text-align:center;position:relative;overflow:hidden}
.page-banner::before{content:'';position:absolute;inset:0;background-image:radial-gradient(circle at 30% 40%,rgba(255,255,255,.08),transparent 50%),radial-gradient(circle at 70% 60%,rgba(201,165,92,.15),transparent 50%)}
.page-banner-content{position:relative;max-width:800px;margin:0 auto}
.page-banner h1{font-family:var(--serif);font-size:clamp(2rem,3.6vw,3rem);font-weight:600;margin-bottom:12px;letter-spacing:-.02em;line-height:1.1}
.page-banner p{font-size:1.08rem;color:#cbd5e1}
.breadcrumb{display:inline-flex;gap:10px;font-size:.85rem;color:var(--gold-light);margin-bottom:14px;align-items:center;letter-spacing:.04em}
.breadcrumb a:hover{color:var(--white)}

.contact-section{display:grid;grid-template-columns:1fr 1.1fr;gap:36px;max-width:1200px;margin:0 auto}
.contact-info{background:linear-gradient(135deg,var(--navy) 0%,var(--navy-light) 100%);color:var(--white);padding:44px;border-radius:var(--radius-lg);position:relative;overflow:hidden}
.contact-info::before{content:'';position:absolute;top:-100px;right:-100px;width:300px;height:300px;background:radial-gradient(circle,rgba(13,139,139,.18),transparent 70%);border-radius:50%}
.contact-info h2{font-family:var(--serif);font-size:1.8rem;margin-bottom:8px;font-weight:600;letter-spacing:-.01em;position:relative}
.contact-info .sub{color:#cbd5e1;font-size:.95rem;margin-bottom:30px;position:relative}
.contact-item{display:flex;gap:16px;margin-bottom:22px;position:relative;align-items:flex-start}
.contact-item-icon{width:46px;height:46px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);border-radius:12px;display:flex;align-items:center;justify-content:center;flex-shrink:0;color:var(--gold-light)}
.contact-item-icon svg{width:20px;height:20px}
.contact-item h4{font-size:.78rem;color:var(--gold-light);font-weight:600;letter-spacing:.1em;text-transform:uppercase;margin-bottom:4px}
.contact-item p{font-size:.96rem;color:#e2e8f0;line-height:1.55}
.contact-item p a{color:var(--white);font-weight:600}
.contact-item p a:hover{color:var(--gold-light)}
.appointment-form{background:var(--white);padding:44px;border-radius:var(--radius-lg);box-shadow:var(--shadow);border:1px solid var(--border-soft)}
.appointment-form h2{font-family:var(--serif);font-size:1.7rem;margin-bottom:8px;color:var(--navy);font-weight:600;letter-spacing:-.01em}
.appointment-form .form-sub{color:var(--text-soft);font-size:.94rem;margin-bottom:28px}
.form-group{margin-bottom:18px}
.form-group label{display:block;margin-bottom:7px;font-weight:600;color:var(--navy);font-size:.88rem;letter-spacing:.01em}
.form-group input,.form-group select,.form-group textarea{width:100%;padding:13px 16px;border:1.5px solid var(--border);border-radius:10px;font-size:.96rem;font-family:var(--sans);background:var(--bg);transition:all .25s var(--ease);color:var(--text)}
.form-group input:focus,.form-group select:focus,.form-group textarea:focus{outline:none;border-color:var(--teal);background:var(--white);box-shadow:0 0 0 4px rgba(13,139,139,.08)}
.form-group textarea{resize:vertical;min-height:110px}
.success-msg{background:#dcfce7;color:#166534;padding:13px 16px;border-radius:10px;margin-bottom:15px;text-align:center;display:none;border:1px solid #86efac;font-weight:500;font-size:.92rem}
.error-msg{background:#fee2e2;color:#991b1b;padding:13px 16px;border-radius:10px;margin-bottom:15px;text-align:center;display:none;border:1px solid #fca5a5;font-weight:500;font-size:.92rem}

.footer{background:var(--navy-dark);color:#cbd5e1;padding:60px 24px 24px;position:relative;overflow:hidden}
.footer::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--teal),var(--gold),var(--teal))}
.footer-content{max-width:1280px;margin:0 auto;display:grid;grid-template-columns:1.4fr 1fr 1fr 1.2fr;gap:40px;margin-bottom:40px}
.footer-col h3{font-family:var(--serif);font-size:1.05rem;color:var(--white);font-weight:600;margin-bottom:20px;letter-spacing:-.01em}
.footer-col p,.footer-col a{color:#94a3b8;margin-bottom:10px;display:block;font-size:.92rem;line-height:1.65}
.footer-col a:hover{color:var(--teal-light)}
.footer-brand .logo{margin-bottom:18px}
.footer-brand .logo-mark{width:42px;height:42px}
.footer-brand .logo-mark::before{width:20px;height:5px}
.footer-brand .logo-mark::after{width:5px;height:20px}
.footer-brand .logo-text{color:var(--white)}
.footer-brand .logo-text span{color:var(--teal-light)}
.footer-brand p{max-width:280px;color:#94a3b8}
.footer-contact{display:flex;gap:10px;align-items:flex-start;margin-bottom:12px}
.footer-contact .icn{color:var(--gold-light);flex-shrink:0;margin-top:3px}
.footer-contact .icn svg{width:14px;height:14px}
.footer-bottom{text-align:center;padding-top:24px;border-top:1px solid rgba(255,255,255,.06);color:#64748b;font-size:.86rem}

.map-section{padding:80px 24px;background:var(--bg-alt)}
.map-container{max-width:1200px;margin:0 auto;border-radius:var(--radius-lg);overflow:hidden;box-shadow:var(--shadow);border:1px solid var(--border-soft)}
.map-container iframe{width:100%;height:420px;border:none;display:block;filter:saturate(1.1)}

.admin-bg{min-height:100vh;background:linear-gradient(135deg,var(--navy) 0%,var(--navy-light) 50%,var(--teal) 100%);display:flex;align-items:center;justify-content:center;padding:20px;position:relative;overflow:hidden}
.admin-bg::before{content:'';position:absolute;inset:0;background-image:radial-gradient(circle at 20% 30%,rgba(201,165,92,.18),transparent 40%),radial-gradient(circle at 80% 70%,rgba(13,139,139,.25),transparent 40%);pointer-events:none}
.login-box{background:rgba(255,255,255,.98);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);padding:50px 44px;border-radius:24px;box-shadow:0 30px 80px rgba(0,0,0,.3);max-width:440px;width:100%;position:relative;z-index:1}
.login-box .login-logo{text-align:center;margin-bottom:24px}
.login-box .login-mark{width:84px;height:84px;background:linear-gradient(135deg,var(--navy),var(--teal));border-radius:20px;margin:0 auto;position:relative;box-shadow:0 16px 40px rgba(13,139,139,.35)}
.login-box .login-mark::before,.login-box .login-mark::after{content:'';position:absolute;background:var(--white);border-radius:5px;top:50%;left:50%;transform:translate(-50%,-50%)}
.login-box .login-mark::before{width:40px;height:10px}
.login-box .login-mark::after{width:10px;height:40px}
.login-box h1{text-align:center;font-family:var(--serif);color:var(--navy);font-size:1.7rem;margin-bottom:6px;font-weight:600}
.login-box .subtitle{text-align:center;color:var(--text-soft);margin-bottom:32px;font-size:.92rem}
.login-hint{background:linear-gradient(135deg,#fef3c7,#fde68a);color:#92400e;padding:12px;border-radius:10px;font-size:.82rem;margin-top:18px;text-align:center;border-left:3px solid #f59e0b}
.admin-layout{display:flex;min-height:100vh;background:var(--bg-alt)}
.sidebar{width:270px;background:var(--navy-dark);color:var(--white);padding:28px 0;flex-shrink:0;position:sticky;top:0;height:100vh;overflow-y:auto}
.sidebar-logo{padding:0 26px 26px;border-bottom:1px solid rgba(255,255,255,.06);margin-bottom:22px;display:flex;align-items:center;gap:12px}
.sidebar-logo .logo-mark{width:38px;height:38px;border-radius:10px;box-shadow:0 4px 12px rgba(13,139,139,.4)}
.sidebar-logo .logo-mark::before{width:18px;height:4px}
.sidebar-logo .logo-mark::after{width:4px;height:18px}
.sidebar-logo .logo-text{color:var(--white);font-size:1rem}
.sidebar-logo .logo-text span{color:var(--teal-light);font-size:.65rem}
.sidebar-menu{list-style:none}
.sidebar-menu a{display:flex;align-items:center;gap:13px;padding:14px 26px;color:#94a3b8;border-left:3px solid transparent;font-size:.94rem;font-weight:500;transition:all .25s var(--ease)}
.sidebar-menu a:hover,.sidebar-menu a.active{background:rgba(13,139,139,.12);color:var(--white);border-left-color:var(--teal)}
.logout-btn{margin:24px 26px;padding:13px;background:var(--red);color:#fff;border:none;border-radius:10px;cursor:pointer;width:calc(100% - 52px);font-weight:600;font-family:inherit;transition:all .25s var(--ease)}
.logout-btn:hover{background:var(--red-dark)}
.main-area{flex:1;padding:36px;overflow-x:auto}
.admin-header{margin-bottom:32px}
.admin-header h1{font-family:var(--serif);font-size:1.9rem;color:var(--navy);font-weight:600;letter-spacing:-.01em}
.admin-header .welcome{color:var(--text-soft);margin-top:4px}
.dashboard-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:20px;margin-bottom:32px}
.dash-card{background:var(--white);padding:26px;border-radius:14px;box-shadow:var(--shadow-sm);display:flex;justify-content:space-between;align-items:center;border-left:4px solid var(--teal);transition:transform .25s var(--ease)}
.dash-card:hover{transform:translateY(-3px);box-shadow:var(--shadow)}
.dash-card .info h3{font-family:var(--serif);font-size:2.2rem;margin-bottom:4px;color:var(--navy);font-weight:700}
.dash-card .info p{color:var(--text-soft);font-size:.9rem;font-weight:500}
.dash-card .icon{width:54px;height:54px;background:linear-gradient(135deg,var(--teal-bg),#fff);border-radius:12px;display:flex;align-items:center;justify-content:center;color:var(--teal)}
.dash-card .icon svg{width:24px;height:24px}
.data-card{background:var(--white);border-radius:14px;box-shadow:var(--shadow-sm);padding:28px;margin-bottom:26px}
.data-card-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px;flex-wrap:wrap;gap:12px}
.data-card-header h2{font-family:var(--serif);font-size:1.3rem;color:var(--navy);font-weight:600}
.search-box{padding:10px 16px;border:1.5px solid var(--border);border-radius:10px;outline:none;font-family:inherit;background:var(--bg);min-width:200px;transition:all .25s var(--ease)}
.search-box:focus{border-color:var(--teal);background:var(--white)}
.appt-table{width:100%;border-collapse:collapse;font-size:.92rem}
.appt-table th{background:var(--bg-alt);padding:13px;text-align:left;font-weight:600;border-bottom:2px solid var(--border);white-space:nowrap;color:var(--navy);font-size:.86rem;letter-spacing:.02em}
.appt-table td{padding:13px;border-bottom:1px solid var(--border-soft);color:var(--text)}
.appt-table tr:hover td{background:var(--bg)}
.status-badge{display:inline-block;padding:4px 12px;border-radius:30px;font-size:.78rem;font-weight:600;letter-spacing:.02em}
.status-pending{background:#fef3c7;color:#92400e}
.status-confirmed{background:#dcfce7;color:#166534}
.status-completed{background:#dbeafe;color:#1e40af}
.status-cancelled{background:#fee2e2;color:#991b1b}
.action-btn{padding:6px 12px;border:none;border-radius:7px;cursor:pointer;font-size:.82rem;margin:2px;font-family:inherit;font-weight:500;transition:all .25s var(--ease)}
.btn-confirm{background:#10b981;color:#fff}
.btn-complete{background:#3b82f6;color:#fff}
.btn-cancel{background:#f59e0b;color:#fff}
.btn-delete{background:#94a3b8;color:#fff}
.action-btn:hover{transform:translateY(-1px);filter:brightness(1.08)}
.add-form{display:grid;grid-template-columns:1fr 1fr;gap:15px;margin-bottom:18px}
.add-form .full{grid-column:1/-1}
.add-form input,.add-form select,.add-form textarea{width:100%;padding:11px 14px;border:1.5px solid var(--border);border-radius:10px;font-family:inherit;background:var(--bg)}
.add-form input:focus,.add-form select:focus,.add-form textarea:focus{outline:none;border-color:var(--teal);background:var(--white)}
.info-grid{display:grid;gap:14px;max-width:640px}
.info-grid div{padding:10px 0;border-bottom:1px solid var(--border-soft);color:var(--text)}
.info-grid strong{color:var(--navy);font-weight:600}
.empty-state{text-align:center;padding:60px 20px;color:var(--text-soft)}
.empty-state .big-icon{font-size:3.6rem;margin-bottom:16px;opacity:.4}
.empty-state h3{color:var(--navy);font-family:var(--serif);font-weight:600}
.loading{text-align:center;padding:60px;color:var(--text-soft)}
.toast{position:fixed;top:24px;right:24px;background:linear-gradient(135deg,#10b981,#059669);color:#fff;padding:14px 24px;border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.18);z-index:9999;font-weight:500;animation:toastIn .4s var(--ease);max-width:380px}
.toast.error{background:linear-gradient(135deg,#ef4444,#dc2626)}
@keyframes toastIn{from{opacity:0;transform:translateX(40px)}to{opacity:1;transform:translateX(0)}}

.reveal{opacity:0;transform:translateY(28px);transition:opacity .8s var(--ease),transform .8s var(--ease)}
.reveal.in{opacity:1;transform:translateY(0)}

@media(max-width:1024px){
  .hero-content,.contact-section,.about-content{grid-template-columns:1fr;gap:40px}
  .footer-content{grid-template-columns:1fr 1fr}
  .trust-grid{grid-template-columns:repeat(2,1fr)}
  .trust-item:nth-child(2){border-right:none}
  .trust-item:nth-child(1),.trust-item:nth-child(2){border-bottom:1px solid rgba(255,255,255,.08);padding-bottom:24px}
  .trust-item:nth-child(3),.trust-item:nth-child(4){padding-top:24px}
}
@media(max-width:768px){
  .menu-toggle{display:flex}
  .nav-menu{position:fixed;top:64px;left:0;right:0;background:var(--white);flex-direction:column;padding:18px;gap:6px;box-shadow:var(--shadow-lg);display:none;border-top:1px solid var(--border-soft);max-height:calc(100vh - 64px);overflow-y:auto}
  .nav-menu.active{display:flex}
  .nav-menu a{padding:12px 16px;width:100%}
  .top-bar-content{flex-direction:column;text-align:center;font-size:.78rem}
  .hero{padding:50px 20px 70px}
  .section{padding:60px 20px}
  .why-section,.offers-section{padding:60px 20px}
  .section-head{margin-bottom:40px}
  .trust-strip{padding:36px 20px}
  .trust-grid{gap:18px}
  .trust-item .num{font-size:2rem}
  .admin-layout{flex-direction:column}
  .sidebar{width:100%;height:auto;position:relative;padding:18px 0}
  .sidebar-menu{display:flex;overflow-x:auto;padding:0 12px}
  .sidebar-menu a{white-space:nowrap;padding:10px 16px;border-left:none;border-bottom:3px solid transparent}
  .sidebar-menu a.active{border-left:none;border-bottom-color:var(--teal)}
  .sidebar-logo{display:none}
  .logout-btn{margin:12px}
  .main-area{padding:22px 16px}
  .appt-table{font-size:.82rem}
  .appt-table th,.appt-table td{padding:9px}
  .add-form{grid-template-columns:1fr}
  .footer-content{grid-template-columns:1fr;gap:30px}
  .appointment-form,.contact-info{padding:30px 24px}
  .login-box{padding:36px 28px}
  .hero-image{height:340px}
  .hero-image-wrap{min-height:auto}
  .hero-float-stats{bottom:14px;left:14px;right:14px;padding:14px 16px;gap:14px}
  .hero-float-discount{top:14px;right:14px;padding:12px 14px}
  .hf-num{font-size:1.4rem}
  .hf-discount-num{font-size:1rem}
  .fd-grid{grid-template-columns:repeat(2,1fr);gap:18px}
  .featured-docs{padding:60px 18px}
  .facility-grid{grid-template-columns:1fr;gap:40px}
  .facility-section{padding:60px 18px}
  .test-grid{grid-template-columns:1fr;gap:18px}
  .testimonials{padding:60px 18px}
  .test-quote{min-height:auto}
  .glm-grid{grid-template-columns:1fr 1fr;grid-template-rows:repeat(3,180px);gap:12px}
  .glm-card:nth-child(1){grid-row:1/2;grid-column:1/3}
  .glimpses{padding:60px 18px}
  .wa-float{bottom:18px;right:18px}
  .wa-float-icon{width:54px;height:54px}
}
@media(max-width:480px){
  .hero h1{font-size:2rem}
  .section-head h2{font-size:1.6rem}
  .page-banner h1{font-size:1.8rem}
  .btn{padding:12px 22px;font-size:.92rem}
  .hero-cta{flex-direction:column;align-items:stretch}
  .hero-cta .btn{justify-content:center}
  .fd-grid{grid-template-columns:1fr;gap:16px}
  .hero-image{height:280px}
  .facility-features{gap:10px}
}

::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-track{background:var(--bg-alt)}
::-webkit-scrollbar-thumb{background:linear-gradient(to bottom,var(--teal),var(--navy));border-radius:5px}
::-webkit-scrollbar-thumb:hover{background:var(--navy)}

/* Gallery / Glimpses section */
.glimpses{padding:80px 24px;background:var(--white);position:relative}
.glm-grid{max-width:1280px;margin:0 auto;display:grid;grid-template-columns:1.4fr 1fr 1fr;grid-template-rows:240px 240px;gap:18px}
.glm-card{position:relative;border-radius:var(--radius-lg);overflow:hidden;cursor:pointer;background:var(--bg-alt);box-shadow:0 12px 30px -10px rgba(10,37,64,.18)}
.glm-card:nth-child(1){grid-row:1/3}
.glm-card img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .8s var(--ease)}
.glm-card:hover img{transform:scale(1.08)}
.glm-card::after{content:'';position:absolute;inset:0;background:linear-gradient(to top,rgba(10,37,64,.75) 0%,rgba(10,37,64,.15) 50%,transparent 100%);pointer-events:none}
.glm-label{position:absolute;left:18px;bottom:16px;color:var(--white);font-family:var(--serif);font-weight:600;font-size:1.05rem;letter-spacing:.01em;z-index:2;display:flex;align-items:center;gap:8px}
.glm-label::before{content:'';width:24px;height:1.5px;background:var(--gold-light);border-radius:1px}
.glm-card:nth-child(1) .glm-label{font-size:1.3rem}

/* Testimonials section */
.testimonials{padding:90px 24px;background:linear-gradient(180deg,var(--bg-alt) 0%,var(--white) 100%);position:relative;overflow:hidden}
.testimonials::before{content:'';position:absolute;top:-150px;left:-100px;width:400px;height:400px;background:radial-gradient(circle,rgba(201,165,92,.08),transparent 60%);border-radius:50%;pointer-events:none}
.testimonials::after{content:'';position:absolute;bottom:-150px;right:-100px;width:400px;height:400px;background:radial-gradient(circle,rgba(13,139,139,.08),transparent 60%);border-radius:50%;pointer-events:none}
.test-grid{max-width:1280px;margin:0 auto;display:grid;grid-template-columns:repeat(3,1fr);gap:28px;position:relative}
.test-card{background:var(--white);border-radius:var(--radius-lg);padding:34px 30px 28px;border:1px solid var(--border-soft);position:relative;transition:all .45s var(--ease);box-shadow:0 4px 20px -8px rgba(10,37,64,.08)}
.test-card::before{content:'\201C';position:absolute;top:-10px;left:24px;font-family:var(--serif);font-size:5rem;color:var(--teal);line-height:1;opacity:.18;font-weight:700}
.test-card:hover{transform:translateY(-6px);box-shadow:var(--shadow-lg);border-color:transparent}
.test-stars{display:flex;gap:3px;margin-bottom:18px;color:var(--gold)}
.test-quote{color:var(--text);font-size:1.02rem;line-height:1.65;margin-bottom:24px;font-style:italic;min-height:60px;font-weight:500}
.test-author{display:flex;align-items:center;gap:14px;padding-top:20px;border-top:1px solid var(--border-soft)}
.test-avatar{width:48px;height:48px;border-radius:50%;display:flex;align-items:center;justify-content:center;color:var(--white);font-family:var(--serif);font-weight:600;font-size:1.05rem;flex-shrink:0}
.test-info strong{display:block;color:var(--navy);font-family:var(--serif);font-weight:600;font-size:1rem;letter-spacing:-.01em}
.test-info span{color:var(--text-mute);font-size:.82rem;letter-spacing:.02em}

/* Floating WhatsApp button */
.wa-float{position:fixed;bottom:26px;right:26px;z-index:998;display:flex;align-items:center;gap:0;background:linear-gradient(135deg,#25d366 0%,#128c7e 100%);color:var(--white);padding:0;border-radius:50px;text-decoration:none;box-shadow:0 14px 38px -8px rgba(37,211,102,.55),0 6px 18px -4px rgba(0,0,0,.18);transition:all .4s var(--ease);overflow:hidden;font-family:inherit;border:none;cursor:pointer}
.wa-float::before{content:'';position:absolute;inset:0;border-radius:50px;border:2px solid #25d366;animation:waRing 2.2s ease-out infinite;pointer-events:none}
.wa-float-icon{width:60px;height:60px;display:flex;align-items:center;justify-content:center;flex-shrink:0;position:relative;z-index:1}
.wa-float-label{font-weight:600;font-size:.92rem;letter-spacing:.02em;padding-right:0;max-width:0;opacity:0;overflow:hidden;white-space:nowrap;transition:all .4s var(--ease);position:relative;z-index:1}
.wa-float:hover{transform:translateY(-3px) scale(1.02);box-shadow:0 20px 44px -8px rgba(37,211,102,.65)}
.wa-float:hover .wa-float-label{max-width:220px;opacity:1;padding-right:22px}
@keyframes waRing{0%{transform:scale(1);opacity:.6}100%{transform:scale(1.5);opacity:0}}

/* Animated counter trust-strip */
.trust-item .num[data-count]{display:inline-block}
</style>
</head>
<body>

<div class="page active" id="home-page">
<div class="top-bar"><div class="top-bar-content">
<div class="top-bar-info">
<span><span class="dot"></span>Open Today: 12:00 PM &mdash; 6:00 PM</span>
<span>Endoscopy: 8:00 PM &mdash; 9:00 PM</span>
</div>
<div class="top-bar-info">
<span>Call: 0320 4639794 / 0370 0469037</span>
</div></div></div>

<header class="header"><nav class="navbar">
<a class="logo" onclick="showPage('home')">
<div class="logo-mark"></div>
<div class="logo-text">Sharif Medical Center<span>Consultant Care</span></div>
</a>
<ul class="nav-menu" id="nm1">
<li><a onclick="showPage('home')" class="active">Home</a></li>
<li><a onclick="showPage('about')">About</a></li>
<li><a onclick="showPage('services')">Services</a></li>
<li><a onclick="showPage('doctors')">Doctors</a></li>
<li><a onclick="showPage('contact')">Contact</a></li>
<li><a onclick="showPage('admin-login')" class="admin-link">Admin</a></li>
</ul>
<button class="menu-toggle" onclick="document.getElementById('nm1').classList.toggle('active')">&#9776;</button>
</nav></header>

<section class="hero"><div class="hero-content">
<div class="hero-text">
<div class="hero-badge"><span class="dot"></span>Trusted Healthcare in Lahore</div>
<h1>Compassionate care, <em>expert hands</em>, every single day.</h1>
<p class="hero-sub">Specialist consultation for blood pressure, diabetes, gastroenterology, endoscopy and general medicine &mdash; with a 50% discount on lab tests and ultrasound, plus free Saturday & Sunday medical camps.</p>
<div class="hero-cta">
<a class="btn btn-primary" onclick="showPage('contact')">Book Appointment
<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
</a>
<a class="btn btn-outline" onclick="showPage('services')">Explore Services</a>
</div>
</div>

<div class="hero-image-wrap">
<img class="hero-image" src="https://images.unsplash.com/photo-1612531385446-f7e6d131e1d0?w=900&q=85&auto=format&fit=crop" alt="Medical professional at Sharif Medical Center" loading="eager">
<div class="hero-image-overlay"></div>

<div class="hero-float hero-float-stats">
<div class="hf-row"><div class="hf-num">4</div><div class="hf-lbl">Expert<br>Consultants</div></div>
<div class="hf-row"><div class="hf-num">1000<span>+</span></div><div class="hf-lbl">Patients<br>Treated</div></div>
</div>

<div class="hero-float hero-float-discount">
<div class="hf-discount-icon">
<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="5" x2="5" y2="19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/></svg>
</div>
<div>
<div class="hf-discount-num">50% OFF</div>
<div class="hf-discount-sub">Lab Tests &amp; Ultrasound</div>
</div>
</div>
</div>
</div></section>

<section class="trust-strip"><div class="trust-grid">
<div class="trust-item reveal"><div class="num" data-count="1000" data-suffix="+"><span class="cnum">1000</span><span class="plus">+</span></div><div class="lbl">Happy Patients</div></div>
<div class="trust-item reveal"><div class="num" data-count="4"><span class="cnum">4</span></div><div class="lbl">Expert Consultants</div></div>
<div class="trust-item reveal"><div class="num" data-count="50" data-suffix="%"><span class="cnum">50</span><span class="plus">%</span></div><div class="lbl">Discount on Tests</div></div>
<div class="trust-item reveal"><div class="num" data-count="6"><span class="cnum">6</span></div><div class="lbl">Days a Week</div></div>
</div></section>

<section class="featured-docs">
<div class="section-head reveal">
<span class="eyebrow">Our Specialists</span>
<h2>Meet our <em>expert consultants</em></h2>
<p>A team of dedicated specialists with proven track records across general medicine, gastroenterology and diagnostics.</p>
</div>
<div class="fd-grid">
<div class="fd-card reveal" onclick="showPage('doctors')">
<div class="fd-avatar av-teal">DS</div>
<div class="fd-name">Dr. Shaheena Shafaq</div>
<div class="fd-spec">General Physician</div>
<div class="fd-time">Mon &mdash; Sat &middot; 12 PM &mdash; 6 PM</div>
</div>
<div class="fd-card reveal" onclick="showPage('doctors')">
<div class="fd-avatar av-navy">DI</div>
<div class="fd-name">Dr. Ishfaq Ahmed Cheema</div>
<div class="fd-spec">Gastroenterologist</div>
<div class="fd-time">Daily Night &middot; 8 PM &mdash; 9 PM</div>
</div>
<div class="fd-card reveal" onclick="showPage('doctors')">
<div class="fd-avatar av-gold">DM</div>
<div class="fd-name">Dr. Hafiz Muhammad Mahid</div>
<div class="fd-spec">BP &amp; Sugar Specialist</div>
<div class="fd-time">Sunday &middot; 3 PM &mdash; 6 PM</div>
</div>
<div class="fd-card reveal" onclick="showPage('doctors')">
<div class="fd-avatar av-emerald">DA</div>
<div class="fd-name">Dr. Amjad</div>
<div class="fd-spec">Ultrasonography</div>
<div class="fd-time">On Appointment</div>
</div>
</div>
</section>

<section class="facility-section">
<div class="facility-grid">
<div class="facility-image-wrap reveal">
<img src="https://images.unsplash.com/photo-1519494026892-80bbd2d6fd0d?w=900&q=85&auto=format&fit=crop" alt="Modern medical facility" loading="lazy">
<div class="facility-badge">
<div class="facility-badge-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg></div>
<div class="facility-badge-txt"><strong>Trusted Care</strong><span>Since establishment</span></div>
</div>
</div>
<div class="facility-content reveal">
<span class="eyebrow" style="padding:0 28px 0 0;text-align:left">Our Facility</span>
<h2>A modern medical center <em>built for your comfort</em></h2>
<p>Sharif Medical Center brings together qualified specialists, advanced diagnostic equipment and a comfortable patient-first environment &mdash; right at the heart of Sharqpur Road, Lahore.</p>
<div class="facility-features">
<div class="fac-feat">
<div class="fac-feat-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg></div>
<div class="fac-feat-txt"><strong>Open Six Days a Week</strong><span>Monday to Saturday, 12 PM &mdash; 6 PM &middot; Endoscopy 8&ndash;9 PM</span></div>
</div>
<div class="fac-feat">
<div class="fac-feat-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/></svg></div>
<div class="fac-feat-txt"><strong>Qualified Consultants</strong><span>FCPS-certified specialists and registered general physicians</span></div>
</div>
<div class="fac-feat">
<div class="fac-feat-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/></svg></div>
<div class="fac-feat-txt"><strong>Modern Diagnostics</strong><span>Digital ECG, Ultrasound, Endoscopy and frequency therapy on-site</span></div>
</div>
<div class="fac-feat">
<div class="fac-feat-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78L12 21.23l8.84-8.84a5.5 5.5 0 000-7.78z"/></svg></div>
<div class="fac-feat-txt"><strong>Free Weekly Camps</strong><span>Saturday free checkup &amp; meds &middot; Sunday BP &amp; Sugar free camp</span></div>
</div>
</div>
</div>
</div>
</section>

<section class="testimonials">
<div class="section-head reveal">
<span class="eyebrow">What Patients Say</span>
<h2>Trusted by <em>our community</em></h2>
<p>Real stories from the patients we&rsquo;ve had the privilege to care for.</p>
</div>
<div class="test-grid">

<div class="test-card reveal">
<div class="test-stars">
<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"/></svg>
<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"/></svg>
<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"/></svg>
<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"/></svg>
<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"/></svg>
</div>
<p class="test-quote">Excellent BP &amp; sugar care for my mother. Highly recommended.</p>
<div class="test-author">
<div class="test-avatar av-teal">AR</div>
<div class="test-info"><strong>Ahmed Raza</strong><span>Patient&rsquo;s Son &middot; Lahore</span></div>
</div>
</div>

<div class="test-card reveal">
<div class="test-stars">
<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"/></svg>
<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"/></svg>
<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"/></svg>
<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"/></svg>
<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"/></svg>
</div>
<p class="test-quote">Modern endoscopy. Professional, comfortable experience.</p>
<div class="test-author">
<div class="test-avatar av-navy">FB</div>
<div class="test-info"><strong>Fatima Bibi</strong><span>Verified Patient &middot; Sharqpur</span></div>
</div>
</div>

<div class="test-card reveal">
<div class="test-stars">
<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"/></svg>
<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"/></svg>
<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"/></svg>
<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"/></svg>
<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"/></svg>
</div>
<p class="test-quote">Affordable, caring. The Sunday free camp truly helped.</p>
<div class="test-author">
<div class="test-avatar av-gold">MI</div>
<div class="test-info"><strong>Muhammad Ilyas</strong><span>Regular Patient &middot; Al-Rehman Gardens</span></div>
</div>
</div>

</div>
</section>

<section class="glimpses">
<div class="section-head reveal">
<span class="eyebrow">Inside Our Center</span>
<h2>A glimpse of our <em>healing space</em></h2>
<p>Modern equipment, comfortable rooms and a calm, professional environment built around patient care.</p>
</div>
<div class="glm-grid">
<div class="glm-card reveal">
<img src="https://images.unsplash.com/photo-1666214280391-8ff5bd3c0bf0?w=800&q=85&auto=format&fit=crop" alt="Hospital corridor at Sharif Medical Center" loading="lazy">
<div class="glm-label">Modern Facility</div>
</div>
<div class="glm-card reveal">
<img src="https://images.unsplash.com/photo-1631217868264-e5b90bb7e133?w=600&q=85&auto=format&fit=crop" alt="Advanced medical equipment" loading="lazy">
<div class="glm-label">Diagnostics</div>
</div>
<div class="glm-card reveal">
<img src="https://images.unsplash.com/photo-1559757148-5c350d0d3c56?w=600&q=85&auto=format&fit=crop" alt="Professional medical consultation" loading="lazy">
<div class="glm-label">Consultation</div>
</div>
<div class="glm-card reveal">
<img src="https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?w=600&q=85&auto=format&fit=crop" alt="Patient care and treatment" loading="lazy">
<div class="glm-label">Patient Care</div>
</div>
<div class="glm-card reveal">
<img src="https://images.unsplash.com/photo-1551076805-e1869033e561?w=600&q=85&auto=format&fit=crop" alt="Clinic reception and waiting area" loading="lazy">
<div class="glm-label">Welcoming Space</div>
</div>
</div>
</section>

<section class="section">
<div class="section-head reveal">
<span class="eyebrow">What We Offer</span>
<h2>Comprehensive medical care, <em>under one roof</em></h2>
<p>From routine consultations to advanced endoscopy and laboratory diagnostics &mdash; we treat the conditions that matter most to our community.</p>
</div>
<div class="services-grid">
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12h3l3-9 4 18 3-9h7"/></svg></div><h3>Blood Pressure</h3><p>Accurate BP screening, monitoring and long-term management for hypertension patients.</p></div>
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M9 12h6M12 9v6"/></svg></div><h3>Diabetes Care</h3><p>Sugar testing, diabetes diagnosis, HbA1c assessment and personalised treatment plans.</p><span class="tag tag-discount">HbA1c 50% Off</span></div>
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10 2v7.5L4 16l4 4 4-4 4 4 4-4-6-6.5V2"/></svg></div><h3>Endoscopy</h3><p>Stomach and large intestine examination with modern endoscopic equipment.</p></div>
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L8 7v6c0 4 4 7 4 7s4-3 4-7V7l-4-5z"/></svg></div><h3>Gastroenterology</h3><p>Specialist care for liver, stomach, pancreas, intestines, hepatitis and digestive disorders.</p></div>
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M8 12a4 4 0 018 0"/></svg></div><h3>Ultrasound</h3><p>Advanced ultrasound imaging by qualified radiologists.</p><span class="tag tag-discount">Rs.500 (50% Off)</span></div>
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10 2v6l-4 8a4 4 0 008 0l-4-8V2M8 2h4"/></svg></div><h3>Laboratory Tests</h3><p>Full range of pathology, biochemistry and microbiology tests &mdash; conducted by Zeenat Laboratory.</p><span class="tag tag-discount">50% Off</span></div>
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg></div><h3>Digital ECG</h3><p>Digital electrocardiogram for accurate cardiac rhythm and heart health evaluation.</p></div>
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 1v6M12 17v6M4.22 4.22l4.24 4.24M15.54 15.54l4.24 4.24M1 12h6M17 12h6M4.22 19.78l4.24-4.24M15.54 8.46l4.24-4.24"/></svg></div><h3>Frequency Therapy</h3><p>Modern frequency therapy using advanced equipment for chronic pain & wellness.</p><span class="tag tag-new">Modern</span></div>
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l2 7h7l-5.5 4 2 7L12 16l-5.5 4 2-7L3 9h7z"/></svg></div><h3>Uric Acid & Anemia</h3><p>Testing and treatment for uric acid, anemia (khoon ki kami) and related conditions.</p></div>
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h3l3-9 4 18 3-9h5"/></svg></div><h3>Typhoid & Flu</h3><p>Rapid testing and complete treatment for typhoid, flu, and seasonal infections.</p></div>
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M6.5 6.5h11v11h-11z"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/></svg></div><h3>On-site Pharmacy</h3><p>Convenient on-site pharmacy facility for prescribed medicines.</p></div>
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg></div><h3>Asthma & Respiratory</h3><p>Diagnosis and management of asthma, bronchial and respiratory diseases.</p></div>
</div></section>

<section class="offers-section">
<div class="section-head reveal" style="color:var(--white)">
<span class="eyebrow" style="color:var(--gold-light)">Special Programs</span>
<h2 style="color:var(--white)">Free camps & <em style="color:var(--gold-light)">special offers</em></h2>
<p style="color:#cbd5e1">Affordable, accessible healthcare with weekly camps and significant discounts on diagnostics.</p>
</div>
<div class="offers-grid">

<div class="offer-card reveal">
<span class="price-tag">Rs. 500</span>
<div class="offer-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M9 12h6"/></svg></div>
<h4>Ultrasound at 50% Off</h4>
<p>Get advanced ultrasound imaging at Rs. 500 instead of Rs. 1000 &mdash; original prices slashed in half.</p>
<div class="offer-meta">Available daily 12 PM &mdash; 6 PM</div>
</div>

<div class="offer-card reveal">
<span class="price-tag">FREE</span>
<div class="offer-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78L12 21.23l8.84-8.84a5.5 5.5 0 000-7.78z"/></svg></div>
<h4>Saturday Free Camp</h4>
<p>Every Saturday: free medical checkup and free medicine for all patients visiting our center.</p>
<div class="offer-meta">Every Saturday &middot; All Day</div>
</div>

<div class="offer-card reveal">
<span class="price-tag">FREE</span>
<div class="offer-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h3l3-9 4 18 3-9h5"/></svg></div>
<h4>Sunday BP & Sugar Camp</h4>
<p>Every Sunday with Dr. Hafiz Muhammad Mahid &mdash; free medicines and tests for blood pressure & sugar patients.</p>
<div class="offer-meta">Every Sunday &middot; 3 PM &mdash; 6 PM</div>
</div>

<div class="offer-card reveal">
<span class="price-tag">FREE</span>
<div class="offer-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21v-2a4 4 0 014-4h8a4 4 0 014 4v2"/></svg></div>
<h4>Free Gynae Camp</h4>
<p>Free gynaecology checkup and free medicine &mdash; dedicated camp for women's health.</p>
<div class="offer-meta">Special women-only camp</div>
</div>

<div class="offer-card reveal">
<span class="price-tag">50% Off</span>
<div class="offer-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10 2v7.5L4 16l4 4 4-4 4 4 4-4-6-6.5V2"/></svg></div>
<h4>Lab Tests Discount</h4>
<p>50% discount on the full range of laboratory tests, blood work, and pathology investigations.</p>
<div class="offer-meta">All lab tests included</div>
</div>

<div class="offer-card reveal">
<span class="price-tag">50% Off</span>
<div class="offer-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M9 12h6M12 9v6"/></svg></div>
<h4>HbA1c (3-Month Sugar)</h4>
<p>Comprehensive 3-month sugar test (HbA1c) plus free uric acid screening and general checkup.</p>
<div class="offer-meta">Special diabetes program</div>
</div>

</div></section>

<section class="why-section">
<div class="section-head reveal">
<span class="eyebrow">Why Choose Us</span>
<h2>A standard of <em>care you can trust</em></h2>
</div>
<div class="why-grid">
<div class="why-box reveal"><div class="why-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21v-2a4 4 0 014-4h8a4 4 0 014 4v2"/></svg></div><h3>Expert Consultants</h3><p>Senior, qualified specialists with years of trusted clinical experience.</p></div>
<div class="why-box reveal"><div class="why-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg></div><h3>Affordable Pricing</h3><p>50% discounts on tests, weekly free camps, transparent and honest pricing.</p></div>
<div class="why-box reveal"><div class="why-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78L12 21.23l8.84-8.84a5.5 5.5 0 000-7.78z"/></svg></div><h3>Community Focused</h3><p>Free Saturday & Sunday camps, free medicines for chronic patients in need.</p></div>
<div class="why-box reveal"><div class="why-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9z"/></svg></div><h3>Modern Equipment</h3><p>Digital ECG, ultrasound, endoscopy, frequency therapy &mdash; the latest diagnostics.</p></div>
</div></section>

<section class="camp-banner">
<div class="camp-banner-inner">
<div class="tag">Weekly Special</div>
<h2>Every Saturday &amp; Sunday &mdash; <em style="font-style:italic;color:var(--gold-light)">Free for Everyone</em></h2>
<p>Free medical checkup, free medicine, and free tests for sugar and blood pressure patients. Walk-ins welcome.</p>
<div class="camp-pills">
<div class="camp-pill">FREE Checkup</div>
<div class="camp-pill">FREE Medicine</div>
<div class="camp-pill">FREE Sugar Tests</div>
<div class="camp-pill">FREE BP Tests</div>
</div>
</div></section>
</div>

<div class="page" id="about-page">
<div class="top-bar"><div class="top-bar-content"><div class="top-bar-info"><span><span class="dot"></span>Open Today: 12:00 PM &mdash; 6:00 PM</span><span>Endoscopy: 8:00 PM &mdash; 9:00 PM</span></div><div class="top-bar-info"><span>Call: 0320 4639794 / 0370 0469037</span></div></div></div>
<header class="header"><nav class="navbar"><a class="logo" onclick="showPage('home')"><div class="logo-mark"></div><div class="logo-text">Sharif Medical Center<span>Consultant Care</span></div></a>
<ul class="nav-menu" id="nm2"><li><a onclick="showPage('home')">Home</a></li><li><a onclick="showPage('about')" class="active">About</a></li><li><a onclick="showPage('services')">Services</a></li><li><a onclick="showPage('doctors')">Doctors</a></li><li><a onclick="showPage('contact')">Contact</a></li><li><a onclick="showPage('admin-login')" class="admin-link">Admin</a></li></ul>
<button class="menu-toggle" onclick="document.getElementById('nm2').classList.toggle('active')">&#9776;</button></nav></header>

<section class="page-banner"><div class="page-banner-content">
<div class="breadcrumb"><a onclick="showPage('home')">Home</a><span>/</span><span>About</span></div>
<h1>About Our Center</h1>
<p>A trusted healthcare destination serving the Sharqpur Road community of Lahore</p>
</div></section>

<section class="section"><div class="about-content">
<div class="about-text reveal">
<span class="eyebrow">Our Story</span>
<h2>Welcome to <em>Sharif Medical Center</em></h2>
<p>Sharif Medical Center is a trusted consultant care facility located near Al-Rehman Gardens Phase 2, opposite Clinix Pharmacy on Sharqpur Road, Lahore. We provide quality medical care to the local community with a strong focus on accessibility and affordability.</p>
<p>Our center brings together experienced consultants, modern diagnostic equipment, and a genuine commitment to community health. From routine consultations to specialist gastroenterology and endoscopy services, we cover the conditions that matter most to our patients.</p>
<ul>
<li>Three experienced consultants and specialists</li>
<li>50% discount on all laboratory tests &amp; ultrasound</li>
<li>Free medical checkup every Saturday for all patients</li>
<li>Free Sunday camp for blood pressure &amp; sugar patients</li>
<li>Affordable, transparent pricing &mdash; no hidden costs</li>
<li>Modern diagnostic equipment and on-site pharmacy</li>
</ul>
</div>
<div class="about-visual reveal">
<div class="about-card">
<div class="about-card-mark"></div>
<h3>Quality Care</h3>
<div class="tag">Every Patient. Every Time.</div>
</div>
</div>
</div>

<div class="stats-grid">
<div class="stat-box reveal"><h3>1000<span class="plus">+</span></h3><p>Happy Patients Served</p></div>
<div class="stat-box reveal"><h3>3</h3><p>Expert Consultants</p></div>
<div class="stat-box reveal"><h3>50<span class="plus">%</span></h3><p>Discount on All Tests</p></div>
<div class="stat-box reveal"><h3>6</h3><p>Days Open Per Week</p></div>
</div></section>
</div>

<div class="page" id="services-page">
<div class="top-bar"><div class="top-bar-content"><div class="top-bar-info"><span><span class="dot"></span>Open Today: 12:00 PM &mdash; 6:00 PM</span><span>Endoscopy: 8:00 PM &mdash; 9:00 PM</span></div><div class="top-bar-info"><span>Call: 0320 4639794 / 0370 0469037</span></div></div></div>
<header class="header"><nav class="navbar"><a class="logo" onclick="showPage('home')"><div class="logo-mark"></div><div class="logo-text">Sharif Medical Center<span>Consultant Care</span></div></a>
<ul class="nav-menu" id="nm3"><li><a onclick="showPage('home')">Home</a></li><li><a onclick="showPage('about')">About</a></li><li><a onclick="showPage('services')" class="active">Services</a></li><li><a onclick="showPage('doctors')">Doctors</a></li><li><a onclick="showPage('contact')">Contact</a></li><li><a onclick="showPage('admin-login')" class="admin-link">Admin</a></li></ul>
<button class="menu-toggle" onclick="document.getElementById('nm3').classList.toggle('active')">&#9776;</button></nav></header>

<section class="page-banner"><div class="page-banner-content">
<div class="breadcrumb"><a onclick="showPage('home')">Home</a><span>/</span><span>Services</span></div>
<h1>Our Medical Services</h1>
<p>Quality medical care for every condition, supported by experienced consultants</p>
</div></section>

<section class="section">
<div class="section-head reveal">
<span class="eyebrow">Complete Care</span>
<h2>What we <em>offer</em></h2>
<p>From routine general medicine to advanced endoscopy and laboratory diagnostics &mdash; under one trusted roof.</p>
</div>
<div class="services-grid">
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12h3l3-9 4 18 3-9h7"/></svg></div><h3>Blood Pressure</h3><p>Accurate BP screening, monitoring and long-term hypertension management.</p></div>
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M9 12h6M12 9v6"/></svg></div><h3>Sugar (Diabetes)</h3><p>Diabetes screening, HbA1c testing, and personalised treatment.</p><span class="tag tag-discount">HbA1c 50% Off</span></div>
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="9"/></svg></div><h3>Uric Acid</h3><p>Uric acid testing and complete management plans.</p></div>
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2C9 6 6 9 6 14a6 6 0 0012 0c0-5-3-8-6-12z"/></svg></div><h3>Anemia (Khoon Ki Kami)</h3><p>Comprehensive anemia diagnosis and treatment.</p></div>
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h3l3-9 4 18 3-9h5"/></svg></div><h3>Typhoid &amp; Flu</h3><p>Rapid testing and complete treatment for typhoid and seasonal flu.</p></div>
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10 2v7.5L4 16l4 4 4-4 4 4 4-4-6-6.5V2"/></svg></div><h3>Endoscopy</h3><p>Stomach and large intestine examination with modern endoscopic equipment.</p></div>
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L8 7v6c0 4 4 7 4 7s4-3 4-7V7l-4-5z"/></svg></div><h3>Gastroenterology</h3><p>Liver, stomach, pancreas, intestines, hepatitis and digestive disorders.</p></div>
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/></svg></div><h3>Ultrasound</h3><p>Advanced ultrasound imaging by qualified radiologists.</p><span class="tag tag-discount">Rs.500 (50% Off)</span></div>
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg></div><h3>Digital ECG</h3><p>Digital electrocardiogram for accurate heart rhythm evaluation.</p></div>
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10 2v6l-4 8a4 4 0 008 0l-4-8V2"/></svg></div><h3>Laboratory Tests</h3><p>Pathology, biochemistry, microbiology &mdash; complete diagnostic suite by Zeenat Laboratory.</p><span class="tag tag-discount">50% Off</span></div>
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 1v6M12 17v6M4.22 4.22l4.24 4.24M15.54 15.54l4.24 4.24M1 12h6M17 12h6"/></svg></div><h3>Frequency Therapy</h3><p>Modern frequency therapy using advanced equipment.</p><span class="tag tag-new">Modern</span></div>
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M6.5 6.5h11v11h-11z"/></svg></div><h3>On-site Pharmacy</h3><p>Convenient pharmacy facility for all prescribed medicines.</p></div>
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12c0 4 4 7 7 9 3-2 7-5 7-9V6l-7-3-7 3z"/></svg></div><h3>Joint &amp; Chest Pain</h3><p>Assessment and treatment for joint pain and chest discomfort.</p></div>
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg></div><h3>Asthma &amp; Respiratory</h3><p>Diagnosis and management of asthma and bronchial diseases.</p></div>
<div class="service-card reveal"><div class="service-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21v-2a4 4 0 014-4h8a4 4 0 014 4v2"/></svg></div><h3>Gynae Camp (Free)</h3><p>Free women's health checkup and free medicine &mdash; dedicated camp.</p><span class="tag tag-free">FREE Camp</span></div>
</div></section>

<section class="camp-banner">
<div class="camp-banner-inner">
<div class="tag">Weekly Special</div>
<h2>Every Saturday &amp; Sunday &mdash; <em style="font-style:italic;color:var(--gold-light)">Free for Everyone</em></h2>
<p>Free medical checkup, free medicine, free sugar &amp; BP tests. Walk-ins welcome &mdash; no appointment needed.</p>
<div class="camp-pills"><div class="camp-pill">FREE Checkup</div><div class="camp-pill">FREE Medicine</div><div class="camp-pill">FREE Tests</div></div>
</div></section>
</div>

<div class="page" id="doctors-page">
<div class="top-bar"><div class="top-bar-content"><div class="top-bar-info"><span><span class="dot"></span>Open Today: 12:00 PM &mdash; 6:00 PM</span><span>Endoscopy: 8:00 PM &mdash; 9:00 PM</span></div><div class="top-bar-info"><span>Call: 0320 4639794 / 0370 0469037</span></div></div></div>
<header class="header"><nav class="navbar"><a class="logo" onclick="showPage('home')"><div class="logo-mark"></div><div class="logo-text">Sharif Medical Center<span>Consultant Care</span></div></a>
<ul class="nav-menu" id="nm4"><li><a onclick="showPage('home')">Home</a></li><li><a onclick="showPage('about')">About</a></li><li><a onclick="showPage('services')">Services</a></li><li><a onclick="showPage('doctors')" class="active">Doctors</a></li><li><a onclick="showPage('contact')">Contact</a></li><li><a onclick="showPage('admin-login')" class="admin-link">Admin</a></li></ul>
<button class="menu-toggle" onclick="document.getElementById('nm4').classList.toggle('active')">&#9776;</button></nav></header>

<section class="page-banner"><div class="page-banner-content">
<div class="breadcrumb"><a onclick="showPage('home')">Home</a><span>/</span><span>Doctors</span></div>
<h1>Meet Our Specialists</h1>
<p>Qualified consultants with years of trusted clinical experience</p>
</div></section>

<section class="section"><div class="doctors-grid">

<div class="doctor-card reveal">
<div class="doctor-banner"><div class="doctor-avatar av-teal">DS</div></div>
<div class="doctor-info">
<h3>Dr. Shaheena Shafaq</h3>
<div class="specialty">General Physician</div>
<div class="specialties-list">
<span class="spec-chip">BP</span><span class="spec-chip">Sugar</span><span class="spec-chip">Uric Acid</span><span class="spec-chip">Anemia</span><span class="spec-chip">Typhoid</span>
</div>
<div class="qualifications">
<strong>Qualifications</strong>
<span class="qual-line">Doctor of Alternative Medicine</span>
<span class="qual-line">BEMS, MHP</span>
<span class="qual-line">General Physician &mdash; Years of trusted experience</span>
</div>
<div class="timing"><strong>Timing:</strong> Monday &mdash; Saturday<br>12:00 PM &mdash; 6:00 PM</div>
</div>
</div>

<div class="doctor-card reveal">
<div class="doctor-banner"><div class="doctor-avatar av-navy">DI</div></div>
<div class="doctor-info">
<h3>Dr. Ishfaq Ahmed Cheema</h3>
<div class="specialty">Gastroenterologist &amp; Hepatologist</div>
<div class="specialties-list">
<span class="spec-chip">Endoscopy</span><span class="spec-chip">Liver</span><span class="spec-chip">Stomach</span><span class="spec-chip">Hepatitis</span><span class="spec-chip">Intestines</span>
</div>
<div class="qualifications">
<strong>Qualifications</strong>
<span class="qual-line">Assistant Professor</span>
<span class="qual-line">MBBS (King Edward Medical University)</span>
<span class="qual-line">FCPS (Medicine)</span>
<span class="qual-line">Diploma in Gastroenterology (Ireland)</span>
</div>
<div class="timing"><strong>Timing:</strong> Daily Night<br>8:00 PM &mdash; 9:00 PM</div>
</div>
</div>

<div class="doctor-card reveal">
<div class="doctor-banner"><div class="doctor-avatar av-gold">DM</div></div>
<div class="doctor-info">
<h3>Dr. Hafiz Muhammad Mahid</h3>
<div class="specialty">Blood Pressure &amp; Sugar Specialist</div>
<div class="specialties-list">
<span class="spec-chip">BP</span><span class="spec-chip">Sugar</span><span class="spec-chip">Free Camp</span>
</div>
<div class="qualifications">
<strong>Qualifications</strong>
<span class="qual-line">MBBS, RMP</span>
<span class="qual-line">PMDC Registered: 757077-01M</span>
<span class="qual-line">Specialist in Hypertension &amp; Diabetes Management</span>
</div>
<div class="timing"><strong>Sunday Free Camp:</strong><br>3:00 PM &mdash; 6:00 PM &mdash; Free medicines &amp; tests</div>
</div>
</div>

<div class="doctor-card reveal">
<div class="doctor-banner"><div class="doctor-avatar av-emerald">DA</div></div>
<div class="doctor-info">
<h3>Dr. Amjad</h3>
<div class="specialty">Ultrasonography Specialist</div>
<div class="specialties-list">
<span class="spec-chip">Ultrasound</span><span class="spec-chip">Diagnostic Imaging</span>
</div>
<div class="qualifications">
<strong>Qualifications</strong>
<span class="qual-line">Specialist in Ultrasonography</span>
<span class="qual-line">Advanced diagnostic imaging</span>
</div>
<div class="timing"><strong>Ultrasound Service</strong><br>Available on appointment &mdash; Rs.500 (50% Off)</div>
</div>
</div>

</div>

<div style="text-align:center;margin-top:60px;" class="reveal">
<p style="color:var(--text-soft);margin-bottom:22px;font-size:1.05rem">Senior consultant care also available on request.</p>
<a class="btn btn-primary" onclick="showPage('contact')">Book Appointment
<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
</a>
</div>
</section>
</div>

<div class="page" id="contact-page">
<div class="top-bar"><div class="top-bar-content"><div class="top-bar-info"><span><span class="dot"></span>Open Today: 12:00 PM &mdash; 6:00 PM</span><span>Endoscopy: 8:00 PM &mdash; 9:00 PM</span></div><div class="top-bar-info"><span>Call: 0320 4639794 / 0370 0469037</span></div></div></div>
<header class="header"><nav class="navbar"><a class="logo" onclick="showPage('home')"><div class="logo-mark"></div><div class="logo-text">Sharif Medical Center<span>Consultant Care</span></div></a>
<ul class="nav-menu" id="nm5"><li><a onclick="showPage('home')">Home</a></li><li><a onclick="showPage('about')">About</a></li><li><a onclick="showPage('services')">Services</a></li><li><a onclick="showPage('doctors')">Doctors</a></li><li><a onclick="showPage('contact')" class="active">Contact</a></li><li><a onclick="showPage('admin-login')" class="admin-link">Admin</a></li></ul>
<button class="menu-toggle" onclick="document.getElementById('nm5').classList.toggle('active')">&#9776;</button></nav></header>

<section class="page-banner"><div class="page-banner-content">
<div class="breadcrumb"><a onclick="showPage('home')">Home</a><span>/</span><span>Contact</span></div>
<h1>Get In Touch</h1>
<p>Book your appointment or visit us at Sharqpur Road, Lahore</p>
</div></section>

<section class="section"><div class="contact-section">
<div class="contact-info reveal">
<h2>Visit our center</h2>
<p class="sub">We are open six days a week. Walk-ins welcome on Saturdays and Sundays for free camps.</p>

<div class="contact-item">
<div class="contact-item-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/></svg></div>
<div><h4>Address</h4><p>Near Al-Rehman Gardens Phase 2,<br>Opposite Clinix Pharmacy,<br>Sharqpur Road, Lahore</p></div>
</div>

<div class="contact-item">
<div class="contact-item-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z"/></svg></div>
<div><h4>Phone Numbers</h4><p><a href="tel:03700469037">0370 0469037</a><br><a href="tel:03204639794">0320 4639794</a></p></div>
</div>

<div class="contact-item">
<div class="contact-item-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg></div>
<div><h4>Center Timing</h4><p>Mon &mdash; Sat: 12:00 PM &mdash; 6:00 PM<br>Endoscopy: 8:00 PM &mdash; 9:00 PM<br>Sunday Camp: 3:00 PM &mdash; 6:00 PM</p></div>
</div>

<div class="contact-item">
<div class="contact-item-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78L12 21.23l8.84-8.84a5.5 5.5 0 000-7.78z"/></svg></div>
<div><h4>Weekly Free Camps</h4><p>Saturday: Free checkup &amp; medicine<br>Sunday: Free BP &amp; sugar camp</p></div>
</div>
</div>

<div class="appointment-form reveal">
<h2>Book Appointment</h2>
<p class="form-sub">Fill the form and we will confirm your slot shortly.</p>
<div class="success-msg" id="successMsg">Thank you! Your appointment request has been submitted.</div>
<div class="error-msg" id="formError"></div>
<form id="apForm" onsubmit="submitAppointment(event)">
<div class="form-group"><label>Full Name *</label><input type="text" id="ap-name" required placeholder="Enter your full name"></div>
<div class="form-group"><label>Phone *</label><input type="tel" id="ap-phone" required placeholder="03XX-XXXXXXX"></div>
<div class="form-group"><label>Select Doctor</label>
<select id="ap-doctor">
<option>Dr. Shaheena Shafaq (General Physician)</option>
<option>Dr. Ishfaq Ahmed Cheema (Gastroenterologist)</option>
<option>Dr. Hafiz Muhammad Mahid (BP &amp; Sugar Specialist)</option>
<option>Dr. Amjad (Ultrasonography)</option>
</select></div>
<div class="form-group"><label>Preferred Date</label><input type="date" id="ap-date"></div>
<div class="form-group"><label>Message <span style="color:var(--text-mute);font-weight:normal">(Optional)</span></label><textarea id="ap-message" placeholder="Briefly describe your problem... (skip if not needed)"></textarea></div>
<button type="submit" class="btn btn-primary" style="width:100%;justify-content:center" id="submitBtn">Submit Request
<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
</button>
</form>
</div>
</div></section>

<section class="map-section"><div class="section-head reveal"><span class="eyebrow">Location</span><h2>Find <em>us</em></h2></div>
<div class="map-container reveal"><iframe src="https://www.google.com/maps?q=Al+Rehman+Garden+Phase+2+Sharqpur+Road+Lahore&output=embed" loading="lazy"></iframe></div></section>
</div>

<div class="page" id="admin-login-page">
<div class="admin-bg"><div class="login-box">
<div class="login-logo"><div class="login-mark"></div></div>
<h1>Admin Portal</h1>
<p class="subtitle">Sharif Medical Center Management Panel</p>
<div class="error-msg" id="loginError"></div>
<form onsubmit="adminLogin(event)">
<div class="form-group"><label>Username</label><input type="text" id="login-user" required placeholder="Enter username"></div>
<div class="form-group"><label>Password</label><input type="password" id="login-pass" required placeholder="Enter password"></div>
<button type="submit" class="btn btn-primary" style="width:100%;justify-content:center" id="loginBtn">Login</button>
</form>
<div class="login-hint"><strong>Secure Admin Access</strong><br>Authorized personnel only</div>
<div style="text-align:center;margin-top:22px;"><a onclick="showPage('home')" style="color:var(--teal);font-size:.92rem;font-weight:500">&larr; Back to Website</a></div>
</div></div></div>

<div class="page" id="admin-dashboard-page">
<div class="admin-layout">
<aside class="sidebar">
<div class="sidebar-logo"><div class="logo-mark"></div><div class="logo-text">Sharif Medical<span>Admin Panel</span></div></div>
<ul class="sidebar-menu">
<li><a class="active" onclick="showAdminTab('dashboard',this)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg> Dashboard</a></li>
<li><a onclick="showAdminTab('appointments',this)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg> Appointments</a></li>
<li><a onclick="showAdminTab('add',this)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> Add Appointment</a></li>
<li><a onclick="showAdminTab('patients',this)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/></svg> Patients</a></li>
<li><a onclick="showAdminTab('settings',this)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33z"/></svg> Settings</a></li>
</ul>
<button class="logout-btn" onclick="adminLogout()">Logout</button>
</aside>

<main class="main-area">
<div class="admin-header"><h1 id="admin-tab-title">Dashboard</h1><p class="welcome">Welcome back, Admin</p></div>

<div id="tab-dashboard" class="admin-tab">
<div class="dashboard-stats">
<div class="dash-card"><div class="info"><h3 id="stat-total">0</h3><p>Total Appointments</p></div><div class="icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/></svg></div></div>
<div class="dash-card"><div class="info"><h3 id="stat-pending">0</h3><p>Pending</p></div><div class="icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg></div></div>
<div class="dash-card"><div class="info"><h3 id="stat-confirmed">0</h3><p>Confirmed</p></div><div class="icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg></div></div>
<div class="dash-card"><div class="info"><h3 id="stat-completed">0</h3><p>Completed</p></div><div class="icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="10"/><polyline points="8 12 11 15 16 9"/></svg></div></div>
</div>
<div class="data-card"><div class="data-card-header"><h2>Recent Appointments</h2></div><div id="recent-table"><div class="loading">Loading...</div></div></div>
</div>

<div id="tab-appointments" class="admin-tab" style="display:none;">
<div class="data-card"><div class="data-card-header"><h2>All Appointments</h2><input type="text" class="search-box" placeholder="Search by name or phone..." oninput="filterAppointments(this.value)"></div>
<div id="appointments-table"><div class="loading">Loading...</div></div></div>
</div>

<div id="tab-add" class="admin-tab" style="display:none;">
<div class="data-card"><div class="data-card-header"><h2>Add New Appointment</h2></div>
<div class="add-form">
<input type="text" id="new-name" placeholder="Patient Full Name *">
<input type="tel" id="new-phone" placeholder="Phone Number *">
<select id="new-doctor">
<option>Dr. Shaheena Shafaq (General Physician)</option>
<option>Dr. Ishfaq Ahmed Cheema (Gastroenterologist)</option>
<option>Dr. Hafiz Muhammad Mahid (BP &amp; Sugar Specialist)</option>
<option>Dr. Amjad (Ultrasonography)</option>
</select>
<input type="date" id="new-date">
<textarea class="full" id="new-message" placeholder="Notes / Problem description... (Optional)"></textarea>
</div><button class="btn btn-primary" onclick="addNewAppointment()">+ Add Appointment</button></div>
</div>

<div id="tab-patients" class="admin-tab" style="display:none;">
<div class="data-card"><div class="data-card-header"><h2>Patient List (Unique by Phone)</h2></div><div id="patients-table"><div class="loading">Loading...</div></div></div>
</div>

<div id="tab-settings" class="admin-tab" style="display:none;">
<div class="data-card"><div class="data-card-header"><h2>Center Information</h2></div>
<div class="info-grid">
<div><strong>Center Name:</strong> Sharif Medical Center (Consultant Care)</div>
<div><strong>Address:</strong> Near Al-Rehman Gardens Phase 2, Opposite Clinix Pharmacy, Sharqpur Road, Lahore</div>
<div><strong>Phone:</strong> 0320 4639794 / 0370 0469037</div>
<div><strong>Daily Timing:</strong> Mon &mdash; Sat, 12:00 PM &mdash; 6:00 PM</div>
<div><strong>Endoscopy Timing:</strong> 8:00 PM &mdash; 9:00 PM</div>
<div><strong>Sunday Camp:</strong> 3:00 PM &mdash; 6:00 PM with Dr. Hafiz Muhammad Mahid</div>
<div><strong>Discount:</strong> 50% on lab tests &amp; ultrasound</div>
<div><strong>Saturday Special:</strong> Free checkup &amp; free medicine</div>
<div><strong>Free Camps:</strong> Saturday (all), Sunday (BP &amp; Sugar), Gynae Camp</div>
</div></div>
<div class="data-card"><div class="data-card-header"><h2>Danger Zone</h2></div>
<button class="action-btn btn-cancel" onclick="clearAllAppointments()">Clear All Appointments</button></div>
</div>
</main></div></div>

<div id="footer-template" style="display:none;">
<footer class="footer"><div class="footer-content">
<div class="footer-col footer-brand">
<a class="logo" onclick="showPage('home')"><div class="logo-mark"></div><div class="logo-text">Sharif Medical Center<span>Consultant Care</span></div></a>
<p>Trusted healthcare on Sharqpur Road, Lahore. Senior consultants, modern equipment, affordable pricing.</p>
</div>
<div class="footer-col"><h3>Quick Links</h3>
<a onclick="showPage('home')">Home</a>
<a onclick="showPage('about')">About</a>
<a onclick="showPage('services')">Services</a>
<a onclick="showPage('doctors')">Doctors</a>
<a onclick="showPage('contact')">Contact</a>
</div>
<div class="footer-col"><h3>Specialties</h3>
<a>Endoscopy &amp; Gastroenterology</a>
<a>Blood Pressure &amp; Sugar</a>
<a>Ultrasound (50% off)</a>
<a>Digital ECG</a>
<a>Laboratory Tests</a>
</div>
<div class="footer-col"><h3>Contact</h3>
<div class="footer-contact"><span class="icn"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z"/></svg></span><span>0370 0469037<br>0320 4639794</span></div>
<div class="footer-contact"><span class="icn"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/></svg></span><span>Sharqpur Road, Lahore</span></div>
<div class="footer-contact"><span class="icn"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg></span><span>Mon &mdash; Sat: 12 PM &mdash; 6 PM</span></div>
</div>
</div><div class="footer-bottom">&copy; 2026 Sharif Medical Center. All Rights Reserved. &middot; Care You Can Trust</div></footer>
</div>

<a class="wa-float" href="https://wa.me/923700469037?text=Assalam-o-Alaikum%2C%20I%20would%20like%20to%20book%20an%20appointment%20at%20Sharif%20Medical%20Center." target="_blank" rel="noopener" aria-label="Chat on WhatsApp">
<span class="wa-float-icon">
<svg width="30" height="30" viewBox="0 0 24 24" fill="currentColor"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
</span>
<span class="wa-float-label">Chat with us</span>
</a>

<script>
const API_BASE = window.location.origin + '/api';
let allAppointments = [];

function getToken(){return localStorage.getItem('admin_token');}
function setToken(t){localStorage.setItem('admin_token',t);}
function clearToken(){localStorage.removeItem('admin_token');}

async function api(endpoint, options){
  options = options || {};
  const headers = Object.assign({'Content-Type':'application/json'}, options.headers || {});
  const token = getToken();
  if(token) headers['Authorization']='Bearer '+token;
  const res = await fetch(API_BASE+endpoint, Object.assign({}, options, {headers:headers}));
  const data = await res.json();
  if(!res.ok){
    if(data.error && (data.error.indexOf('Token expired')>=0 || data.error.indexOf('Authentication required')>=0)){clearToken();showPage('admin-login');}
    throw new Error(data.error || 'Request failed');
  }
  return data;
}

function esc(s){return String(s).replace(/[&<>"']/g, function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}

function showToast(msg, error){
  const t = document.createElement('div');
  t.className = 'toast' + (error ? ' error' : '');
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(function(){t.style.opacity='0';t.style.transform='translateX(40px)';setTimeout(function(){t.remove();}, 400);}, 2800);
}

function showPage(page){
  document.querySelectorAll('.page').forEach(function(p){p.classList.remove('active');});
  if(page === 'admin-dashboard' && !getToken()){page = 'admin-login';}
  const target = document.getElementById(page + '-page');
  if(!target){return;}
  target.classList.add('active');
  window.scrollTo({top:0, behavior:'smooth'});
  if(page === 'admin-dashboard'){loadDashboard();loadAppointments();}
  const pub = ['home','about','services','doctors','contact'];
  if(pub.indexOf(page) >= 0){
    if(!target.querySelector('.footer')){
      target.insertAdjacentHTML('beforeend', document.getElementById('footer-template').innerHTML);
    }
  }
  document.querySelectorAll('.nav-menu').forEach(function(m){m.classList.remove('active');});
  setTimeout(initReveals, 50);
}

function initReveals(){
  const els = document.querySelectorAll('.page.active .reveal:not(.in)');
  if(!('IntersectionObserver' in window)){els.forEach(function(e){e.classList.add('in');});return;}
  const io = new IntersectionObserver(function(entries){
    entries.forEach(function(en){
      if(en.isIntersecting){
        const el = en.target;
        const idx = Array.from(el.parentNode.children).indexOf(el);
        setTimeout(function(){el.classList.add('in');}, Math.min(idx * 60, 400));
        io.unobserve(el);
      }
    });
  }, {rootMargin:'-30px 0px', threshold:.05});
  els.forEach(function(el){io.observe(el);});

  // Animated counters
  const counters = document.querySelectorAll('.page.active [data-count]:not(.counted)');
  const co = new IntersectionObserver(function(entries){
    entries.forEach(function(en){
      if(en.isIntersecting){
        const el = en.target;
        el.classList.add('counted');
        const target = parseInt(el.getAttribute('data-count'), 10);
        const span = el.querySelector('.cnum');
        if(!span){co.unobserve(el);return;}
        const duration = 1400;
        const start = performance.now();
        function tick(now){
          const p = Math.min((now - start) / duration, 1);
          const eased = 1 - Math.pow(1 - p, 3);
          span.textContent = Math.floor(eased * target);
          if(p < 1) requestAnimationFrame(tick);
          else span.textContent = target;
        }
        requestAnimationFrame(tick);
        co.unobserve(el);
      }
    });
  }, {threshold:.3});
  counters.forEach(function(el){co.observe(el);});
}

window.addEventListener('scroll', function(){
  document.querySelectorAll('.header').forEach(function(h){
    if(window.scrollY > 10) h.classList.add('scrolled');
    else h.classList.remove('scrolled');
  });
});

async function submitAppointment(e){
  e.preventDefault();
  const btn = document.getElementById('submitBtn');
  btn.disabled = true; btn.textContent = 'Submitting...';
  document.getElementById('formError').style.display = 'none';
  document.getElementById('successMsg').style.display = 'none';
  try{
    await api('/appointments', {method:'POST', body:JSON.stringify({
      name: document.getElementById('ap-name').value,
      phone: document.getElementById('ap-phone').value,
      doctor: document.getElementById('ap-doctor').value,
      date: document.getElementById('ap-date').value,
      message: document.getElementById('ap-message').value
    })});
    document.getElementById('successMsg').style.display = 'block';
    document.getElementById('apForm').reset();
    showToast('Appointment booked successfully!');
    setTimeout(function(){document.getElementById('successMsg').style.display = 'none';}, 6000);
  }catch(err){
    const e1 = document.getElementById('formError');
    e1.textContent = err.message; e1.style.display = 'block';
  }finally{
    btn.disabled = false;
    btn.innerHTML = 'Submit Request <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>';
  }
}

async function adminLogin(e){
  e.preventDefault();
  const btn = document.getElementById('loginBtn');
  btn.disabled = true; btn.textContent = 'Logging in...';
  document.getElementById('loginError').style.display = 'none';
  try{
    const data = await api('/admin/login', {method:'POST', body:JSON.stringify({
      username: document.getElementById('login-user').value,
      password: document.getElementById('login-pass').value
    })});
    setToken(data.token);
    document.getElementById('login-user').value = '';
    document.getElementById('login-pass').value = '';
    showPage('admin-dashboard');
    showToast('Welcome admin!');
  }catch(err){
    const e1 = document.getElementById('loginError');
    e1.textContent = err.message; e1.style.display = 'block';
  }finally{
    btn.disabled = false; btn.textContent = 'Login';
  }
}

function adminLogout(){clearToken();showPage('home');showToast('Logged out');}

function showAdminTab(tab, el){
  document.querySelectorAll('.sidebar-menu a').forEach(function(a){a.classList.remove('active');});
  if(el) el.classList.add('active');
  document.querySelectorAll('.admin-tab').forEach(function(t){t.style.display = 'none';});
  document.getElementById('tab-' + tab).style.display = 'block';
  const titles = {dashboard:'Dashboard', appointments:'Appointments', add:'Add Appointment', patients:'Patients', settings:'Settings'};
  document.getElementById('admin-tab-title').textContent = titles[tab];
  if(tab === 'dashboard') loadDashboard();
  if(tab === 'appointments') loadAppointments();
  if(tab === 'patients') loadPatients();
}

async function loadDashboard(){
  try{
    const stats = await api('/admin/stats');
    document.getElementById('stat-total').textContent = stats.total;
    document.getElementById('stat-pending').textContent = stats.pending;
    document.getElementById('stat-confirmed').textContent = stats.confirmed;
    document.getElementById('stat-completed').textContent = stats.completed;
    const list = await api('/admin/appointments');
    document.getElementById('recent-table').innerHTML = buildTable(list.slice(0, 5));
  }catch(err){showToast(err.message, true);}
}

async function loadAppointments(){
  try{
    allAppointments = await api('/admin/appointments');
    document.getElementById('appointments-table').innerHTML = buildTable(allAppointments, true);
  }catch(err){showToast(err.message, true);}
}

function filterAppointments(filter){
  if(!filter){document.getElementById('appointments-table').innerHTML = buildTable(allAppointments, true);return;}
  const f = filter.toLowerCase();
  const filtered = allAppointments.filter(function(a){return a.name.toLowerCase().indexOf(f) >= 0 || a.phone.indexOf(filter) >= 0;});
  document.getElementById('appointments-table').innerHTML = buildTable(filtered, true);
}

async function loadPatients(){
  try{
    const list = await api('/admin/patients');
    if(list.length === 0){
      document.getElementById('patients-table').innerHTML = '<div class="empty-state"><div class="big-icon">&#128101;</div><h3>No patients yet</h3></div>';
      return;
    }
    let html = '<div style="overflow-x:auto;"><table class="appt-table"><thead><tr><th>Name</th><th>Phone</th><th>Visits</th><th>Last Visit</th></tr></thead><tbody>';
    list.forEach(function(p){html += '<tr><td><strong>' + esc(p.name) + '</strong></td><td>' + esc(p.phone) + '</td><td>' + p.visits + '</td><td>' + esc(p.lastVisit) + '</td></tr>';});
    document.getElementById('patients-table').innerHTML = html + '</tbody></table></div>';
  }catch(err){showToast(err.message, true);}
}

function buildTable(list, full){
  full = full || false;
  if(list.length === 0) return '<div class="empty-state"><div class="big-icon">&#128238;</div><h3>No appointments yet</h3></div>';
  let html = '<div style="overflow-x:auto;"><table class="appt-table"><thead><tr><th>#</th><th>Patient</th><th>Phone</th><th>Doctor</th><th>Date</th><th>Status</th>' + (full ? '<th>Actions</th>' : '') + '</tr></thead><tbody>';
  list.forEach(function(a){
    html += '<tr><td>' + a.id + '</td><td><strong>' + esc(a.name) + '</strong></td><td>' + esc(a.phone) + '</td><td>' + esc(a.doctor.split('(')[0]) + '</td><td>' + esc(a.date) + '</td><td><span class="status-badge status-' + a.status + '">' + a.status + '</span></td>';
    if(full){
      html += '<td>';
      if(a.status === 'pending') html += '<button class="action-btn btn-confirm" onclick="updateStatus(' + a.id + ',\'confirmed\')">Confirm</button>';
      if(a.status === 'confirmed') html += '<button class="action-btn btn-complete" onclick="updateStatus(' + a.id + ',\'completed\')">Complete</button>';
      if(a.status !== 'cancelled' && a.status !== 'completed') html += '<button class="action-btn btn-cancel" onclick="updateStatus(' + a.id + ',\'cancelled\')">Cancel</button>';
      html += '<button class="action-btn btn-delete" onclick="deleteAppointment(' + a.id + ')">Delete</button>';
      html += '</td>';
    }
    html += '</tr>';
  });
  return html + '</tbody></table></div>';
}

async function updateStatus(id, status){
  try{
    await api('/admin/appointments/' + id, {method:'PUT', body:JSON.stringify({status:status})});
    showToast('Updated to ' + status);
    loadDashboard(); loadAppointments();
  }catch(err){showToast(err.message, true);}
}

async function deleteAppointment(id){
  if(!confirm('Delete this appointment?')) return;
  try{
    await api('/admin/appointments/' + id, {method:'DELETE'});
    showToast('Deleted');
    loadDashboard(); loadAppointments(); loadPatients();
  }catch(err){showToast(err.message, true);}
}

async function clearAllAppointments(){
  if(!confirm('Delete ALL appointments? This cannot be undone.')) return;
  try{
    await api('/admin/appointments', {method:'DELETE'});
    showToast('All cleared');
    loadDashboard(); loadAppointments(); loadPatients();
  }catch(err){showToast(err.message, true);}
}

async function addNewAppointment(){
  const name = document.getElementById('new-name').value.trim();
  const phone = document.getElementById('new-phone').value.trim();
  if(!name || !phone){showToast('Name and phone required', true); return;}
  try{
    await api('/admin/appointments', {method:'POST', body:JSON.stringify({
      name:name, phone:phone,
      doctor: document.getElementById('new-doctor').value,
      date: document.getElementById('new-date').value,
      message: document.getElementById('new-message').value
    })});
    document.getElementById('new-name').value = '';
    document.getElementById('new-phone').value = '';
    document.getElementById('new-date').value = '';
    document.getElementById('new-message').value = '';
    showToast('Appointment added');
    loadDashboard();
  }catch(err){showToast(err.message, true);}
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
