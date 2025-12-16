import random, os, csv
from datetime import datetime, timezone
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
from docx import Document
from pytz import timezone as localtimezone
from dotenv import load_dotenv


app = Flask(__name__)
app.secret_key = "TUPC_DED_REVIEWER_1022"

## Database Configuration ##
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///let_reviewer.db' # <-- Main database
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_BINDS'] = {
    'users_db': 'sqlite:///users.db', # <-- Users database
    'questions_db': 'sqlite:///questions.db', # <-- Questions database
}

db = SQLAlchemy(app)

# Model Database #

class User(db.Model):

    __bind_key__ = 'users_db'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(512), nullable=False)
    cellphone = db.Column(db.String(150), nullable=False)
    major = db.Column(db.String(150), nullable=True)
    is_admin = db.Column(db.Boolean, default=False)
    otp_code = db.Column(db.String(6), nullable=True)

    def set_password(self, password):
        self.password = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password, password)

class Question(db.Model):

    __bind_key__ = 'questions_db'

    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(500), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    choice_a = db.Column(db.Text, nullable=False)
    choice_b = db.Column(db.Text, nullable=False)
    choice_c = db.Column(db.Text, nullable=False)
    choice_d = db.Column(db.Text, nullable=False)
    correct_answer = db.Column(db.String(1), nullable=False)

    def __repr__(self):
        return f'<Question {self.id} ({self.subject}): {self.question_text[:30]}...>'
    
class Attempt(db.Model):

    __bind_key__ = 'users_db'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    username = db.Column(db.String(150), nullable=False)
    major = db.Column(db.String(150), nullable=True)
    subject = db.Column(db.String(50), nullable=False)
    score = db.Column(db.Float, nullable=False)
    max_score = db.Column(db.Float, nullable=False)
    date_taken = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    duration_seconds = db.Column(db.Integer, nullable=True)

    student = db.relationship('User', backref='attempts')


# OTP #
load_dotenv()
BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
SENDER_EMAIL = "letreviewer1022@gmail.com"
SENDER_NAME = "LET Reviewer"

configuration = sib_api_v3_sdk.Configuration()
configuration.api_key['api-key'] = BREVO_API_KEY

api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))

def generate_otp():
    return str(random.randint(100000, 999999))

def save_otp_to_user(user):
    otp_code = generate_otp()
    user.otp_code = otp_code
    db.session.commit()
    return otp_code

def send_otp_email(user, otp_code):
    html_content = f"""
    <html>
      <body>
        <h2>OTP Verification</h2>
        <p>Hello {user.username},</p>
        <h1>{otp_code}</h1>
        <p>This code is valid for 5 minutes.</p>
      </body>
    </html>
    """

    email = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": user.email, "name": user.username}],
        sender={"email": SENDER_EMAIL, "name": SENDER_NAME},
        subject="Your OTP Code",
        html_content=html_content
    )

    try:
        api_instance.send_transac_email(email)
        print("OTP email sent successfully")
        return True
    except ApiException as e:
        print("Brevo API Exception:", e)
        return False

def verify_user_otp(user, otp_code):
    if user.otp_code == otp_code:
        # OTP is valid
        user.otp_code = None
        db.session.commit()
        return True
    else:
        # OTP invalid or expired
        return False


## Questions ##

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = ['docx', 'csv']
ALLOWED_SUBJECTS = {
    'profed', 'gened', 'cp', 'et', 'he', 'ia', 'ict'
}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def check_for_duplicate(question_text):
    existing_question = Question.query.filter(
        Question.question_text == question_text
    ).first()
    return existing_question is not None

def process_csv(filepath, subject_tag):
    new_questions = []
    inserted_count = 0
    duplicate_count = 0

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None)
            with app.app_context():
                for row in reader:
                    if len(row) >= 6:
                        q_text = row[0].strip()

                        if check_for_duplicate(q_text):
                            duplicate_count += 1
                            continue 
                            
                        q = Question(
                            subject = subject_tag, 
                            question_text=q_text,
                            choice_a=row[1].strip(),
                            choice_b=row[2].strip(),
                            choice_c=row[3].strip(),
                            choice_d=row[4].strip(),
                            correct_answer=row[5].strip().lower()
                        )
                        new_questions.append(q)
                        inserted_count += 1
                    else:
                        flash(f"Skipped row in CSV (Expected 6 columns).", 'warning')      
                db.session.add_all(new_questions)
                db.session.commit()
                success_msg = f"Processed {inserted_count + duplicate_count} rows. Added {inserted_count} new questions."
                if duplicate_count > 0:
                     success_msg += f" ({duplicate_count} duplicates skipped.)"
                return inserted_count, None, success_msg          
    except Exception as e:
        db.session.rollback()
        return 0, f"Error processing CSV: {e}", None
    
def process_docx(filepath, subject_tag):
    document = Document(filepath)
    new_questions = []
    inserted_count = 0

    try:
        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if "Q:" in text and "A)" in text and "B)" in text and "C)" in text and "D)" in text and "Ans:" in text:
                try:
                    q_parts = text.split("Ans:")
                    correct_answer = q_parts[-1].strip().split()[0].lower() 
                    qc_part = q_parts[0].replace("Q:", "").strip() 
                    
                    parts = qc_part.split('A)')
                    question_text = parts[0].strip()
                    
                    choices_part = 'A)' + parts[1]
                    choices = [c.strip() for c in choices_part.split(' B)')]
                    
                    choice_b_d = choices[1].split(' C)')
                    choice_b = choice_b_d[0].strip()
                    
                    choice_c_d = choice_b_d[1].split(' D)')
                    choice_c = choice_c_d[0].strip()
                    choice_d = choice_c_d[1].strip()

                    q = Question(
                        subject=subject_tag,
                        question_text=question_text,
                        choice_a=choices[0].replace('A)', '').strip(),
                        choice_b=choice_b.replace('B)', '').strip(),
                        choice_c=choice_c.replace('C)', '').strip(),
                        choice_d=choice_d.replace('D)', '').strip(),
                        correct_answer=correct_answer
                    )
                    new_questions.append(q)
                    inserted_count += 1
                except Exception:
                    continue 
        
        db.session.add_all(new_questions)
        db.session.commit()
        return inserted_count, None

    except Exception as e:
        return 0, f"Error processing DOCX: {e}"

PHILIPPINES_TZ = localtimezone('Asia/Manila')

@app.template_filter('localize_time')
def localize_time_filter(utc_dt):
    if not utc_dt:
        return 'N/A'
    utc_aware_dt = utc_dt.replace(tzinfo=localtimezone('UTC'))
    local_dt = utc_aware_dt.astimezone(PHILIPPINES_TZ)
    return local_dt.strftime('%b %d, %Y %I:%M %p')

@app.template_filter('format_duration')
def format_duration_filter(seconds):
    if seconds is None:
        return 'N/A'
    seconds = int(seconds)
    minutes = seconds // 60
    remaining_seconds = seconds % 60

    return f"{minutes:02d}:{remaining_seconds:02d}"

## Routes ##

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/quiz', methods=['GET', 'POST'])
def quiz():
    logged_in = 'username' in session
    user = None

    if logged_in:
        user = User.query.filter_by(username=session['username']).first()
        if not user:
            session.clear()
            flash("Please log in first.", "warning")
            return redirect(url_for('login'))

    if request.method == 'POST':
        action = request.form.get('action')
        value = request.form.get('value')

        # 🔒 LOGIN RESTRICTION
        if not logged_in:
            flash("Log-in first", "warning")
            return redirect(url_for('quiz')+ '#started-section')

        # 🎯 SUBJECT SELECTION
        if action == 'subject':
            session['selected_subject'] = value
            flash(f"Subject selected: {value}", "success")
            return redirect(url_for('quiz')+ '#started-section')

        # 🔢 ITEM COUNT SELECTION
        elif action == 'items':
            session['selected_items'] = int(value)
            flash(f"Items selected: {value}", "success")
            return redirect(url_for('quiz')+ '#items')

        # ▶️ START QUIZ
        elif action == 'start':
            if 'selected_subject' not in session or 'selected_items' not in session:
                flash("Please select a subject and number of items first.", "warning")
            else:
                flash("Quiz started successfully!", "success")
                return redirect(url_for('quiz_page'))

    return render_template(
        'quiz.html',
        logged_in=logged_in,
        current_user=user,
        selected_subject=session.get('selected_subject'),
        selected_items=session.get('selected_items')
    )

@app.route('/quiz_page')
def quiz_page():
    if 'username' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for('quiz'))

    subject = session.get('selected_subject')
    items = session.get('selected_items')

    

    if not subject or not items:
        flash("Quiz setup incomplete. Please try again.", "warning")
        return redirect(url_for('quiz'))

    # 🎯 FETCH RANDOM QUESTIONS
    print(f"DEBUG: Starting query for subject='{subject}', items={items}")

    questions = []

    try:
        questions = (
            Question.query
            .filter_by(subject=subject)
            .order_by(db.func.random())
            .limit(items)
            .all()
        )
    
        print(f"DEBUG: Query successful. Retrieved {len(questions)} questions.")

    except Exception as e:

        print(f"FATAL DEBUG: Database query failed with error: {e}")

    if not questions:
        flash("No questions available for this subject.", "danger")
        return redirect(url_for('quiz'))
    
    if 'quiz_start_time' not in session:
        session['quiz_start_time'] = datetime.now().isoformat()

    return render_template(
        'quiz_page.html',
        subject=subject,
        items=items,
        questions=questions
    )

@app.route('/submit_quiz', methods=['POST'])
def submit_quiz():
    if 'username' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for('login'))

    submitted_answers = {key: value for key, value in request.form.items() if key.startswith("q")}
    username_from_session = session['username']

    user = User.query.filter_by(username=username_from_session).first()
    if not user:
        flash("User session error. Please log in again.", "danger")
        session.clear()
        return redirect(url_for('login'))
    
    # Get the quiz subject to filter questions
    subject = session.get('selected_subject')
    items = session.get('selected_items')

    ids_string = request.form.get('question_ids_shown')
    
    if not ids_string:
        flash("Quiz session data corrupted. Cannot score accurately.", "danger")
        return redirect(url_for('quiz_page'))
    try:
        displayed_ids = [int(q_id) for q_id in ids_string.split(',') if q_id.isdigit()]
    except ValueError:
        flash("Invalid question ID format received.", "danger")
        return redirect(url_for('quiz_page'))
    
    questions = Question.query.filter(Question.id.in_(displayed_ids)).all()

    question_map = {q.id: q for q in questions}
    questions = [question_map[q_id] for q_id in displayed_ids if q_id in question_map]
    
    total_questions = len(questions)

    if not questions or total_questions != items:
        flash("Question mismatch detected. Scoring aborted.", "danger")
        return redirect(url_for('quiz_page'))
    
    score = 0
    results = []

    for q in questions:
        user_answer = submitted_answers.get(f"q{q.id}", None) 
        correct_answer = q.correct_answer.upper()
        if user_answer and user_answer.upper() == correct_answer:
            score += 1

        results.append({
            "question_text": q.question_text,
            "selected": user_answer,
            "correct": correct_answer,
            "choices": {
                "A": q.choice_a,
                "B": q.choice_b,
                "C": q.choice_c,
                "D": q.choice_d
            }
        })

    start_time_str = session.get('quiz_start_time')
    time_taken = "N/A"
    duration_seconds = None
    if start_time_str:
        start_time = datetime.fromisoformat(start_time_str)
        end_time = datetime.now()
        time_taken_seconds = (end_time - start_time).total_seconds()
        duration_seconds = int(time_taken_seconds)
        minutes = int(time_taken_seconds // 60)
        seconds = int(time_taken_seconds % 60)
        time_taken = f"{minutes:02d}:{seconds:02d}"
    else:
        time_taken = "N/A"
    session.pop('quiz_start_time', None)
    session.pop('selected_subject', None)
    session.pop('selected_items', None)

    flash(f"Quiz submitted! You scored {score} out of {len(questions)}.", "success")

    try:
        new_attempt = Attempt(
            student_id=user.id,
            username=user.username,
            major=user.major,
            subject=subject,
            score=float(score),
            max_score=float(total_questions),
            date_taken=datetime.utcnow(),
            duration_seconds=duration_seconds
        )
        db.session.add(new_attempt)
        db.session.commit()
        flash(f"Quiz submitted! Your score has been recorded.", "success")
    except Exception as e:
        db.session.rollback()
        print(f"FATAL DEBUG: Failed to save quiz attempt: {e}")
        flash("Quiz submission recorded, but failed to save to history.", "warning")

    return render_template(
        'results.html',
        username=user.username,
        subject=subject,
        time_taken=time_taken,
        score=score,
        total_questions=len(questions),
        results=results
    )


@app.route('/mock', methods=['GET', 'POST'])
def mock():
    logged_in = 'username' in session
    user = None

    if logged_in:
        user = User.query.filter_by(username=session['username']).first()
        if not user:
            session.clear()
            flash("Please log in first.", "warning")
            return redirect(url_for('login'))

    if request.method == 'POST':
        action = request.form.get('action')

        if not logged_in:
            flash("Log-in first", "warning")
            return redirect(url_for('mock')+ '#started-section')

        # ▶️ START QUIZ
        elif action == 'start':
            session['mock_start_time'] = datetime.now().isoformat()
            return redirect(url_for('mock_exam_page'))

    return render_template(
        'mock.html',
        logged_in=logged_in,
        current_user=user,
        selected_subject=session.get('selected_subject'),
        selected_items=session.get('selected_items')
    )

@app.route('/mock_exam_page')
def mock_exam_page():
    if 'username' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for('mock'))

    # Total items per subject
    items_per_subject = 150

    # Fetch questions from all subjects
    subjects = ['gened', 'profed', 'major']
    questions = []
    total_questions_retrieved = 0

    print("--- DEBUG: Mock Exam Question Fetching Started ---")
    print(f"Target items per subject: {items_per_subject}")

    for subject in subjects:
        qs = (
            Question.query
            .filter_by(subject=subject)
            .order_by(db.func.random())
            .limit(items_per_subject)
            .all()
        )
        questions.extend(qs)
        retrieved_count = len(qs)
        print(f"-> Subject '{subject}': Retrieved {retrieved_count} questions (Target: {items_per_subject})")
        
        total_questions_retrieved += retrieved_count

    print(f"--- DEBUG: Total Questions Retrieved: {total_questions_retrieved} ---")
    if not questions:
        flash("No questions available for the mock exam.", "danger")
        return redirect(url_for('mock'))

    # Save quiz start time
    if 'mock_start_time' not in session:
        session['mock_start_time'] = datetime.now().isoformat()

    # Total time in seconds: 3 hours = 180 min = 10800 seconds
    total_time_seconds = 3 * 60 * 60

    return render_template(
        'mock_exam_page.html',
        questions=questions,
        total_items=len(questions),
        total_time_seconds=total_time_seconds
    )

@app.route('/submit_mock_exam', methods=['POST'])
def submit_mock_exam():
    if 'username' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for('login'))

    submitted_answers = {key: value for key, value in request.form.items() if key.startswith("q")}
    username_from_session = session['username']
    user = User.query.filter_by(username=username_from_session).first()
    if not user:
        flash("User session error. Please log in again.", "danger")
        session.clear()
        return redirect(url_for('login'))
    
    submitted_ids = []
    try:
        submitted_ids = [int(key[1:]) for key in submitted_answers.keys() if key.startswith('q')]
    except ValueError:
        flash("Invalid submission data received.", "danger")
        return redirect(url_for('mock'))

    if not submitted_ids:
        flash("No answers were submitted.", "warning")
        return redirect(url_for('mock'))
    
    questions = Question.query.filter(Question.id.in_(submitted_ids)).all()
    total_questions = len(questions)

    score = 0
    results = []

    for q in questions:
        user_answer = submitted_answers.get(f"q{q.id}", None)
        correct_answer = q.correct_answer.upper()
        is_correct = False

        if user_answer and user_answer.upper() == correct_answer:
            score += 1
            is_correct = True

        results.append({
            "question_text": q.question_text,
            "selected": user_answer,
            "correct": correct_answer,
            "is_correct": is_correct,
            "choices": {
                "A": q.choice_a,
                "B": q.choice_b,
                "C": q.choice_c,
                "D": q.choice_d
            }
        })

    # Calculate time taken
    mock_start_time_str = session.get('mock_start_time')
    time_taken = "N/A"

    if isinstance(mock_start_time_str, str): # Robust check
        try:
            start_time = datetime.fromisoformat(mock_start_time_str)
            end_time = datetime.now()
            time_taken_seconds = (end_time - start_time).total_seconds()
            duration_seconds = int(time_taken_seconds)
            minutes = int(time_taken_seconds // 60)
            seconds = int(time_taken_seconds % 60)
            time_taken = f"{minutes:02d}:{seconds:02d}"
        except ValueError:
            print("DEBUG: mock_start_time in session is not a valid ISO format string.")

    session.pop('mock_start_time', None)

    flash(f"Mock Exam submitted! You scored {score} out of {total_questions}.", "success")
    try:
        new_attempt = Attempt(
            student_id=user.id,
            username=user.username,
            major=user.major,
            subject="Mock Exam", # Subject is explicitly set to "Mock Exam"
            score=float(score),
            max_score=float(total_questions),
            date_taken=datetime.utcnow(),
            duration_seconds=duration_seconds
        )
        db.session.add(new_attempt)
        db.session.commit()
        flash(f"Mock Exam submitted! Your score has been recorded.", "success")
    except Exception as e:
        db.session.rollback()
        print(f"FATAL DEBUG: Failed to save mock attempt: {e}")
        flash("Mock Exam submission recorded, but failed to save to history.", "warning")

    return render_template(
        'results.html',
        username=session.get('username'),
        subject="Mock Exam",
        time_taken=time_taken,
        score=score,
        total_questions=len(questions),
        results=results
    )

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email')
        cellphone = request.form.get('cellphone')
        confirm_password = request.form.get('confirm_password')
        major = request.form.get('major')
        if not all([username, password, email, cellphone, confirm_password, major]):
            flash("Please fill out all required fields.", "danger")
            return redirect(url_for("register"))
        if password != confirm_password:
            flash("Passwords do not match. Please try again.", "danger")
            return redirect(url_for("register"))
        user = User.query.filter_by(username=username).first()
        email_user = User.query.filter_by(email=email).first()
        if user:
            flash("Username already exists. Please choose a different one.", "danger")
            return redirect(url_for("register"))
        elif email_user:
            flash("Email already registered. Please use a different email.", "danger")
            return redirect(url_for("register"))
        else:
            new_user = User(username=username, email=email, cellphone=cellphone, major=major)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            
            session['username'] = username
            flash(f"Registration successful! Welcome, {username}!", "success")
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if not username or not password:
            flash('Please fill out both fields.', 'error')
            return redirect(url_for('login'))
        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            flash('Invalid username or password.', 'danger')
            return redirect(url_for('login'))
        session['username'] = user.username
        session['is_admin'] = user.is_admin
        otp_code = save_otp_to_user(user)
        if not send_otp_email(user,otp_code):
            flash('Failed to send OTP email. Please try again later.', 'danger')
            return redirect(url_for('login'))
        session['otp_user_id'] = user.id
        session['otp_start_time'] = datetime.now(timezone.utc).timestamp()
        flash('OTP sent to your email. Please check your inbox.', 'info')
        return redirect(url_for('verify_otp'))
    return render_template('login.html')

@app.route('/verify_otp', methods=['GET','POST'])
def verify_otp():
    if request.method == 'GET':
        return render_template('verify_otp.html')
    user_otp = request.form.get('otp_code')
    user_id = session.get('otp_user_id')
    if not user_id:
        flash('Session expired. Please log in again.', 'danger')
        return redirect(url_for('login'))
    user = User.query.get(user_id)
    if not user:
        flash('User not found. Please log in again.', 'danger')
        return redirect(url_for('login'))
    if verify_user_otp(user, user_otp):
        session['username'] = user.username
        session.pop('otp_user_id', None)
        flash(f'Welcome back, {user.username}!', 'success')
        if not session.get('is_admin', False):
            return redirect(url_for('dashboard'))  
        else:
            return redirect(url_for('admin_dashboard'))
    else:
        flash('Invalid or expired OTP. Please try again.', 'danger')
        return redirect(url_for('login'))
    
@app.route('/resend_otp', methods=['GET'])
def resend_otp():
    user_id = session.get('otp_user_id')
    if not user_id:
        flash('Session expired. Please log in again.', 'danger')
        return redirect(url_for('login'))
    user = User.query.get(user_id)
    if not user:
        flash('User not found. Please log in again.', 'danger')
        return redirect(url_for('login'))
    otp_code = save_otp_to_user(user)
    if not send_otp_email(user, otp_code):
        flash('Failed to resend OTP email. Please try again later.', 'danger')
        return redirect(url_for('login'))
    flash('OTP resent to your email. Please check your inbox.', 'info')
    return redirect(url_for('verify_otp'))

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('Email not found. Please try again.', 'danger')
            return redirect(url_for('forgot_password'))
        otp_code = save_otp_to_user(user)
        if not send_otp_email(user, otp_code):
            flash('Failed to send OTP email. Please try again later.', 'danger')
            return redirect(url_for('forgot_password'))
        session['otp_user_id'] = user.id
        session['otp_context'] = 'reset'
        return redirect(url_for('reset_otp_page'))
    return render_template('forgot_password.html')

@app.route('/reset_otp', methods=['GET', 'POST'])
def reset_otp_page():
    user_id = session.get('otp_user_id')
    context = session.get('otp_context')
    if context != 'reset' or not user_id:
        flash('Invalid session. Please try again.', 'danger')
        return redirect(url_for('forgot_password'))
    user = User.query.get(user_id)
    if request.method == 'POST':
        user_otp = request.form.get('otp_code')
        if verify_user_otp(user, user_otp):
            session.pop('otp_user_id', None)
            session.pop('otp_context', None)
            session['reset_allowed_id'] = user.id
            flash('OTP verified. Please set your new password.', 'success')
            return redirect(url_for('set_new_password'))
        else:
            flash('Invalid or expired OTP. Please try again.', 'danger')
            return redirect(url_for('reset_otp_page'))
    return render_template('verify_otp.html', context='reset')

@app.route('/set_new_password', methods=['GET', 'POST'])
def set_new_password():
    user_id = session.get('reset_allowed_id')
    if not user_id:
        flash('Accesss denied. Please verify OTP first.', 'danger')
        return redirect(url_for('forgot_password'))
    user = User.query.get(user_id)
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        if not password or password != confirm_password:
            flash("Passwords do not match or are empty. Please try again.", "danger")
            return redirect(url_for('set_new_password'))
        user.set_password(password)
        db.session.commit()
        session.pop('reset_allowed_id', None)
        flash('Password reset successful! You can now log in with your new password.', 'success')
        return redirect(url_for('login'))
    return render_template('set_new_password.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        flash('Please log in to access the dashboard.', 'danger')
        return redirect(url_for('login'))
    username_from_session = session['username']
    user = User.query.filter_by(username=username_from_session).first()
    if not user:
        flash('User not found. Please log in again.', 'danger')
        session.pop('username', None)
        return redirect(url_for('login'))
    user_attempts = Attempt.query.filter_by(student_id=user.id).order_by(Attempt.date_taken.desc()).all()
    return render_template('dashboard.html', current_user=user, attempts=user_attempts)

@app.route('/admin_dashboard')
def admin_dashboard():
    username_from_session = session['username']
    user = User.query.filter_by(username=username_from_session).first()
    if not session.get('is_admin', False):
        flash('Access Denied: Adminnistrators only.', 'danger')
        return redirect(url_for('index'))
    return render_template('admin_dashboard.html', current_user=user)

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/admin_question')
def admin_question():
    username_from_session = session['username']
    user = User.query.filter_by(username=username_from_session).first()
    subjects = {
        'profed': Question.query.filter_by(subject='profed').all(),
        'gened': Question.query.filter_by(subject='gened').all(),
        'cp': Question.query.filter_by(subject='cp').all(),
        'et': Question.query.filter_by(subject='et').all(),
        'he': Question.query.filter_by(subject='he').all(),
        'ia': Question.query.filter_by(subject='ia').all(),
        'ict': Question.query.filter_by(subject='ict').all()
    }

    return render_template(
        'admin_question.html',
        subjects=subjects,
        allowed_subjects=sorted(ALLOWED_SUBJECTS),
        current_user=user
    )

@app.route('/submit_upload', methods=['POST'])
def submit_upload():
    
    file = request.files.get('file')
    subject_tag = request.form.get('subject_tag', '').lower()

    if not file or file.filename == '' or subject_tag not in ALLOWED_SUBJECTS:
        flash('Upload failed: Missing file or invalid subject.', 'danger')
        return redirect(url_for('admin_question'))

    if not allowed_file(file.filename):
        flash('Upload failed: File type not allowed (must be CSV or DOCX).', 'danger')
        return redirect(url_for('admin_question'))

    safe_name = secure_filename(file.filename)
    filename = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)
    file.save(filename)
    
    ext = filename.rsplit('.', 1)[1].lower()
    
    with app.app_context():
        inserted_count = 0
        error = None
        
        if ext == 'csv':
            inserted_count, error = process_csv(filename, subject_tag)
        elif ext == 'docx':
            inserted_count, error = process_docx(filename, subject_tag)

    if os.path.exists(filename):
        os.remove(filename)

    if error:
        flash(f"Upload FAILED for {subject_tag.upper()}. Reason: {error}", 'danger')
    else:
        flash(f"Successfully uploaded and categorized {inserted_count} questions under: {subject_tag.upper()}", 'success')
        
    return redirect(url_for('admin_question'))

@app.route('/delete_question', methods=['POST'])
def delete_question():
    if not session.get('is_admin'):
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))
    question_ids = request.form.getlist('question_ids')
    if not question_ids:
        flash("No questions were selected for deletion.", 'warning')
        return redirect(url_for('admin_question'))
    try:
        ids_to_delete = [int(q_id) for q_id in question_ids]
        deleted_count = db.session.query(Question) \
            .filter(Question.id.in_(ids_to_delete)) \
            .delete(synchronize_session='fetch')
        db.session.commit()
        flash(f"Successfully deleted {deleted_count} question(s).", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Error during batch deletion: {e}", 'danger')
    return redirect(url_for('admin_question'))

@app.route("/admin_student")
def admin_student():
    username_from_session = session['username']
    user = User.query.filter_by(username=username_from_session).first()
    students = User.query.filter_by(is_admin=False).all()
    return render_template("admin_student.html", students=students, current_user=user)

@app.route("/admin_attempt")
def admin_attempt():
    if 'username' not in session or not session.get('is_admin'):
        flash("Unauthorized access. Admin privileges required.", "danger")
        return redirect(url_for('login'))
        
    username_from_session = session['username']
    user = User.query.filter_by(username=username_from_session).first()

    all_attempts = Attempt.query.order_by(Attempt.date_taken.desc()).all()

    students = User.query.filter_by(is_admin=False).all()
    return render_template(
        "admin_attempt.html", 
        students=students, 
        current_user=user,
        attempts=all_attempts
    )

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)