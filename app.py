# app.py
import os, sqlite3, json, io, csv, secrets, bcrypt, datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file, flash
from dotenv import load_dotenv
from flask_mail import Mail, Message
from twilio.rest import Client

load_dotenv()
DB = os.getenv('DATABASE_URL', 'data.db')
SECRET = os.getenv('FLASK_SECRET', 'change-this-secret')
DEBUG = os.getenv('DEBUG', 'True') == 'True'

app = Flask(__name__)
app.secret_key = SECRET
app.config['DEBUG'] = DEBUG

# Mail config
app.config.update(
    MAIL_SERVER=os.getenv('MAIL_SERVER', 'localhost'),
    MAIL_PORT=int(os.getenv('MAIL_PORT', '1025')),
    MAIL_USERNAME=os.getenv('MAIL_USERNAME', ''),
    MAIL_PASSWORD=os.getenv('MAIL_PASSWORD', ''),
    MAIL_DEFAULT_SENDER=os.getenv('MAIL_DEFAULT_SENDER', 'no-reply@example.com'),
    MAIL_USE_TLS=False,
    MAIL_USE_SSL=False
)
mail = Mail(app)

# Twilio
TW_SID = os.getenv('TWILIO_SID','')
TW_TOKEN = os.getenv('TWILIO_AUTH_TOKEN','')
TW_FROM = os.getenv('TWILIO_FROM_NUM','')
SUPERVISOR_NUM = os.getenv('SUPERVISOR_NUM','')
tw_client = Client(TW_SID, TW_TOKEN) if TW_SID and TW_TOKEN else None

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def login_required(role=None):
    def deco(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            if role and session.get('role') != role and session.get('role') != 'supervisor':
                return "Access denied", 403
            return f(*args, **kwargs)
        return wrapped
    return deco

@app.route('/', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password','')
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username=? OR email=?", (username, username))
        u = cur.fetchone()
        conn.close()
        if u and bcrypt.checkpw(password.encode(), u['password_hash'].encode()):
            session['user_id'] = u['id']
            session['user'] = u['username']
            session['role'] = u['role']
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error="Invalid credentials", username=username)
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required()
def dashboard():
    return render_template('dashboard.html', user=session.get('user'), role=session.get('role'))

@app.route('/users')
@login_required(role='supervisor')
def users():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, username, role, email, phone, created_at FROM users ORDER BY created_at DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return render_template('users.html', users=rows)

@app.route('/api/create_user', methods=['POST'])
@login_required(role='supervisor')
def create_user():
    payload = request.get_json(force=True)
    username = payload.get('username')
    pw = payload.get('password')
    role = payload.get('role','asha')
    email = payload.get('email','')
    phone = payload.get('phone','')
    if not username or not pw:
        return jsonify({"ok": False, "message": "username and password required"}), 400
    phash = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO users (username, password_hash, role, email, phone) VALUES (?,?,?,?,?)",
                    (username, phash, role, email, phone))
        conn.commit()
        return jsonify({"ok": True})
    except sqlite3.IntegrityError:
        return jsonify({"ok": False, "message": "username exists"}), 400
    finally:
        conn.close()

@app.route('/api/delete_user', methods=['POST'])
@login_required(role='supervisor')
def delete_user():
    payload = request.get_json(force=True)
    uid = payload.get('id')
    if not uid:
        return jsonify({"ok": False}), 400
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route('/reset-request', methods=['GET','POST'])
def reset_request():
    if request.method == 'POST':
        email_or_user = request.form.get('email_or_user')
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username=? OR email=?", (email_or_user, email_or_user))
        u = cur.fetchone()
        if not u:
            flash("No account found", "danger")
            return redirect(url_for('reset_request'))
        token = secrets.token_urlsafe(32)
        cur.execute("INSERT INTO password_resets (user_id, token) VALUES (?,?)", (u['id'], token))
        conn.commit()
        conn.close()
        reset_link = url_for('reset_password', token=token, _external=True)
        try:
            if u['email']:
                msg = Message("Password reset for ASHA Portal", recipients=[u['email']])
                msg.body = f"Reset link:\n\n{reset_link}\n\nIf you didn't request, ignore."
                mail.send(msg)
                flash("Password reset link sent to email (if configured).", "info")
            else:
                print("Reset link for user", u['username'], reset_link)
                flash("No email configured — reset link printed to server console.", "warning")
        except Exception as e:
            print("Mail error:", e)
            print("Reset link:", reset_link)
            flash("Could not send email; reset link printed to console.", "warning")
        return redirect(url_for('login'))
    return render_template('reset_password.html')

@app.route('/reset/<token>', methods=['GET','POST'])
def reset_password(token):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM password_resets WHERE token=? ORDER BY created_at DESC LIMIT 1", (token,))
    row = cur.fetchone()
    if not row:
        return "Invalid or expired token", 400
    created = None
    try:
        created = datetime.datetime.fromisoformat(row['created_at'])
    except Exception:
        created = None
    if created and (datetime.datetime.utcnow() - created).total_seconds() > 3600:
        return "Token expired", 400
    if request.method == 'POST':
        pw = request.form.get('password')
        if len(pw) < 8:
            flash("Password must be at least 8 characters", "danger")
            return redirect(request.url)
        phash = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
        cur.execute("UPDATE users SET password_hash=? WHERE id=?", (phash, row['user_id']))
        conn.commit()
        conn.close()
        flash("Password reset successful.", "success")
        return redirect(url_for('login'))
    return render_template('reset_password.html', token=token)

# Data entry + detection
@app.route('/api/submit_entry', methods=['POST'])
@login_required()
def submit_entry():
    payload = request.get_json(force=True)
    module = payload.get('module')
    data = json.dumps(payload.get('data', {}))
    flagged = enhanced_risk_check(module, payload.get('data', {}))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO entries (module, data, flagged, status) VALUES (?,?,?,?)", (module, data, int(flagged), 'pending'))
    entry_id = cur.lastrowid
    if flagged:
        cur.execute("INSERT INTO notifications (message, target_user, sent) VALUES (?,?,?)",
                    (f"High-risk detected in {module} entry id:{entry_id}", session.get('user'), 0))
        notify_supervisor_sms(f"High-risk detected in {module} entry id:{entry_id}")
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "entry_id": entry_id, "flagged": bool(flagged)})

def enhanced_risk_check(module, data):
    try:
        if module == 'child':
            age = float(data.get('age', 999) or 999)
            weight = float(data.get('weight', 999) or 999)
            if age < 1 or weight < 2.5:
                return True
        if module == 'ncd':
            bp = (data.get('bp') or '').replace(' ','')
            diabetes = (data.get('diabetes') or '').lower()
            if bp:
                try:
                    parts = bp.split('/')
                    sys = int(parts[0]); dia = int(parts[1]) if len(parts)>1 else 0
                    if sys >= 140 or dia >= 90:
                        return True
                except:
                    pass
            if diabetes in ('yes','y','true','1'):
                return True
        if module == 'maternal':
            anc = int(data.get('anc_visit',0) or 0)
            if anc < 2:
                return True
    except Exception as e:
        print("Risk check error:", e)
    return False

def notify_supervisor_sms(message):
    if not tw_client or not TW_FROM or not SUPERVISOR_NUM:
        print("Twilio not configured or missing numbers; skipping SMS. Msg:", message)
        return False
    try:
        tw_client.messages.create(body=message, from_=TW_FROM, to=SUPERVISOR_NUM)
        return True
    except Exception as e:
        print("Twilio error:", e)
        return False

@app.route('/api/sync_queue', methods=['POST'])
@login_required()
def sync_queue():
    payload = request.get_json(force=True)
    items = payload.get('items', [])
    conn = get_db()
    cur = conn.cursor()
    results = []
    for item in items:
        module = item.get('module')
        data = json.dumps(item.get('data', {}))
        flagged = enhanced_risk_check(module, item.get('data', {}))
        cur.execute("INSERT INTO entries (module, data, flagged, status) VALUES (?,?,?,?)", (module, data, int(flagged), 'pending'))
        e_id = cur.lastrowid
        if flagged:
            cur.execute("INSERT INTO notifications (message, target_user, sent) VALUES (?,?,?)",
                        (f"High-risk detected in {module} entry id:{e_id}", session.get('user'), 0))
            notify_supervisor_sms(f"High-risk detected in {module} entry id:{e_id}")
        results.append({"id": e_id, "flagged": bool(flagged)})
    conn.commit()
    conn.close()
    return jsonify({"synced": len(results), "details": results})

@app.route('/api/notifications', methods=['GET'])
@login_required()
def notifications():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM notifications ORDER BY created_at DESC LIMIT 50")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route('/supervisor')
@login_required(role='supervisor')
def supervisor_panel():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM entries ORDER BY created_at DESC LIMIT 500")
    entries = [dict(r) for r in cur.fetchall()]
    conn.close()
    return render_template('supervisor.html', entries=entries)

@app.route('/api/supervisor_action', methods=['POST'])
@login_required(role='supervisor')
def supervisor_action():
    payload = request.get_json(force=True)
    entry_id = payload.get('entry_id')
    action = payload.get('action')
    conn = get_db()
    cur = conn.cursor()
    status = 'approved' if action == 'approve' else ('rejected' if action == 'reject' else 'clarify')
    cur.execute("UPDATE entries SET status=? WHERE id=?", (status, entry_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "entry_id": entry_id, "status": status})

@app.route('/export/csv')
@login_required(role='supervisor')
def export_csv():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, module, data, status, flagged, created_at FROM entries ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['id','module','data','status','flagged','created_at'])
    for r in rows:
        cw.writerow([r[0], r[1], r[2], r[3], r[4], r[5]])
    mem = io.BytesIO()
    mem.write(si.getvalue().encode('utf-8'))
    mem.seek(0)
    return send_file(mem, mimetype='text/csv', download_name='entries_export.csv', as_attachment=True)

@app.route('/api/healthcheck')
def healthcheck():
    return jsonify({"ok": True, "server": "running"})

if __name__ == '__main__':
    if not os.path.exists(DB):
        print("Database not found. Run db_init.py to create DB and seed users.")
    app.run(debug=DEBUG, host='0.0.0.0', port=5000)
