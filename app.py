from flask import (Flask, render_template, request, redirect,
                   url_for, flash, jsonify, session as flask_session)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user,
                         login_required, logout_user, current_user)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from detection.detector import process_frame
import os, uuid, json

# ─── App Config ──────────────────────────────────────────────
app = Flask(__name__)
app.config['SECRET_KEY']                  = os.urandom(24).hex()
app.config['SQLALCHEMY_DATABASE_URI']     = 'sqlite:///drowsyguard.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER']              = os.path.join('static', 'uploads')
app.config['MAX_CONTENT_LENGTH']         = 5 * 1024 * 1024  # 5 MB
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

db           = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view     = 'login'
login_manager.login_message  = 'Please log in to access this page.'

# ─── Models ──────────────────────────────────────────────────
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id             = db.Column(db.Integer, primary_key=True)
    username       = db.Column(db.String(80),  unique=True,  nullable=False)
    email          = db.Column(db.String(120), unique=True,  nullable=False)
    password_hash  = db.Column(db.String(256), nullable=False)
    full_name      = db.Column(db.String(120), default='')
    bio            = db.Column(db.Text,         default='')
    avatar         = db.Column(db.String(255),  default='')
    created_at     = db.Column(db.DateTime,     default=datetime.utcnow)
    total_sessions = db.Column(db.Integer,      default=0)
    total_alerts   = db.Column(db.Integer,      default=0)
    total_minutes  = db.Column(db.Integer,      default=0)
    sessions       = db.relationship('DetectionSession', backref='user', lazy=True)

    def set_password(self, pw):   self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)

    @property
    def avatar_url(self):
        if self.avatar and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], self.avatar)):
            return url_for('static', filename=f'uploads/{self.avatar}')
        return url_for('static', filename='img/default_avatar.svg')

    @property
    def member_since(self):
        return self.created_at.strftime('%B %Y')


class DetectionSession(db.Model):
    __tablename__ = 'sessions'
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    start_time  = db.Column(db.DateTime, default=datetime.utcnow)
    end_time    = db.Column(db.DateTime, nullable=True)
    alert_count = db.Column(db.Integer, default=0)
    duration    = db.Column(db.Integer, default=0)   # seconds
    status      = db.Column(db.String(20), default='active')

    @property
    def duration_str(self):
        m, s = divmod(self.duration, 60)
        h, m = divmod(m, 60)
        return f'{h:02d}:{m:02d}:{s:02d}'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ─── Helpers ─────────────────────────────────────────────────
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ─── Routes: Auth ────────────────────────────────────────────
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        password   = request.form.get('password', '')
        remember   = request.form.get('remember') == 'on'
        user = (User.query.filter_by(email=identifier).first() or
                User.query.filter_by(username=identifier).first())
        if user and user.check_password(password):
            login_user(user, remember=remember)
            next_page = request.args.get('next')
            flash(f'Welcome back, {user.username}!', 'success')
            return redirect(next_page or url_for('dashboard'))
        flash('Invalid credentials. Please try again.', 'error')
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username  = request.form.get('username', '').strip()
        email     = request.form.get('email', '').strip().lower()
        full_name = request.form.get('full_name', '').strip()
        password  = request.form.get('password', '')
        confirm   = request.form.get('confirm_password', '')

        if password != confirm:
            flash('Passwords do not match.', 'error')
        elif len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
        elif User.query.filter_by(username=username).first():
            flash('Username already taken.', 'error')
        elif User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
        else:
            user = User(username=username, email=email, full_name=full_name)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash('Account created successfully! Welcome to DrowsyGuard.', 'success')
            return redirect(url_for('dashboard'))
    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


# ─── Routes: Dashboard ───────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    recent = (DetectionSession.query
              .filter_by(user_id=current_user.id)
              .order_by(DetectionSession.start_time.desc())
              .limit(5).all())
    return render_template('dashboard.html', recent_sessions=recent)


# ─── Routes: Profile ─────────────────────────────────────────
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        action = request.form.get('action', 'update_info')

        if action == 'update_info':
            current_user.full_name = request.form.get('full_name', '').strip()
            current_user.bio       = request.form.get('bio', '').strip()
            new_email = request.form.get('email', '').strip().lower()
            if new_email != current_user.email:
                if User.query.filter_by(email=new_email).first():
                    flash('Email already in use.', 'error')
                    return redirect(url_for('profile'))
                current_user.email = new_email

            if 'avatar' in request.files:
                file = request.files['avatar']
                if file and file.filename and allowed_file(file.filename):
                    ext      = file.filename.rsplit('.', 1)[1].lower()
                    filename = f'{current_user.id}_{uuid.uuid4().hex}.{ext}'
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    current_user.avatar = filename

            db.session.commit()
            flash('Profile updated successfully.', 'success')

        elif action == 'change_password':
            old_pw = request.form.get('old_password', '')
            new_pw = request.form.get('new_password', '')
            conf   = request.form.get('confirm_new_password', '')
            if not current_user.check_password(old_pw):
                flash('Current password is incorrect.', 'error')
            elif new_pw != conf:
                flash('New passwords do not match.', 'error')
            elif len(new_pw) < 6:
                flash('Password must be at least 6 characters.', 'error')
            else:
                current_user.set_password(new_pw)
                db.session.commit()
                flash('Password changed successfully.', 'success')

        return redirect(url_for('profile'))

    sessions_page = (DetectionSession.query
                     .filter_by(user_id=current_user.id)
                     .order_by(DetectionSession.start_time.desc())
                     .limit(10).all())
    return render_template('profile.html', sessions=sessions_page)


# ─── API: Detection ──────────────────────────────────────────
_frame_counters = {}   # user_id → frame counter

@app.route('/api/detect', methods=['POST'])
@login_required
def api_detect():
    data = request.get_json(silent=True) or {}
    image = data.get('image', '')
    uid   = current_user.id
    fc    = _frame_counters.get(uid, 0)
    result = process_frame(image, fc)
    _frame_counters[uid] = result['frame_counter']
    return jsonify(result)


@app.route('/api/session/start', methods=['POST'])
@login_required
def api_session_start():
    sess = DetectionSession(user_id=current_user.id)
    db.session.add(sess)
    db.session.commit()
    _frame_counters[current_user.id] = 0
    return jsonify({'session_id': sess.id})


@app.route('/api/session/end', methods=['POST'])
@login_required
def api_session_end():
    data       = request.get_json(silent=True) or {}
    session_id = data.get('session_id')
    alerts     = data.get('alerts', 0)
    duration   = data.get('duration', 0)

    sess = db.session.get(DetectionSession, session_id)
    if sess and sess.user_id == current_user.id:
        sess.end_time    = datetime.utcnow()
        sess.alert_count = alerts
        sess.duration    = duration
        sess.status      = 'completed'

        current_user.total_sessions += 1
        current_user.total_alerts   += alerts
        current_user.total_minutes  += duration // 60
        db.session.commit()

    return jsonify({'ok': True})


# ─── Run ─────────────────────────────────────────────────────
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True, port=5000)
