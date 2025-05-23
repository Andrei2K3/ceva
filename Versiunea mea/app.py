from flask import Flask, render_template, request, redirect, url_for, session, flash
import json, os, hashlib

from flask import Response
from io import StringIO
import csv

app = Flask(__name__)
app.secret_key = 'supersecretkey'

DATA_DIR = 'data'
USERS_FILE = os.path.join(DATA_DIR, 'utilizatori.json')
HOTELS_FILE = os.path.join(DATA_DIR, 'hoteluri.json')
ROOMS_FILE = os.path.join(DATA_DIR, 'camere.json')
BOOKINGS_FILE = os.path.join(DATA_DIR, 'rezervari.json')
REVIEWS_FILE = os.path.join(DATA_DIR, 'recenzii.json')

# Helper functions
def load_json(path):
    if not os.path.exists(path):
        return []
    with open(path, 'r') as f:
        return json.load(f)

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def current_user():
    return session.get('user')

# Routes
@app.route('/')
def home():
    hotels = load_json(HOTELS_FILE)
    return render_template('home.html', hotels=hotels)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        users = load_json(USERS_FILE)
        username = request.form['username']
        password = hash_password(request.form['password'])
        role = 'client'
        if any(u['username'] == username for u in users):
            flash('Utilizatorul există deja')
            return redirect(url_for('register'))
        users.append({'username': username, 'password': password, 'role': role})
        save_json(USERS_FILE, users)
        flash('Cont creat cu succes!')
        return redirect(url_for('login'))
    return render_template('register.html', title='Înregistrare')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        users = load_json(USERS_FILE)
        username = request.form['username']
        password = hash_password(request.form['password'])
        user = next((u for u in users if u['username'] == username and u['password'] == password), None)
        if user:
            session['user'] = user
            return redirect(url_for('home'))
        else:
            flash('Date incorecte')
    return render_template('login.html', title='Autentificare')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('home'))

@app.route('/admin')
def admin_panel():
    user = current_user()
    if not user or user['role'] != 'admin':
        return redirect(url_for('login'))
    users = load_json(USERS_FILE)
    hotels = load_json(HOTELS_FILE)
    rooms = load_json(ROOMS_FILE)
    bookings = load_json(BOOKINGS_FILE)
    return render_template('admin_panel.html', users=users, hotels=hotels, rooms=rooms, bookings=bookings)

@app.route('/staff')
def staff_panel():
    user = current_user()
    if not user or user['role'] != 'angajat':
        return redirect(url_for('login'))
    hotels = load_json(HOTELS_FILE)
    rooms = load_json(ROOMS_FILE)
    bookings = load_json(BOOKINGS_FILE)
    return render_template('staff_panel.html', hotels=hotels, rooms=rooms, bookings=bookings)

@app.route('/staff/add-hotel', methods=['POST'])
def staff_add_hotel():
    user = current_user()
    if not user or user['role'] != 'angajat':
        return redirect(url_for('login'))
    hotels = load_json(HOTELS_FILE)
    name = request.form.get('nume')
    location = request.form.get('locatie')
    if name and location:
        new_id = max([h['id'] for h in hotels], default=0) + 1
        hotels.append({"id": new_id, "nume": name, "locatie": location})
        save_json(HOTELS_FILE, hotels)
    return redirect(url_for('staff_panel'))

@app.route('/staff/add-room', methods=['POST'])
def staff_add_room():
    user = current_user()
    if not user or user['role'] != 'angajat':
        return redirect(url_for('login'))
    rooms = load_json(ROOMS_FILE)
    try:
        new_room = {
            "id": max([r['id'] for r in rooms], default=0) + 1,
            "hotel_id": int(request.form['hotel_id']),
            "numar": request.form['numar'],
            "tip": request.form['tip'],
            "pret": float(request.form['pret'])
        }
        rooms.append(new_room)
        save_json(ROOMS_FILE, rooms)
    except:
        flash("Eroare la adăugarea camerei")
    return redirect(url_for('staff_panel'))

@app.route('/update-booking/<int:booking_id>/<action>')
def update_booking(booking_id, action):
    user = current_user()
    if not user or user['role'] not in ['admin', 'angajat']:
        return redirect(url_for('login'))
    bookings = load_json(BOOKINGS_FILE)
    for b in bookings:
        if b['id'] == booking_id:
            if action == 'confirm':
                b['status'] = 'confirmata'
            elif action == 'reject':
                b['status'] = 'respinsa'
            break
    save_json(BOOKINGS_FILE, bookings)
    return redirect(url_for('admin_panel') if user['role'] == 'admin' else url_for('staff_panel'))

@app.route('/hotel/<int:hotel_id>', methods=['GET'])
def hotel_detail(hotel_id):
    hotels = load_json(HOTELS_FILE)
    rooms = load_json(ROOMS_FILE)
    reviews = load_json(REVIEWS_FILE)
    hotel = next((h for h in hotels if h['id'] == hotel_id), None)
    hotel_rooms = [r for r in rooms if r['hotel_id'] == hotel_id]
    hotel_reviews = [r for r in reviews if r['hotel_id'] == hotel_id]
    return render_template('hotel.html', hotel=hotel, rooms=hotel_rooms, reviews=hotel_reviews)

@app.route('/hotel/<int:hotel_id>/review', methods=['POST'])
def add_review(hotel_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    bookings = load_json(BOOKINGS_FILE)
    has_paid = any(
        b['user'] == session['user']['username'] and b['status'] == 'platita' and
        any(r['hotel_id'] == hotel_id and r['id'] == b['room_id'] for r in load_json(ROOMS_FILE))
        for b in bookings
    )
    if not has_paid:
        flash("Poți lăsa o recenzie doar după o rezervare plătită.")
        return redirect(url_for('hotel_detail', hotel_id=hotel_id))

    reviews = load_json(REVIEWS_FILE)
    new_review = {
        'id': len(reviews) + 1,
        'hotel_id': hotel_id,
        'user': session['user']['username'],
        'text': request.form['text']
    }
    reviews.append(new_review)
    save_json(REVIEWS_FILE, reviews)
    flash("Recenzia a fost adăugată cu succes.")
    return redirect(url_for('hotel_detail', hotel_id=hotel_id))

@app.route('/book/<int:room_id>', methods=['GET', 'POST'])
def book(room_id):
    if 'user' not in session:
        return redirect(url_for('login'))

    rooms = load_json(ROOMS_FILE)
    hotels = load_json(HOTELS_FILE)
    camera = next((r for r in rooms if r['id'] == room_id), None)
    hotel = next((h for h in hotels if h['id'] == camera['hotel_id']), None) if camera else None

    if request.method == 'POST':
        checkin = request.form['checkin']
        checkout = request.form['checkout']

        if checkin >= checkout:
            flash("Data de check-out trebuie să fie DUPĂ check-in.")
            return redirect(url_for('book', room_id=room_id))

        bookings = load_json(BOOKINGS_FILE)
        new_id = max((b['id'] for b in bookings), default=0) + 1
        new_booking = {
            'id': new_id,
            'user': session['user']['username'],
            'room_id': room_id,
            'checkin': checkin,
            'checkout': checkout,
            'status': 'neconfirmata'
        }
        bookings.append(new_booking)
        save_json(BOOKINGS_FILE, bookings)
        flash('Rezervare înregistrată')
        return redirect(url_for('my_bookings'))

    return render_template('book.html', room_id=room_id, camera=camera, hotel=hotel)

@app.route('/my-bookings')
def my_bookings():
    if 'user' not in session:
        return redirect(url_for('login'))
    bookings = load_json(BOOKINGS_FILE)
    rooms = load_json(ROOMS_FILE)
    hotels = load_json(HOTELS_FILE)
    user_bookings = [b for b in bookings if b['user'] == session['user']['username']]
    return render_template('my_bookings.html', bookings=user_bookings, rooms=rooms, hotels=hotels)

@app.route('/pay/<int:booking_id>')
def pay_booking(booking_id):
    if 'user' not in session:
        return redirect(url_for('login'))

    bookings = load_json(BOOKINGS_FILE)
    updated = False

    for b in bookings:
        if b['id'] == booking_id and b['user'] == session['user']['username']:
            if b['status'] == 'confirmata':
                b['status'] = 'platita'
                updated = True
            break

    if updated:
        save_json(BOOKINGS_FILE, bookings)
        flash("Rezervarea a fost plătită cu succes.")
    else:
        flash("Nu se poate plăti această rezervare.")

    return redirect(url_for('my_bookings'))

@app.route('/cancel/<int:booking_id>')
def cancel_booking(booking_id):
    if 'user' not in session:
        return redirect(url_for('login'))

    bookings = load_json(BOOKINGS_FILE)
    new_bookings = []

    for b in bookings:
        if b['id'] == booking_id and b['user'] == session['user']['username']:
            if b['status'] in ['neconfirmata', 'confirmata']:
                flash("Rezervarea a fost anulată.")
                continue
        new_bookings.append(b)

    save_json(BOOKINGS_FILE, new_bookings)
    return redirect(url_for('my_bookings'))

from flask import Response
from io import StringIO
import csv

@app.route('/export-reservari', endpoint='export_rezervari')
def export_rezervari():
    user = session.get('user')
    if not user or user['role'] not in ['admin', 'angajat']:
        return redirect(url_for('login'))

    bookings = load_json(BOOKINGS_FILE)
    rooms = load_json(ROOMS_FILE)
    hotels = load_json(HOTELS_FILE)

    output = StringIO()
    writer = csv.writer(output)

    # Header CSV
    writer.writerow(['ID', 'Utilizator', 'Hotel', 'Cameră', 'Tip', 'Check-in', 'Check-out', 'Status'])

    for b in bookings:
        room = next((r for r in rooms if r['id'] == b['room_id']), None)
        hotel = next((h for h in hotels if h['id'] == room['hotel_id']), None) if room else None
        writer.writerow([
            b['id'],
            b['user'],
            hotel['nume'] if hotel else 'necunoscut',
            room['numar'] if room else 'necunoscut',
            room['tip'] if room else '',
            b['checkin'],
            b['checkout'],
            b['status']
        ])

    output.seek(0)
    return Response(
        output,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=rezervari.csv'}
    )



if __name__ == '__main__':
    os.makedirs(DATA_DIR, exist_ok=True)
    for f in [USERS_FILE, HOTELS_FILE, ROOMS_FILE, BOOKINGS_FILE, REVIEWS_FILE]:
        if not os.path.exists(f):
            save_json(f, [])
    app.run(debug=True)
