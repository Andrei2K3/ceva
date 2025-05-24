from flask import Flask, render_template, request, redirect, url_for, session, flash
import json, os, hashlib

from flask import Response
from io import StringIO
import csv

from datetime import datetime

from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors

app = Flask(__name__)
app.secret_key = 'supersecretkey'

DATA_DIR = 'data'
USERS_FILE = os.path.join(DATA_DIR, 'utilizatori.json')
HOTELS_FILE = os.path.join(DATA_DIR, 'hoteluri.json')
ROOMS_FILE = os.path.join(DATA_DIR, 'camere.json')
BOOKINGS_FILE = os.path.join(DATA_DIR, 'rezervari.json')
REVIEWS_FILE = os.path.join(DATA_DIR, 'recenzii.json')
RECLAME_FILE = os.path.join(DATA_DIR, 'reclame.json')

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
    reclame = load_json(RECLAME_FILE)  # incarca reclamele
    return render_template('home.html', hotels=hotels, reclame=reclame)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        users = load_json(USERS_FILE)
        username = request.form['username']
        password = hash_password(request.form['password'])
        role = 'client'
        if any(u['username'] == username for u in users):
            flash('Utilizatorul exista deja')
            return redirect(url_for('register'))
        users.append({'username': username, 'password': password, 'role': role})
        save_json(USERS_FILE, users)
        flash('Cont creat cu succes!')
        return redirect(url_for('login'))
    return render_template('register.html', title='Inregistrare')

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

@app.route('/search')
def search_rooms():
    locatie = request.args.get('locatie')
    checkin = request.args.get('checkin')
    checkout = request.args.get('checkout')

    hotels = load_json(HOTELS_FILE)
    rooms = load_json(ROOMS_FILE)
    bookings = load_json(BOOKINGS_FILE)

    # Gaseste hotelurile din acea locatie
    hoteluri_gasite = [h for h in hotels if locatie.lower() in h['locatie'].lower()]

    camere_disponibile = []
    for hotel in hoteluri_gasite:
        for room in rooms:
            if room['hotel_id'] == hotel['id']:
                ocupata = any(
                    b['room_id'] == room['id'] and b['status'] in ['neconfirmata', 'confirmata', 'platita'] and
                    not (checkout <= b['checkin'] or checkin >= b['checkout'])
                    for b in bookings
                )
                if not ocupata:
                    camere_disponibile.append({'camera': room, 'hotel': hotel})

    return render_template('search_results.html', camere=camere_disponibile, checkin=checkin, checkout=checkout)

@app.route('/rezerva-direct/<int:room_id>', methods=['POST'])
def rezerva_direct(room_id):
    if 'user' not in session:
        return redirect(url_for('login'))

    checkin = request.form['checkin']
    checkout = request.form['checkout']

    if checkin >= checkout:
        flash("Data de check-out trebuie sa fie DUPA check-in.")
        return redirect(url_for('home'))

    bookings = load_json(BOOKINGS_FILE)

    # Verifica suprapunere
    for b in bookings:
        if b['room_id'] == room_id and b['status'] in ['neconfirmata', 'confirmata', 'platita']:
            if not (checkout <= b['checkin'] or checkin >= b['checkout']):
                flash("Camera selectata este deja rezervata in perioada aleasa.")
                return redirect(url_for('home'))

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
    flash('Rezervarea a fost inregistrata direct.')
    return redirect(url_for('my_bookings'))

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

    # Adauga hotel_nume si camera_numar fiecarei rezervari
    for b in bookings:
        room = next((r for r in rooms if r['id'] == b['room_id']), None)
        hotel = next((h for h in hotels if h['id'] == room['hotel_id']), None) if room else None
        b['hotel_nume'] = hotel['nume'] if hotel else 'necunoscut'
        b['camera_numar'] = room['numar'] if room else 'necunoscut'

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
        flash("Eroare la adaugarea camerei")
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

@app.route('/staff/delete-hotel/<int:hotel_id>')
def delete_hotel(hotel_id):
    user = current_user()
    if not user or user['role'] not in ['admin', 'angajat']:
        return redirect(url_for('login'))

    hotels = load_json(HOTELS_FILE)
    rooms = load_json(ROOMS_FILE)
    bookings = load_json(BOOKINGS_FILE)

    # elimina hotelul
    hotels = [h for h in hotels if h['id'] != hotel_id]

    # elimina camerele asociate
    camere_ids = [r['id'] for r in rooms if r['hotel_id'] == hotel_id]
    rooms = [r for r in rooms if r['hotel_id'] != hotel_id]

    # elimina rezervarile asociate acelor camere
    bookings = [b for b in bookings if b['room_id'] not in camere_ids]

    # salveaza fisierele actualizate
    save_json(HOTELS_FILE, hotels)
    save_json(ROOMS_FILE, rooms)
    save_json(BOOKINGS_FILE, bookings)

    flash("Hotelul si toate datele aferente au fost sterse.")
    return redirect(url_for('staff_panel'))

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
        flash("Poti lasa o recenzie doar dupa o rezervare platita.")
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
    flash("Recenzia a fost adaugata cu succes.")
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
            flash("Data de check-out trebuie sa fie DUPA check-in.")
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
        flash('Rezervare inregistrata')
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
    rooms = load_json(ROOMS_FILE)
    hotels = load_json(HOTELS_FILE)

    user = session['user']['username']
    booking = next((b for b in bookings if b['id'] == booking_id and b['user'] == user), None)

    if not booking or booking['status'] != 'confirmata':
        flash("A fost deja platita aceasta rezervare.")
        return redirect(url_for('my_bookings'))

    # Marcheaza rezervarea ca platita
    booking['status'] = 'platita'
    save_json(BOOKINGS_FILE, bookings)

    # Obtine date pentru chitanta
    room = next((r for r in rooms if r['id'] == booking['room_id']), None)
    hotel = next((h for h in hotels if h['id'] == room['hotel_id']), None) if room else None
    pret = room['pret']
    zile = (datetime.strptime(booking['checkout'], '%Y-%m-%d') - datetime.strptime(booking['checkin'], '%Y-%m-%d')).days
    total = zile * pret

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Titlu
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(width / 2, height - 2 * cm, "🧾 CHITANTA DE PLATA")
    c.setStrokeColor(colors.darkgrey)
    c.setLineWidth(1)
    c.line(2 * cm, height - 2.3 * cm, width - 2 * cm, height - 2.3 * cm)

    # Detalii
    c.setFont("Helvetica-Bold", 13)
    c.drawString(2 * cm, height - 3.5 * cm, "Detalii Client")
    c.setFont("Helvetica", 12)

    y = height - 4.2 * cm
    line_height = 18

    def draw_field(label, value):
        nonlocal y
        c.setFont("Helvetica-Bold", 11)
        c.drawString(2 * cm, y, f"{label}:")
        c.setFont("Helvetica", 11)
        c.drawString(6 * cm, y, str(value))
        y -= line_height

    draw_field("Nume client", booking['user'])
    draw_field("Hotel", hotel['nume'] if hotel else 'necunoscut')
    draw_field("Camera", room['numar'] if room else 'necunoscut')
    draw_field("Check-in", booking['checkin'])
    draw_field("Check-out", booking['checkout'])
    draw_field("Pret/noapte", f"{pret} RON")
    draw_field("Numar de nopti", zile)

    # Total Box
    y -= 20
    c.setFillColor(colors.lightblue)
    c.roundRect(2 * cm, y - 1.5 * cm, width - 4 * cm, 1.8 * cm, 10, stroke=0, fill=1)

    c.setFillColor(colors.darkblue)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2.5 * cm, y - 0.7 * cm, f"TOTAL DE PLATA: {total} RON")

    # Footer
    c.setFont("Helvetica-Oblique", 10)
    c.setFillColor(colors.gray)
    c.drawCentredString(width / 2, 2 * cm, "Va multumim pentru rezervare! | www.hotel-booking.ro")

    c.showPage()
    c.save()
    buffer.seek(0)

    # Returneaza chitanta PDF la descarcare
    return Response(
        buffer,
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename=chitanta_{booking_id}.pdf'}
    )


@app.route('/cancel/<int:booking_id>')
def cancel_booking(booking_id):
    if 'user' not in session:
        return redirect(url_for('login'))

    bookings = load_json(BOOKINGS_FILE)
    new_bookings = []

    for b in bookings:
        if b['id'] == booking_id and b['user'] == session['user']['username']:
            if b['status'] in ['neconfirmata', 'confirmata']:
                flash("Rezervarea a fost anulata.")
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
    writer.writerow(['ID', 'Utilizator', 'Hotel', 'Camera', 'Tip', 'Check-in', 'Check-out', 'Status'])

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

@app.route('/contabil')
def contabil_panel():
    if 'user' not in session or session['user']['role'] != 'contabil':
        return redirect(url_for('login'))
    return render_template('contabil_panel.html')

@app.route('/contabil/finante')
def contabil_finante():
    if 'user' not in session or session['user']['role'] != 'contabil':
        return redirect(url_for('login'))

    bookings = load_json(BOOKINGS_FILE)
    rooms = load_json(ROOMS_FILE)
    hotels = load_json(HOTELS_FILE)

    rezervari = []
    total = 0

    for b in bookings:
        if b['status'] == 'platita':
            room = next((r for r in rooms if r['id'] == b['room_id']), None)
            hotel = next((h for h in hotels if h['id'] == room['hotel_id']), None) if room else None

            if room:
                zile = (datetime.strptime(b['checkout'], '%Y-%m-%d') - datetime.strptime(b['checkin'], '%Y-%m-%d')).days
                suma = zile * room['pret']
                total += suma
                rezervari.append({
                    'user': b['user'],
                    'hotel': hotel['nume'] if hotel else 'necunoscut',
                    'room_numar': room['numar'] if room else 'necunoscut',
                    'checkin': b['checkin'],
                    'checkout': b['checkout'],
                    'zile': zile,
                    'pret': room['pret'] if room else 0,
                    'total': suma
                })

    return render_template('finante.html', rezervari=rezervari, total=total)

@app.route('/contabil/reclame', methods=['GET', 'POST'])
def contabil_reclame():
    if 'user' not in session or session['user']['role'] != 'contabil':
        return redirect(url_for('login'))

    if request.method == 'POST':
        titlu = request.form['titlu']
        continut = request.form['continut']
        reclame = load_json(RECLAME_FILE)
        new_id = max([r['id'] for r in reclame], default=0) + 1
        reclame.append({'id': new_id, 'titlu': titlu, 'continut': continut})
        save_json(RECLAME_FILE, reclame)
        flash("Reclama adaugata cu succes.")
        return redirect(url_for('contabil_reclame'))

    reclame = load_json(RECLAME_FILE)
    return render_template('reclame.html', reclame=reclame)

@app.route('/contabil/reclame/delete/<int:id>')
def delete_reclama(id):
    if 'user' not in session or session['user']['role'] != 'contabil':
        return redirect(url_for('login'))

    reclame = load_json(RECLAME_FILE)
    reclame = [r for r in reclame if r['id'] != id]
    save_json(RECLAME_FILE, reclame)
    flash("Reclama stearsa.")
    return redirect(url_for('contabil_reclame'))


if __name__ == '__main__':
    os.makedirs(DATA_DIR, exist_ok=True)
    for f in [USERS_FILE, HOTELS_FILE, ROOMS_FILE, BOOKINGS_FILE, REVIEWS_FILE]:
        if not os.path.exists(f):
            save_json(f, [])
    app.run(debug=True)
