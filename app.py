from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-vibe-key-12345'
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# --- DYNAMIC DATABASE CONFIGURATION FOR DEPLOYMENT ---
db_url = os.environ.get('DATABASE_URL')
# Modern SQLAlchemy expects the full 'postgresql://' prefix
app.config['SQLALCHEMY_DATABASE_URI'] = db_url or 'sqlite:///database.db'

app.config['SQLALCHEMY_DATABASE_URI'] = db_url or 'sqlite:///database.db'

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    profile_pic = db.Column(db.String(200), nullable=True, default='default_avatar.png')
    memories = db.relationship('Memory', backref='author', lazy=True)

class Memory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=True)
    mood = db.Column(db.String(30), nullable=False)
    # Storing file paths as JSON lists to accommodate multiple uploads seamlessly
    photos_json = db.Column(db.Text, nullable=True, default='[]')
    videos_json = db.Column(db.Text, nullable=True, default='[]')
    audios_json = db.Column(db.Text, nullable=True, default='[]')
    date_created = db.Column(db.Date, default=datetime.utcnow().date)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    @property
    def photos(self):
        return json.loads(self.photos_json or '[]')
    @property
    def videos(self):
        return json.loads(self.videos_json or '[]')
    @property
    def audios(self):
        return json.loads(self.audios_json or '[]')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()

# --- AUTH ROUTES ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username').strip().lower()
        password = request.form.get('password')
        
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('That username is already taken, bestie. Pick another one!', 'error')
            return render_template('signup.html')
            
        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        
        login_user(new_user)
        return redirect(url_for('index'))
        
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username').strip().lower()
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('index'))
        
        flash('Invalid credentials. Read the room. 👁️👄👁️', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- MEMORY APP ROUTES ---
@app.route('/')
@login_required
def index():
    today = datetime.utcnow().date()
    on_this_day = Memory.query.filter(
        Memory.user_id == current_user.id,
        db.extract('month', Memory.date_created) == today.month,
        db.extract('day', Memory.date_created) == today.day,
        db.extract('year', Memory.date_created) < today.year
    ).all()
    
    memories = Memory.query.filter_by(user_id=current_user.id).order_by(Memory.date_created.desc()).all()
    return render_template('index.html', memories=memories, on_this_day=on_this_day)

@app.route('/add_memory', methods=['GET', 'POST'])
@login_required
def add_memory():
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        mood = request.form.get('mood')
        
        uploaded_photos = request.files.getlist('photos')
        uploaded_videos = request.files.getlist('videos')
        uploaded_audios = request.files.getlist('audios')
        
        photo_paths, video_paths, audio_paths = [], [], []
        user_dir = os.path.join(app.config['UPLOAD_FOLDER'], str(current_user.id))
        os.makedirs(user_dir, exist_ok=True)
        
        # Save Photos Loop
        for file in uploaded_photos:
            if file and file.filename:
                filename = f"img_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
                file.save(os.path.join(user_dir, filename))
                photo_paths.append(f'uploads/{current_user.id}/{filename}')
                
        # Save Videos Loop
        for file in uploaded_videos:
            if file and file.filename:
                filename = f"vid_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
                file.save(os.path.join(user_dir, filename))
                video_paths.append(f'uploads/{current_user.id}/{filename}')
                
        # Save Audios Loop
        for file in uploaded_audios:
            if file and file.filename:
                filename = f"aud_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
                file.save(os.path.join(user_dir, filename))
                audio_paths.append(f'uploads/{current_user.id}/{filename}')
            
        new_memory = Memory(
            title=title, content=content, mood=mood,
            photos_json=json.dumps(photo_paths),
            videos_json=json.dumps(video_paths),
            audios_json=json.dumps(audio_paths),
            author=current_user
        )
        db.session.add(new_memory)
        db.session.commit()
        return redirect(url_for('index'))
        
    return render_template('add.html')

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        file = request.files.get('profile_pic')
        if file and file.filename:
            user_dir = os.path.join(app.config['UPLOAD_FOLDER'], str(current_user.id))
            os.makedirs(user_dir, exist_ok=True)
            filename = f"profile_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
            file.save(os.path.join(user_dir, filename))
            current_user.profile_pic = f'uploads/{current_user.id}/{filename}'
            db.session.commit()
            return redirect(url_for('profile'))

    total_memories = Memory.query.filter_by(user_id=current_user.id).count()
    return render_template('profile.html', total_memories=total_memories)

@app.route('/delete_memory/<int:memory_id>', methods=['POST'])
@login_required
def delete_memory(memory_id):
    memory = Memory.query.get_or_404(memory_id)
    
    if memory.user_id != current_user.id:
        flash("You can't delete someone else's scrapbook story, bestie! ✋", "error")
        return redirect(url_for('index'))
    
    db.session.delete(memory)
    db.session.commit()
    
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=8000)
