import os
from flask import Flask, render_template, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectMultipleField, TextAreaField, widgets
from wtforms.validators import DataRequired, Email, EqualTo, Length
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from llm import generate_feedback

import requests

# Import and load spaCy
import spacy
nlp = spacy.load("en_core_web_md")


# Load environment variables
load_dotenv()

# App Initialization
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Database Models

class Attempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    interview_id = db.Column(db.Integer, db.ForeignKey('interview.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    user_answer = db.Column(db.Text, nullable=False)
    similarity_score = db.Column(db.Float, nullable=True) # Score from spaCy
    feedback = db.Column(db.Text, nullable=True) # General feedback text
    interview = db.relationship('Interview', backref='attempts')
    question = db.relationship('Question', backref='attempts')

class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    questions = db.relationship('Question', backref='subject', lazy=True)

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    model_answer = db.Column(db.Text, nullable=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)

class Interview(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref='interviews')

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# WTForms
class RegistrationForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class TopicSelectionForm(FlaskForm):
    subjects = SelectMultipleField('Choose Subjects', coerce=int, validators=[DataRequired()], widget=widgets.ListWidget(prefix_label=False), option_widget=widgets.CheckboxInput())
    submit = SubmitField('Start Interview')

class AnswerForm(FlaskForm):
    answer = TextAreaField('Your Answer', validators=[DataRequired()], render_kw={'rows': 10})
    submit = SubmitField('Submit Answer')


# Routes

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please log in.')
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.')
    return render_template('login.html', title='Sign In', form=form)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    form = TopicSelectionForm()
    form.subjects.choices = [(s.id, s.name) for s in Subject.query.all()]
    if form.validate_on_submit():
        selected_subject_ids = form.subjects.data
        new_interview = Interview(user_id=current_user.id)
        db.session.add(new_interview)
        db.session.commit()
        questions = (
            Question.query
            .filter(Question.subject_id.in_(selected_subject_ids))
            .order_by(db.func.random())
            .limit(1)
            .all()
        )
        if not questions:
            flash("No questions found for the selected subjects. Please try other subjects.")
            return redirect(url_for('dashboard'))
        session['interview_id'] = new_interview.id
        session['question_ids'] = [q.id for q in questions]
        return redirect(url_for('interview_question', question_index=0))
    return render_template('dashboard.html', title='Dashboard', form=form)

@app.route('/interview/question/<int:question_index>', methods=['GET', 'POST'])
@login_required
def interview_question(question_index):
    if 'question_ids' not in session:
        flash('Interview session not found. Please start a new one.')
        return redirect(url_for('dashboard'))

    question_ids = session['question_ids']
    if question_index >= len(question_ids):
        return redirect(url_for('interview_summary'))

    question_id = question_ids[question_index]
    question = db.session.get(Question, question_id)
    form = AnswerForm()
    if form.validate_on_submit():
        user_answer = form.answer.data
        question = db.session.get(Question, question_id)
        model_answer = question.model_answer or ""
        feedback_text = generate_feedback(user_answer, model_answer)
        attempt = Attempt(
            interview_id = session['interview_id'],
            question_id = question_id,
            user_answer = user_answer,
            feedback = feedback_text
        )
        db.session.add(attempt)
        db.session.commit()
        next_question_index = question_index + 1
        if next_question_index < len(session['question_ids']):
            return redirect(url_for('interview_question', question_index = next_question_index))
        else:
            return redirect(url_for('interview_summary'))

    return render_template('interview_questions.html', question=question, form=form, question_index=question_index, total_questions=len(question_ids))


# Interview Summary Route with NLP Analysis
@app.route('/interview/summary')
@login_required
def interview_summary():
    interview_id = session.pop('interview_id', None)
    session.pop('question_ids', None) # Clean up session
    
    if not interview_id:
        flash("Could not find an interview to summarize.")
        return redirect(url_for('dashboard'))
    
    interview = Interview.query.get_or_404(interview_id)
    
    # Process each answer
    for attempt in interview.attempts:
        if attempt.question.model_answer:

            feedback_text = generate_feedback(attempt.user_answer, attempt.question.model_answer)
            doc_user = nlp(attempt.user_answer)
            doc_model = nlp(attempt.question.model_answer)
            attempt.similarity_score = round((doc_user.similarity(doc_model)) * 100, 2)
            attempt.feedback = feedback_text

        else:
            attempt.similarity_score = 0
            attempt.feedback = "No model answer available to compare against."

    db.session.commit()
    
    return render_template('interview_summary.html', title='Interview Feedback', interview=interview)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
