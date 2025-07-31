#!/usr/bin/env python3
from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for, flash
import os
from flask import Flask, request, jsonify, send_from_directory
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import subprocess
import json
import requests
import re
import time
import datetime
import logging
import psutil
import shutil
import glob
from urllib.parse import urlparse
import threading
import queue
import uuid
import sys
import hashlib
import firebase_admin
from firebase_admin import credentials, firestore
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import secrets
import string
import random
from google.cloud.firestore_v1 import SERVER_TIMESTAMP
import pytz
import signal
import atexit
app = Flask(__name__)

rudy_process = None
current_attack = None
attack_running = False

# Logging configuration with rotation
from logging.handlers import RotatingFileHandler

log_handler = RotatingFileHandler("app.log", maxBytes=1000000, backupCount=5)
log_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logging.getLogger().addHandler(log_handler)
logging.getLogger().setLevel(logging.INFO)

# Create required directories
for folder in ("outputs", "reports"):
    os.makedirs(folder, exist_ok=True)

# Replace with a secure key
app.secret_key = "f83a9b83e9f0a94e3cf0aa817bfb7b99d55f3c8f298eebc4b315a214d1a71f63"

# Email configuration (update with your email settings)
EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'email': 'khawar.amin75@gmail.com',  # Update this
    'password': 'qebq gxhz wkbj xdyb'   # Update this with app password
}

# Initialize Firebase
try:
    cred = credentials.Certificate("pt-25-4f33b-firebase-adminsdk-fbsvc-6d33cfd52e.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase initialized successfully")
except Exception as e:
    print(f"Firebase initialization failed: {e}")
    db = None

def hash_password(password):
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def validate_password(password):
    """Validate password strength according to security policy"""
    errors = []
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long")
    if not re.search(r'[A-Z]', password):
        errors.append("Password must contain at least one uppercase letter")
    if not re.search(r'[a-z]', password):
        errors.append("Password must contain at least one lowercase letter")
    if not re.search(r'\d', password):
        errors.append("Password must contain at least one number")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        errors.append("Password must contain at least one special character")
    return len(errors) == 0, errors

def generate_otp():
    """Generate a secure 8-digit OTP"""
    return ''.join([str(random.randint(0, 9)) for _ in range(8)])

def generate_reset_token():
    """Generate a secure random token for password reset"""
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))

def send_otp_email(email, otp):
    """Send OTP verification email"""
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_CONFIG['email']
        msg['To'] = email
        msg['Subject'] = "PT-25 Account Verification - OTP"
        
        body = f"""
Hello,

Thank you for registering with PT-25!

Your One-Time Password (OTP) for account verification is:

{otp}

This OTP is valid for 5 minutes. Please enter this code on the verification page to complete your registration.

If you didn't request this registration, please ignore this email.

Best regards,
PT-25 Security Team
K-Corp
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        server.starttls()
        server.login(EMAIL_CONFIG['email'], EMAIL_CONFIG['password'])
        server.send_message(msg)
        server.quit()
        
        logging.info(f"OTP email sent successfully to {email}")
        return True
    except Exception as e:
        logging.error(f"Failed to send OTP email to {email}: {e}")
        return False

def send_reset_email(email, token):
    """Send password reset email"""
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_CONFIG['email']
        msg['To'] = email
        msg['Subject'] = "PT-25 Password Reset Request"
        reset_link = f"http://127.0.0.1:5000/reset_password/{token}"
        body = f"""
Hello,

You requested a password reset for your PT-25 account.

Click the link below to reset your password:
{reset_link}

This link will expire in 1 hour for security reasons.

If you didn't request this reset, please ignore this email. Your account remains secure.

Best regards,
PT-25 Security Team
K-Corp
        """
        msg.attach(MIMEText(body, 'plain'))
        server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        server.starttls()
        server.login(EMAIL_CONFIG['email'], EMAIL_CONFIG['password'])
        server.send_message(msg)
        server.quit()
        return True
    except smtplib.SMTPAuthenticationError as e:
        logging.error(f"SMTP Authentication failed: {e}")
        return False
    except smtplib.SMTPException as e:
        logging.error(f"SMTP error occurred: {e}")
        return False
    except Exception as e:
        logging.error(f"Failed to send reset email: {e}")
        return False

def store_pending_user(email, username, password, otp):
    """Store pending user data with OTP for verification"""
    try:
        if not db:
            return False
        
        # Clean up any existing pending registrations for this email
        try:
            existing_pending = db.collection('pending_registrations').where('email', '==', email).stream()
            for doc in existing_pending:
                doc.reference.delete()
        except Exception as cleanup_error:
            logging.warning(f"Error cleaning up existing pending registrations: {cleanup_error}")
        
        # Create timezone-aware datetime
        utc_now = datetime.datetime.now(pytz.UTC)
        expires_at = utc_now + datetime.timedelta(minutes=5)
        
        pending_data = {
            'email': email,
            'username': username,
            'password': hash_password(password),
            'otp': otp,
            'created_at': SERVER_TIMESTAMP,
            'expires_at': expires_at
        }
        
        db.collection('pending_registrations').add(pending_data)
        logging.info(f"Pending user stored for {email}")
        return True
    except Exception as e:
        logging.error(f"Error storing pending user: {e}")
        return False

def verify_otp_and_create_user(email, entered_otp):
    """Verify OTP and create user if valid"""
    try:
        if not db:
            return False, "Database not initialized"
        
        # Get pending registration
        pending_ref = db.collection('pending_registrations')
        pending_query = pending_ref.where('email', '==', email).limit(1).stream()
        
        pending_doc = None
        pending_data = None
        
        # Get current UTC time for comparison
        utc_now = datetime.datetime.now(pytz.UTC)
        
        for doc in pending_query:
            doc_data = doc.to_dict()
            expires_at = doc_data.get('expires_at')
            
            # Handle both timezone-aware and naive datetime objects
            if expires_at:
                if expires_at.tzinfo is None:
                    expires_at = pytz.UTC.localize(expires_at)
                
                # Check if OTP is not expired
                if expires_at > utc_now:
                    pending_doc = doc
                    pending_data = doc_data
                    break
        
        if not pending_data:
            return False, "OTP expired or not found. Please request a new OTP."
        
        # Verify OTP
        if pending_data.get('otp') != entered_otp:
            return False, "Invalid OTP. Please check and try again."
        
        # Check if user already exists
        users_ref = db.collection('users')
        existing_user = users_ref.where('email', '==', email).limit(1).stream()
        if any(existing_user):
            # Clean up pending registration
            if pending_doc:
                pending_doc.reference.delete()
            return False, "Email already registered"
        
        # Create user account
        user_data = {
            'email': pending_data['email'],
            'username': pending_data['username'],
            'password': pending_data['password'],
            'created_at': SERVER_TIMESTAMP,
            'last_login': None,
            'is_active': True,
            'verified': True
        }
        
        users_ref.add(user_data)
        
        # Clean up pending registration
        if pending_doc:
            pending_doc.reference.delete()
        
        logging.info(f"User account created successfully for {email}")
        return True, "Account created successfully"
        
    except Exception as e:
        logging.error(f"Error verifying OTP and creating user: {e}")
        return False, "Failed to verify OTP and create account"

def resend_otp_for_user(email):
    """Resend OTP for pending user registration"""
    try:
        if not db:
            return False, "Database not initialized"
        
        # Get pending registration
        pending_ref = db.collection('pending_registrations')
        pending_query = pending_ref.where('email', '==', email).limit(1).stream()
        
        pending_doc = None
        pending_data = None
        
        for doc in pending_query:
            pending_doc = doc
            pending_data = doc.to_dict()
            break
        
        if not pending_data:
            return False, "No pending registration found"
        
        # Generate new OTP
        new_otp = generate_otp()
        
        # Update pending registration with new OTP and expiry
        utc_now = datetime.datetime.now(pytz.UTC)
        expires_at = utc_now + datetime.timedelta(minutes=5)
        
        pending_doc.reference.update({
            'otp': new_otp,
            'expires_at': expires_at,
            'updated_at': SERVER_TIMESTAMP
        })
        
        # Send new OTP email
        if send_otp_email(email, new_otp):
            logging.info(f"OTP resent successfully to {email}")
            return True, "OTP sent successfully"
        else:
            return False, "Failed to send OTP email"
        
    except Exception as e:
        logging.error(f"Error resending OTP: {e}")
        return False, "Failed to resend OTP"

def authenticate_user(email, password):
    """Authenticate user against Firebase"""
    try:
        if not db:
            return False, None
        email = email.strip().lower()
        users_ref = db.collection('users')
        user_query = users_ref.where('email', '==', email).limit(1).stream()
        for user_doc in user_query:
            user_data = user_doc.to_dict()
            if not user_data.get('is_active', True):
                logging.warning(f"Inactive user attempted login: {email}")
                return False, None
            if user_data.get('password') == hash_password(password):
                user_doc.reference.update({
                    'last_login': SERVER_TIMESTAMP
                })
                logging.info(f"User authenticated successfully: {email}")
                return True, user_data
        logging.warning(f"Authentication failed for: {email}")
        return False, None
    except Exception as e:
        logging.error(f"Error authenticating user: {e}")
        return False, None

def check_user_exists(email):
    """Check if user exists in Firebase"""
    try:
        if not db:
            return False
        email = email.strip().lower()
        users_ref = db.collection('users')
        user_query = users_ref.where('email', '==', email).limit(1).stream()
        return any(user_query)
    except Exception as e:
        logging.error(f"Error checking user existence for {email}: {e}")
        return False

@app.before_request
def check_session():
    """Check if user session is valid and redirect to login if needed"""
    excluded_routes = ['login', 'signup', 'verify_otp', 'resend_otp', 'forgot_password', 'reset_password', 'static']
    if request.endpoint not in excluded_routes:
        if 'user' not in session:
            return redirect(url_for('login'))

@app.route("/")
@app.route("/index")
def index():
    if 'user' in session:
        username = session['user']
        return render_template("index.html", username=username)
    else:
        return redirect(url_for('login'))

_prev_net = psutil.net_io_counters()
_prev_t = time.time()

@app.route("/system_stats")
def system_stats():
    global _prev_net, _prev_t
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    now, nio = time.time(), psutil.net_io_counters()
    dt = max(now - _prev_t, 1)
    recv = (nio.bytes_recv - _prev_net.bytes_recv) * 8 / (1e6 * dt)
    sent = (nio.bytes_sent - _prev_net.bytes_sent) * 8 / (1e6 * dt)
    recv, sent = max(recv, 0.0), max(sent, 0.0)
    _prev_net, _prev_t = nio, now
    return jsonify({
        "cpu": cpu,
        "ram": {
            "total": mem.total / 1_048_576,
            "used": mem.used / 1_048_576,
            "percent": mem.percent
        },
        "network": {"recv": recv, "sent": sent}
    })

def _normalize_url(url: str) -> str:
    """Normalize URL by adding https:// if no scheme is provided."""
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url

def _valid_domain(url: str) -> str:
    p = urlparse(url.strip())
    d = p.netloc or p.path.split("/")[0]
    d = re.sub(r":\d+$", "", d)
    if not re.match(r"^[\w.-]+\.[a-zA-Z]{2,}$", d):
        raise ValueError("Invalid domain")
    return d

def _run(cmd):
    process = subprocess.run(cmd, check=True, text=True, capture_output=True)
    logging.info(f"Command executed: {' '.join(cmd)}\nOutput: {process.stdout}")
    return process

@app.route("/start_comprehensive_test", methods=["POST"])
def start_comprehensive_test():
    data = request.get_json()
    website_url = data.get("website_url")
    if not website_url:
        return jsonify({"error": "No URL provided"}), 400
    try:
        website_url = _normalize_url(website_url)
        _valid_domain(website_url)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    test_id = str(uuid.uuid4())
    thread = threading.Thread(target=run_pdf_script, args=(test_id, website_url))
    thread.start()
    return jsonify({"test_id": test_id})

def run_pdf_script(test_id, website_url):
    try:
        result = subprocess.run(["python3", "pdf.py", website_url], capture_output=True, text=True)
        if result.returncode != 0:
            logging.error(f"pdf.py failed: {result.stderr}")
            return
        logging.info("Comprehensive test completed successfully")
    except Exception as e:
        logging.exception("Exception in comprehensive test")

@app.route("/check_file")
def check_file():
    path = request.args.get("path")
    if not path:
        return jsonify({"exists": False})
    exists = os.path.exists(path) and os.path.getsize(path) > 0
    return jsonify({"exists": exists})

@app.route("/download_pdf/<path:filename>")
def download_pdf(filename):
    return send_file(os.path.join("reports", filename), as_attachment=True)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        if not check_user_exists(email):
            flash("No account found with this email. Please sign up first.", "danger")
            return render_template("login.html")
        success, user_data = authenticate_user(email, password)
        if success and user_data:
            session.permanent = False
            session["user"] = user_data["username"]
            session["email"] = user_data["email"]
            flash("Login successful!", "success")
            return redirect(url_for("index"))
        else:
            flash("Invalid password.", "danger")
    return render_template("login.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        username = request.form["username"].strip()
        password = request.form["password"]
        confirm = request.form["confirm"]
        
        # Validate input
        if not email or not username or not password or not confirm:
            flash("All fields are required.", "danger")
            return render_template("signup.html")
        
        # Check email format
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            flash("Invalid email format.", "danger")
            return render_template("signup.html")
        
        # Check password confirmation
        if password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("signup.html")
        
        # Validate password strength
        is_valid, errors = validate_password(password)
        if not is_valid:
            flash("; ".join(errors), "danger")
            return render_template("signup.html")
        
        # Check if user already exists
        if check_user_exists(email):
            flash("Email already registered. Please use a different email or login.", "danger")
            return render_template("signup.html")
        
        # Generate OTP
        otp = generate_otp()
        
        # Store pending user data
        if store_pending_user(email, username, password, otp):
            # Send OTP email
            if send_otp_email(email, otp):
                session['pending_email'] = email
                flash("OTP sent to your email. Please check your inbox and enter the verification code.", "success")
                return redirect(url_for('verify_otp'))
            else:
                flash("Failed to send verification email. Please try again.", "danger")
        else:
            flash("Failed to process registration. Please try again.", "danger")
    
    return render_template("signup.html")

@app.route("/verify_otp", methods=["GET", "POST"])
def verify_otp():
    # Check if user has pending email in session
    if 'pending_email' not in session:
        flash("No pending registration found. Please sign up first.", "danger")
        return redirect(url_for('signup'))
    
    if request.method == "POST":
        entered_otp = request.form.get("otp", "").strip()
        
        if not entered_otp:
            flash("Please enter the OTP.", "danger")
            return render_template("otp_verify.html")
        
        if len(entered_otp) != 8:
            flash("Please enter the complete 8-digit OTP.", "danger")
            return render_template("otp_verify.html")
        
        # Verify OTP and create user
        email = session['pending_email']
        success, message = verify_otp_and_create_user(email, entered_otp)
        
        if success:
            # Clear pending email from session
            session.pop('pending_email', None)
            flash("Account created successfully! Please login with your credentials.", "success")
            return redirect(url_for('login'))
        else:
            flash(message, "danger")
    
    return render_template("otp_verify.html")

@app.route("/resend_otp", methods=["POST"])
def resend_otp():
    if 'pending_email' not in session:
        return jsonify({"success": False, "message": "No pending registration found"})
    
    email = session['pending_email']
    success, message = resend_otp_for_user(email)
    
    return jsonify({"success": success, "message": message})

@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not email:
            flash("Please enter your email address.", "danger")
            return render_template("forgot_password.html")
        if not check_user_exists(email):
            flash("No account found with this email address.", "danger")
            return render_template("forgot_password.html")
        token = generate_reset_token()
        try:
            if not db:
                flash("Database not available. Please try again later.", "danger")
                return render_template("forgot_password.html")
            try:
                existing_resets = db.collection('password_resets').where('email', '==', email).stream()
                for existing_reset in existing_resets:
                    existing_reset.reference.delete()
            except Exception as cleanup_error:
                logging.warning(f"Error cleaning up existing reset tokens: {cleanup_error}")
            
            # Create timezone-aware datetime
            utc_now = datetime.datetime.now(pytz.UTC)
            expires_at = utc_now + datetime.timedelta(hours=1)
            
            reset_data = {
                'email': email,
                'token': token,
                'created_at': SERVER_TIMESTAMP,
                'expires_at': expires_at
            }
            db.collection('password_resets').add(reset_data)
            if send_reset_email(email, token):
                flash("Password reset link sent to your email. Please check your inbox and spam folder.", "success")
                logging.info(f"Password reset email sent successfully to {email}")
            else:
                flash("Failed to send reset email. Please try again or contact support.", "danger")
                logging.error(f"Failed to send reset email to {email}")
        except Exception as e:
            logging.error(f"Error creating reset token for {email}: {e}")
            flash("An error occurred while processing your request. Please try again.", "danger")
    return render_template("forgot_password.html")

@app.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        if not db:
            flash("Database not available", "danger")
            return redirect(url_for("forgot_password"))
        resets_ref = db.collection('password_resets')
        reset_query = resets_ref.where('token', '==', token).limit(1).stream()
        valid_token = False
        reset_doc = None
        reset_data = None
        
        # Get current UTC time for comparison
        utc_now = datetime.datetime.now(pytz.UTC)
        
        for doc in reset_query:
            doc_data = doc.to_dict()
            expires_at = doc_data.get('expires_at')
            
            # Handle both timezone-aware and naive datetime objects
            if expires_at:
                # If expires_at is timezone-naive, make it timezone-aware
                if expires_at.tzinfo is None:
                    expires_at = pytz.UTC.localize(expires_at)
                
                # Compare with current UTC time
                if expires_at > utc_now:
                    valid_token = True
                    reset_doc = doc
                    reset_data = doc_data
                    break
        
        if not valid_token or not reset_data:
            flash("Invalid or expired reset link. Please request a new password reset.", "danger")
            return redirect(url_for("forgot_password"))
            
    except Exception as e:
        logging.error(f"Error validating reset token: {e}")
        flash("An error occurred while validating the reset link. Please try again.", "danger")
        return redirect(url_for("forgot_password"))
    
    if request.method == "POST":
        new_password = request.form.get("password", "").strip()
        confirm_password = request.form.get("confirm", "").strip()
        
        if not new_password or not confirm_password:
            flash("Please fill in all fields.", "danger")
            return render_template("reset_password.html", token=token)
        
        if new_password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("reset_password.html", token=token)
        
        is_valid, errors = validate_password(new_password)
        if not is_valid:
            flash("; ".join(errors), "danger")
            return render_template("reset_password.html", token=token)
        
        try:
            email = reset_data['email']
            users_ref = db.collection('users')
            user_query = users_ref.where('email', '==', email).limit(1).stream()
            user_updated = False
            
            for user_doc in user_query:
                user_doc.reference.update({
                    'password': hash_password(new_password),
                    'password_updated_at': SERVER_TIMESTAMP
                })
                user_updated = True
                break
            
            if not user_updated:
                flash("User not found. Please try again.", "danger")
                return render_template("reset_password.html", token=token)
            
            # Delete the used reset token
            if reset_doc:
                reset_doc.reference.delete()
            
            # Clean up any other reset tokens for this email
            try:
                other_resets = resets_ref.where('email', '==', email).stream()
                for other_reset in other_resets:
                    other_reset.reference.delete()
            except Exception as cleanup_error:
                logging.warning(f"Error cleaning up other reset tokens: {cleanup_error}")
            
            flash("Password reset successful! Please log in with your new password.", "success")
            return redirect(url_for("login"))
            
        except Exception as e:
            logging.error(f"Error resetting password: {e}")
            flash("An error occurred while resetting your password. Please try again.", "danger")
            return render_template("reset_password.html", token=token)
    
    return render_template("reset_password.html", token=token)

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

@app.route("/profile")
def profile():
    """Display user profile (optional feature)"""
    try:
        if not db:
            flash("Database not available", "danger")
            return redirect(url_for("index"))
        users_ref = db.collection('users')
        user_query = users_ref.where('email', '==', session.get('email')).limit(1).stream()
        user_data = None
        for user_doc in user_query:
            user_data = user_doc.to_dict()
            break
        return render_template("profile.html", user_data=user_data)
    except Exception as e:
        logging.error(f"Error loading profile: {e}")
        flash("Error loading profile", "danger")
        return redirect(url_for("index"))
# Updated route for hidden directories scan - Add this to your app.py

@app.route("/start_hidden_directories_scan", methods=["POST"])
def start_hidden_directories_scan():
    """Start hidden directories scan using dir.py script"""
    try:
        data = request.get_json()
        website_url = data.get("website_url")

        # Log the URL received from the frontend
        logging.info(f"Received URL from frontend: {website_url}")

        if not website_url:
            return jsonify({"success": False, "message": "No URL provided"}), 400

        # Normalize the URL if needed
        try:
            website_url = _normalize_url(website_url)
            _valid_domain(website_url)
        except ValueError as e:
            return jsonify({"success": False, "message": str(e)}), 400

        # Log the normalized URL
        logging.info(f"Normalized URL: {website_url}")

        # Run the dir.py script with the provided website URL
        result = subprocess.run(
            ["python3", "dir.py", website_url],
            capture_output=True, 
            text=True
        )

        if result.returncode != 0:
            logging.error(f"dir.py script failed with return code {result.returncode}")
            logging.error(f"STDERR: {result.stderr}")
            return jsonify({
                "success": False, 
                "message": f"Scan failed: {result.stderr or 'Unknown error'}"
            }), 500

        # Read the results from the generated 'dir.txt' file
        output_file = os.path.join("outputs", "dir.txt")
        
        if not os.path.exists(output_file):
            logging.error(f"Output file not found: {output_file}")
            return jsonify({
                "success": False, 
                "message": "Scan completed but no output file was generated"
            }), 500

        try:
            with open(output_file, "r", encoding="utf-8") as file:
                results = file.read()
        except UnicodeDecodeError:
            # Try with different encoding if UTF-8 fails
            with open(output_file, "r", encoding="latin-1") as file:
                results = file.read()

        if not results.strip():
            return jsonify({
                "success": False, 
                "message": "Scan completed but no results were found"
            })

        logging.info(f"Hidden directories scan completed successfully for {website_url}")
        return jsonify({
            "success": True, 
            "results": results
        })

    except subprocess.TimeoutExpired:
        logging.error("dir.py script timed out")
        return jsonify({
            "success": False, 
            "message": "Scan timed out. Please try again with a smaller scope."
        }), 500
    except FileNotFoundError:
        logging.error("dir.py script not found")
        return jsonify({
            "success": False, 
            "message": "Scanner script not found. Please contact administrator."
        }), 500
    except Exception as e:
        logging.error(f"Error in hidden directories scan: {str(e)}")
        return jsonify({
            "success": False, 
            "message": f"An error occurred during scan: {str(e)}"
        }), 500
@app.route("/delete_account", methods=["POST"])
def delete_account():
    """Delete user account permanently"""
    if 'user' not in session or 'email' not in session:
        return jsonify({"success": False, "message": "User not authenticated"}), 401
    
    try:
        if not db:
            return jsonify({"success": False, "message": "Database not available"}), 500
        
        data = request.get_json()
        if not data or not data.get('confirm_delete'):
            return jsonify({"success": False, "message": "Confirmation required"}), 400
        
        email = session['email']
        logging.info(f"Attempting to delete account for user: {email}")
        
        # Find and delete user account
        users_ref = db.collection('users')
        user_query = users_ref.where('email', '==', email).limit(1).stream()
        
        user_deleted = False
        for user_doc in user_query:
            user_doc.reference.delete()
            user_deleted = True
            logging.info(f"User account deleted: {email}")
            break
        
        if not user_deleted:
            return jsonify({"success": False, "message": "User account not found"}), 404
        
        # Clean up any related data
        try:
            # Delete pending registrations
            pending_ref = db.collection('pending_registrations')
            pending_query = pending_ref.where('email', '==', email).stream()
            for pending_doc in pending_query:
                pending_doc.reference.delete()
            
            # Delete password reset tokens
            resets_ref = db.collection('password_resets')
            reset_query = resets_ref.where('email', '==', email).stream()
            for reset_doc in reset_query:
                reset_doc.reference.delete()
            
            logging.info(f"Cleanup completed for user: {email}")
        except Exception as cleanup_error:
            logging.warning(f"Error during cleanup for {email}: {cleanup_error}")
        
        # Clear user session
        session.clear()
        
        return jsonify({
            "success": True, 
            "message": "Account deleted successfully"
        })
        
    except Exception as e:
        logging.error(f"Error deleting account for {session.get('email', 'unknown')}: {e}")
        return jsonify({
            "success": False, 
            "message": "An error occurred while deleting your account"
        }), 500
@app.route('/find_subdomains', methods=['POST'])
def find_subdomains():
    try:
        # Get URL from request
        data = request.get_json()
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'success': False, 'message': 'URL is required'})
        
        # Validate URL format
        if not url.startswith(('http://', 'https://')):
            return jsonify({'success': False, 'message': 'Invalid URL format'})
        
        # Extract domain from URL
        domain = url.replace('https://', '').replace('http://', '').split('/')[0]
        
        # Create outputs directory if it doesn't exist
        outputs_dir = 'outputs'
        if not os.path.exists(outputs_dir):
            os.makedirs(outputs_dir)
        
        # Define output file path
        output_file = os.path.join(outputs_dir, 'subdomain.txt')
        
        # Remove existing output file if it exists
        if os.path.exists(output_file):
            os.remove(output_file)
        
        # Run subdomain.py script with the domain
        try:
            # Run the subdomain scanner
            result = subprocess.run(['python', 'subdomain.py', domain], 
                                  capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                return jsonify({'success': False, 'message': 'Subdomain scan failed'})
        
        except subprocess.TimeoutExpired:
            return jsonify({'success': False, 'message': 'Scan timeout - please try again'})
        except Exception as e:
            return jsonify({'success': False, 'message': f'Error running scan: {str(e)}'})
        
        # Wait for output file to be created (max 30 seconds)
        max_wait = 30
        wait_time = 0
        while not os.path.exists(output_file) and wait_time < max_wait:
            time.sleep(1)
            wait_time += 1
        
        # Check if output file was created
        if not os.path.exists(output_file):
            return jsonify({'success': False, 'message': 'No output file generated'})
        
        # Read results from output file
        subdomains = []
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    # Split by lines and clean up
                    lines = content.split('\n')
                    for line in lines:
                        line = line.strip()
                        if line and not line.startswith('#') and not line.startswith('//'):
                            # Ensure proper URL format
                            if not line.startswith(('http://', 'https://')):
                                line = 'https://' + line
                            subdomains.append(line)
        
        except Exception as e:
            return jsonify({'success': False, 'message': f'Error reading results: {str(e)}'})
        
        # Remove duplicates while preserving order
        seen = set()
        unique_subdomains = []
        for subdomain in subdomains:
            if subdomain not in seen:
                seen.add(subdomain)
                unique_subdomains.append(subdomain)
        
        return jsonify({
            'success': True, 
            'subdomains': unique_subdomains,
            'count': len(unique_subdomains)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'})
@app.route('/check_url', methods=['GET'])
def check_url():
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "URL is required"}), 400
    try:
        response = requests.head(url, timeout=5)
        accessible = response.status_code < 400
    except requests.RequestException:
        accessible = False
    return jsonify({"accessible": accessible})

@app.route('/start_rudy', methods=['POST'])
def start_rudy():
    global current_attack
    if current_attack is not None:
        return jsonify({"error": "Attack already in progress"}), 400
    data = request.get_json()
    url = data.get('url')
    users = data.get('users')
    if not url or not users:
        return jsonify({"error": "URL and users are required"}), 400
    try:
        users = int(users)
    except ValueError:
        return jsonify({"error": "Users must be an integer"}), 400
    cmd = ['python3', 'rudy.py',str(users), url]
    current_attack = subprocess.Popen(cmd, preexec_fn=os.setsid)
    return jsonify({"message": "Attack started"})

@app.route('/stop_rudy', methods=['POST'])
def stop_rudy():
    global current_attack
    if current_attack is None:
        return jsonify({"error": "No attack in progress"}), 400
    try:
        os.killpg(os.getpgid(current_attack.pid), signal.SIGTERM)
        current_attack.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(current_attack.pid), signal.SIGKILL)
    current_attack = None
    return jsonify({"message": "Attack stopped"})
import os
import subprocess
import tempfile
from flask import request, jsonify, send_file, abort
from werkzeug.utils import secure_filename
import uuid

# Configuration
UPLOAD_FOLDER = 'uploads'
REPORTS_FOLDER = 'reports'
ALLOWED_EXTENSIONS = {'pdf'}

# Create directories if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(REPORTS_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/analyze_pdf', methods=['POST'])
def analyze_pdf():
    try:
        # Check if file is present in request
        if 'pdf_file' not in request.files:
            return jsonify({'success': False, 'message': 'No file uploaded'}), 400
        
        file = request.files['pdf_file']
        
        # Check if file is selected
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected'}), 400
        
        # Check if file is allowed
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'message': 'Only PDF files are allowed'}), 400
        
        # Generate unique filename to avoid conflicts
        unique_filename = str(uuid.uuid4()) + '_' + secure_filename(file.filename)
        file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
        
        # Save uploaded file
        file.save(file_path)
        
        # Check file size (max 10MB)
        if os.path.getsize(file_path) > 10 * 1024 * 1024:
            os.remove(file_path)  # Clean up
            return jsonify({'success': False, 'message': 'File size exceeds 10MB limit'}), 400
        
        # Extract text from PDF first (you might want to add this step)
        # For now, we'll assume Ai.py can handle PDF directly
        
        # Create a temporary text file path for Ai.py
        txt_filename = unique_filename.replace('.pdf', '.txt')
        txt_path = os.path.join(UPLOAD_FOLDER, txt_filename)
        
        # Extract text from PDF and save to txt file
        # You can use PyPDF2 or pdfplumber for this
        try:
            import PyPDF2
            
            with open(file_path, 'rb') as pdf_file:
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                text_content = ""
                
                for page in pdf_reader.pages:
                    text_content += page.extract_text() + "\n"
                
                # Save extracted text to txt file
                with open(txt_path, 'w', encoding='utf-8') as txt_file:
                    txt_file.write(text_content)
        
        except Exception as e:
            # If PyPDF2 fails, try alternative approach or return error
            os.remove(file_path)  # Clean up
            return jsonify({'success': False, 'message': f'Failed to extract text from PDF: {str(e)}'}), 500
        
        # Call Ai.py script with the text file
        try:
            # Make sure Ai.py is executable and in the correct path
            result = subprocess.run([
                'python3', 'Ai.py', txt_path
            ], capture_output=True, text=True, timeout=300)  # 5 minute timeout
            
            if result.returncode != 0:
                # Clean up files
                os.remove(file_path)
                os.remove(txt_path)
                return jsonify({
                    'success': False, 
                    'message': f'AI analysis failed: {result.stderr}'
                }), 500
            
            # Check if the AI analysis report was created
            ai_report_path = os.path.join(REPORTS_FOLDER, 'Ai_Analyzed_Report.pdf')
            if not os.path.exists(ai_report_path):
                # Clean up files
                os.remove(file_path)
                os.remove(txt_path)
                return jsonify({
                    'success': False, 
                    'message': 'AI analysis completed but report file was not generated'
                }), 500
            
            # Clean up temporary files
            os.remove(file_path)
            os.remove(txt_path)
            
            return jsonify({
                'success': True, 
                'message': 'AI analysis completed successfully',
                'report_path': ai_report_path
            })
            
        except subprocess.TimeoutExpired:
            # Clean up files
            os.remove(file_path)
            os.remove(txt_path)
            return jsonify({
                'success': False, 
                'message': 'AI analysis timed out. Please try with a smaller file.'
            }), 500
        except Exception as e:
            # Clean up files
            os.remove(file_path)
            os.remove(txt_path)
            return jsonify({
                'success': False, 
                'message': f'Error running AI analysis: {str(e)}'
            }), 500
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

@app.route('/api/download_analysis', methods=['GET'])
def download_analysis():
    try:
        ai_report_path = os.path.join(REPORTS_FOLDER, 'Ai_Analyzed_Report.pdf')
        
        # Check if file exists
        if not os.path.exists(ai_report_path):
            return jsonify({'error': 'Analysis report not found'}), 404
        
        # Send file for download
        return send_file(
            ai_report_path,
            as_attachment=True,
            download_name='AI_Analyzed_Report.pdf',
            mimetype='application/pdf'
        )
        
    except Exception as e:
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

@app.route('/api/analysis_status', methods=['GET'])
def analysis_status():
    try:
        ai_report_path = os.path.join(REPORTS_FOLDER, 'Ai_Analyzed_Report.pdf')
        
        if os.path.exists(ai_report_path):
            return jsonify({'status': 'complete'})
        else:
            return jsonify({'status': 'processing'})
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Optional: Clean up old files periodically
@app.route('/api/cleanup_temp_files', methods=['POST'])
def cleanup_temp_files():
    try:
        import time
        current_time = time.time()
        
        # Clean up files older than 1 hour
        for folder in [UPLOAD_FOLDER, REPORTS_FOLDER]:
            for filename in os.listdir(folder):
                file_path = os.path.join(folder, filename)
                if os.path.isfile(file_path):
                    file_age = current_time - os.path.getctime(file_path)
                    if file_age > 3600:  # 1 hour
                        os.remove(file_path)
        
        return jsonify({'success': True, 'message': 'Cleanup completed'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
attack_process = None

import subprocess
import threading
import queue
import os
import signal
from flask import request, jsonify

# Global variables to track the DOS attack process
dos_process = None
dos_output_queue = queue.Queue()
dos_thread = None

def read_dos_output(process, output_queue):
    """Read output from the DOS attack process."""
    try:
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                output_queue.put(output.strip())
    except Exception as e:
        output_queue.put(f"Error reading output: {str(e)}")

@app.route('/launch_dos_attack', methods=['POST'])
def launch_dos_attack():
    """Launch DOS attack with specified URL and method."""
    global dos_process, dos_thread, dos_output_queue
    
    try:
        data = request.get_json()
        url = data.get('url')
        method = data.get('method')
        
        if not url or not method:
            return jsonify({'success': False, 'message': 'URL and method are required'})
        
        # Validate method
        if method not in ['syn', 'udp', 'icmp']:
            return jsonify({'success': False, 'message': 'Invalid attack method'})
        
        # Stop any existing attack
        if dos_process:
            try:
                dos_process.terminate()
                dos_process.wait(timeout=5)
            except:
                pass
        
        # Clear the output queue
        while not dos_output_queue.empty():
            try:
                dos_output_queue.get_nowait()
            except queue.Empty:
                break
        
        # Start the DOS attack process
        command = ['python3', 'DOS.py', url, method]
        
        dos_process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        # Start thread to read output
        dos_thread = threading.Thread(target=read_dos_output, args=(dos_process, dos_output_queue))
        dos_thread.daemon = True
        dos_thread.start()
        
        return jsonify({
            'success': True, 
            'message': f'DOS attack launched with {method} method on {url}'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/stop_dos_attack', methods=['POST'])
def stop_dos_attack():
    """Stop the running DOS attack."""
    global dos_process, dos_thread
    
    try:
        if dos_process:
            # Try to terminate gracefully
            dos_process.terminate()
            
            # Wait for process to terminate
            try:
                dos_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill if it doesn't terminate
                dos_process.kill()
                dos_process.wait()
            
            dos_process = None
            
        return jsonify({'success': True, 'message': 'DOS attack stopped'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/get_attack_output', methods=['GET'])
def get_attack_output():
    """Get the current output from the DOS attack."""
    global dos_process, dos_output_queue
    
    try:
        output_lines = []
        
        # Get all available output
        while not dos_output_queue.empty():
            try:
                line = dos_output_queue.get_nowait()
                output_lines.append(line)
            except queue.Empty:
                break
        
        # Check if process is still running
        finished = dos_process is None or dos_process.poll() is not None
        
        return jsonify({
            'success': True,
            'output': '\n'.join(output_lines) if output_lines else '',
            'finished': finished
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e), 'output': '', 'finished': True})

# Optional: Add a route to check attack status
@app.route('/dos_attack_status', methods=['GET'])
def dos_attack_status():
    """Check the status of the DOS attack."""
    global dos_process
    
    try:
        if dos_process is None:
            status = 'stopped'
        elif dos_process.poll() is None:
            status = 'running'
        else:
            status = 'finished'
            
        return jsonify({
            'success': True,
            'status': status,
            'pid': dos_process.pid if dos_process else None
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# Clean up function to stop DOS attack when app shuts down
def cleanup_dos_attack():
    """Clean up function to stop any running DOS attack."""
    global dos_process
    
    if dos_process:
        try:
            dos_process.terminate()
            dos_process.wait(timeout=5)
        except:
            try:
                dos_process.kill()
            except:
                pass
        finally:
            dos_process = None

# Register cleanup function
import atexit
atexit.register(cleanup_dos_attack)
# Route for handling file upload and AI analysis

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)