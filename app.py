import os
import requests
import openmeteo_requests
import pandas as pd
import requests_cache
import random
import pymysql
from password_process import password_processor, password_verifier
from questions import quiz_questions
from map_weather_code import map_weather_code
from retry_requests import retry
from flask import Flask, render_template, request, redirect, url_for, flash, session
# from pymongo import MongoClient, DESCENDING
# from dotenv import load_dotenv
from datetime import datetime

# load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(24)
# my_sql_password = os.getenv('MONGO_url')

# Sebelumnya menggunakan MongoDB, tapi karena PythonAnywhere Free tidak mendukung koneksinya
# Maka beralih ke MySql internal built in dari PythonAnywhere

def create_connection():
    return pymysql.connect(
    host="AbdulHakim12.mysql.pythonanywhere-services.com",
    user="AbdulHakim12",
    password="*********", # Password hardcoded, karena memang hanya dapat dijalankan di environment PythonAnywhere terkait
    database="AbdulHakim12$default",
    cursorclass=pymysql.cursors.DictCursor
)


# ROUTING ---
@app.route('/', methods=['GET', 'POST'])
def home():
    weather_data = None
    error = None

    if request.method == 'POST':
        city = request.form['city']

        try:
            geo_url = "https://geocoding-api.open-meteo.com/v1/search"
            geo_params = {"name": city, "count": 1, "language": "en", "format": "json"}
            geo_response = requests.get(geo_url, params=geo_params)
            geo_response.raise_for_status()
            geo_data = geo_response.json()

            if not geo_data.get('results'):
                raise ValueError("City not found")

            location = geo_data['results'][0]
            latitude = location['latitude']
            longitude = location['longitude']
            cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
            retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
            openmeteo = openmeteo_requests.Client(session=retry_session)

            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": latitude,
                "longitude": longitude,
                "daily": ["weather_code", "temperature_2m_max", "temperature_2m_min"],
                "timezone": "auto",
                "forecast_days": 4
            }
            responses = openmeteo.weather_api(url, params=params)
            response = responses[0]
            daily = response.Daily()
            daily_weather_code = daily.Variables(0).ValuesAsNumpy()
            daily_temp_max = daily.Variables(1).ValuesAsNumpy()
            daily_temp_min = daily.Variables(2).ValuesAsNumpy()
            daily_dates = pd.date_range(
                start=pd.to_datetime(daily.Time(), unit="s"),
                end=pd.to_datetime(daily.TimeEnd(), unit="s"),
                freq=pd.Timedelta(seconds=daily.Interval()),
                inclusive="left"
            )

            daily_forecasts = []
            for i in range(1, 4): # Loop for the next 3 days
                desc, icon = map_weather_code(daily_weather_code[i])
                forecast = {
                    'date': daily_dates[i].strftime('%d %b %Y'),
                    'day_of_week': daily_dates[i].strftime('%A'),
                    'day_temp': round(daily_temp_max[i]),
                    'night_temp': round(daily_temp_min[i]),
                    'description': desc,
                    'ikon': icon
                }
                daily_forecasts.append(forecast)

            weather_data = {
                'city': location.get('name', city).title(),
                'forecast': daily_forecasts
            }

        except ValueError as ve:
            error = str(ve)
        except Exception as e:
            print(f"Error: {e}")
            error = "An error occurred while fetching data."

    return render_template('index.html', weather=weather_data, error=error)

# REGISTER ROUTE
@app.route("/register", methods=['GET', 'POST'])
def registration():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        conn = create_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
            existing_user = cursor.fetchone()

        if existing_user:
            conn.close()
            flash('Username already taken')
            return redirect(url_for('registration'))

        if password != confirm_password:
            conn.close()
            flash('Both password are not same')
            return redirect(url_for('registration'))

        hashed_password = password_processor(password)

        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (username, password, quiz_score) VALUES (%s, %s, %s)",
                (username, hashed_password, 0)
            )
            conn.commit()

        conn.close()
        flash('Registration Success!')
        return redirect(url_for('login_process'))

    return render_template('register.html')

# LOGIN ROUTE
@app.route('/login', methods=['GET', 'POST'])
def login_process():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = create_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
            user = cursor.fetchone()
        conn.close()

        if user and password_verifier(user['password'], password):
            session['logged_in'] = True
            session['username'] = username
            flash('Login Success')
            return redirect(url_for('dashboard'))
        else:
            flash('Wrong Username or Password!!!')
            return redirect(url_for('login_process'))

    return render_template('login.html')


# DASHBOARD ROUTES ---
@app.route('/dashboard')
def dashboard():
  if 'logged_in' in session:
    return render_template('dashboard.html')

  else:
    flash('Please login fisrt!')
    return render_template('login.html')

@app.route('/quiz', methods=['GET', 'POST'])
def quiz():
    if 'username' not in session:
        flash('Please login first!')
        return redirect(url_for('login_process'))

    conn = create_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM users WHERE username=%s", (session['username'],))
        user = cursor.fetchone()

    current_score = user.get('quiz_score', 0)

    if request.method == 'POST':
        question_id = int(request.form['question_id'])
        user_answer = request.form['user_answer']
        question_answered = next((q for q in quiz_questions if q['id'] == question_id), None)

        if question_answered:
            if user_answer == question_answered['answer']:
                current_score += 1
                flash('Correct! +1 point.', 'success')
            else:
                current_score -= 1
                flash(f"Wrong!. -1 point.", 'error')

            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET quiz_score=%s WHERE username=%s",
                    (current_score, session['username'])
                )
                conn.commit()

        conn.close()
        return redirect(url_for('quiz'))

    # GET logic
    with conn.cursor() as cursor:
        cursor.execute("SELECT username, quiz_score FROM users ORDER BY quiz_score DESC LIMIT 5")
        top_5_users = cursor.fetchall()
    conn.close()

    random_question = random.choice(quiz_questions)
    return render_template('quiz.html', question=random_question, score=current_score, leaderboard=top_5_users)


@app.route('/finish_quiz')
def finish_quiz():
    if 'username' not in session:
        flash('Please login first!')
        return redirect(url_for('login_process'))

    conn = create_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM users WHERE username=%s", (session['username'],))
        user = cursor.fetchone()
    conn.close()

    score = user.get('quiz_score', 0)
    return render_template('quiz_result.html', score=score)


@app.route('/leaderboard')
def leaderboard():
  if 'username' not in session:
    flash('Please login first to see leaderboard')
    return redirect(url_for('login_process'))

  conn = create_connection()
  with conn.cursor() as cursor:
    cursor.execute("SELECT username, quiz_score FROM users ORDER BY quiz_score DESC")
    all_users = cursor.fetchall()

  conn.close()

  return render_template('leaderboard.html', users=all_users)

@app.route('/logout')
def logout():
  session.clear()
  flash('Logged Out')
  return redirect(url_for('login_process'))

# if __name__ == '__main__':
#   app.run(debug= True)
