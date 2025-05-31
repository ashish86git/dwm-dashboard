from flask import Flask, render_template, request, redirect, url_for, session, send_file,flash,jsonify
import pandas as pd
import os
import psycopg2
from flask_sqlalchemy import SQLAlchemy
from folium.plugins import Fullscreen

from psycopg2.extras import RealDictCursor
from werkzeug.utils import secure_filename

from werkzeug.security import generate_password_hash, check_password_hash

from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import folium

from geopy.geocoders import Nominatim
from geopy.distance import geodesic

import uuid
from datetime import datetime,date, timedelta

app = Flask(__name__)
app.secret_key = 'tms-secret-key'

# Import your models and db
from models import db, Fleet, DriverMaster, Order
from models import db, Route

DATA_PATH = "data/"
orders_data = []
geolocator = Nominatim(user_agent="tms")

UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['SQLALCHEMY_DATABASE_URI'] = (
    'postgresql://{user}:{password}@{host}:{port}/{database}'.format(
        user='u7tqojjihbpn7s',
        password='p1b1897f6356bab4e52b727ee100290a84e4bf71d02e064e90c2c705bfd26f4a5',
        host='c7s7ncbk19n97r.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com',
        port=5432,
        database='d8lp4hr6fmvb9m'
    )
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
# db.init_app(app)

# --------- AUTHENTICATION -----------
# Simulated user database (replace with actual DB in production)
# Database configuration
db_config = {
    'host': 'c7s7ncbk19n97r.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com',
    'user': 'u7tqojjihbpn7s',
    'password': 'p1b1897f6356bab4e52b727ee100290a84e4bf71d02e064e90c2c705bfd26f4a5',
    'database': 'd8lp4hr6fmvb9m',
    'port': 5432
}

# Connect to the PostgreSQL database
def get_db_connection():
    conn = psycopg2.connect(
        host=db_config['host'],
        user=db_config['user'],
        password=db_config['password'],
        dbname=db_config['database'],
        port=db_config['port']
    )
    return conn

@app.route('/', methods=['GET', 'POST'])
def auth():
    if request.method == 'POST':
        form_type = request.form.get('form_type')

        # LOGIN
        # LOGIN
        if form_type == 'login':
            username = request.form['username']
            password = request.form['password']

            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('SELECT * FROM users_tms WHERE username = %s', (username,))
            user = cursor.fetchone()
            cursor.close()
            conn.close()

            if user:
                stored_password = user['password']
                if stored_password == password or check_password_hash(stored_password, password):
                    session['user'] = username
                    return redirect(url_for('dashboard'))  # 👈 Go to dashboard after login

            return render_template('login.html', error='Invalid username or password', form_type='login')



        # SIGNUP
        elif form_type == 'signup':
            username = request.form['username']
            email = request.form['email']
            password = request.form['password']

            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('SELECT * FROM users_tms WHERE username = %s', (username,))
            existing_user = cursor.fetchone()

            if existing_user:
                cursor.close()
                conn.close()
                return render_template('login_signup.html', error='Username already exists', form_type='signup')
            else:
                hashed_password = generate_password_hash(password)
                cursor.execute(
                    'INSERT INTO users_tms (username, email, password) VALUES (%s, %s, %s)',
                    (username, email, hashed_password)
                )
                conn.commit()
                cursor.close()
                conn.close()
                session['user'] = username
                return redirect(url_for('dashboard'))

    return render_template('login.html', form_type='login')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('auth'))  # Redirect to login if not logged in
    return render_template('dashboard.html', username=session['user'])

@app.route('/logout')
def logout():
    session.clear()  # Clear all session data
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth'))



# --------- FLEET MASTER -----------
# ---------- Fleet Master View ----------
@app.route('/fleet_master', methods=['GET'])
def fleet_master():
    if 'user' not in session:
        session['user'] = 'Admin'  # Temporary session for demo

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM fleet ORDER BY vehicle_id")
    rows = cursor.fetchall()

    fleet_data = [{
        'vehicle_id': row[0],
        'vehicle_name': row[1],
        'make': row[2],
        'model': row[3],
        'vin': row[4],
        'type': row[5],
        'group': row[6],
        'status': row[7],
        'license_plate': row[8],
        'current_meter': row[9],
        'capacity_wei': row[10],
        'capacity_vol': row[11],
        'documents_expiry': row[12].strftime('%Y-%m-%d') if row[12] else '',
        'driver_id': row[13],
        'date_of_join': row[14].strftime('%Y-%m-%d') if row[14] else ''
    } for row in rows]

    cursor.close()
    conn.close()

    return render_template('fleet_master.html', data=fleet_data, user=session['user'])

# ---------- Add Vehicle ----------
@app.route('/fleet_master/add', methods=['POST'])
def add_vehicle():
    form = request.form

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO fleet (
                vehicle_id, vehicle_name, make, model, vin, type, "group", status,
                license_plate, current_meter, capacity_weight_kg, capacity_vol_cbm,
                documents_expiry, driver_id, date_of_join
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            form['vehicle_id'],
            form['vehicle_name'],
            form['make'],
            form['model'],
            form['vin'],
            form['type'],
            form['group'],
            form['status'],
            form['license_plate'],
            int(form['current_meter']),
            float(form['capacity_wei']),
            float(form['capacity_vol']),
            datetime.strptime(form['documents_expiry'], '%Y-%m-%d'),
            form['driver_id'],
            datetime.strptime(form['date_of_join'], '%Y-%m-%d')
        ))

        conn.commit()
        flash('Vehicle added successfully!', 'success')

    except psycopg2.IntegrityError:
        conn.rollback()
        flash('Vehicle ID already exists.', 'danger')
    except Exception as e:
        conn.rollback()
        flash(f'Error: {str(e)}', 'danger')
    finally:
        cursor.close()
        conn.close()

    return redirect('/fleet_master')

# ---------- Delete Vehicle ----------
@app.route('/fleet_master/delete/<vehicle_id>', methods=['POST'])
def delete_vehicle(vehicle_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM fleet WHERE vehicle_id = %s", (vehicle_id,))
        conn.commit()

        flash('Vehicle deleted successfully!', 'success')

    except Exception as e:
        conn.rollback()
        flash(f'Error deleting vehicle: {str(e)}', 'danger')
    finally:
        cursor.close()
        conn.close()

    return redirect('/fleet_master')

# ---------- Edit Vehicle ----------
@app.route('/fleet_master/edit/<vehicle_id>', methods=['GET', 'POST'])
def edit_vehicle(vehicle_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        form = request.form
        try:
            # Convert date fields if not empty, else None
            documents_expiry = form.get('documents_expiry')
            if documents_expiry:
                documents_expiry = datetime.strptime(documents_expiry, '%Y-%m-%d').date()
            else:
                documents_expiry = None

            date_of_join = form.get('date_of_join')
            if date_of_join:
                date_of_join = datetime.strptime(date_of_join, '%Y-%m-%d').date()
            else:
                date_of_join = None

            cursor.execute("""
                UPDATE fleet
                SET vehicle_name = %s,
                    driver_id = %s,
                    make = %s,
                    model = %s,
                    vin = %s,
                    type = %s,
                    "group" = %s,
                    status = %s,
                    license_plate = %s,
                    current_meter = %s,
                    capacity_weight_kg = %s,
                    capacity_vol_cbm = %s,
                    documents_expiry = %s,
                    date_of_join = %s
                WHERE vehicle_id = %s
            """, (
                form.get('vehicle_name'),
                form.get('assigned_driver'),
                form.get('make'),
                form.get('model'),
                form.get('vin'),
                form.get('type'),
                form.get('group'),
                form.get('status'),
                form.get('license_plate'),
                int(form.get('current_meter') or 0),
                float(form.get('capacity_weight_kg') or 0),
                float(form.get('capacity_vol_cbm') or 0),
                documents_expiry,
                date_of_join,
                vehicle_id
            ))

            conn.commit()
            flash('Vehicle updated successfully!', 'success')
            return redirect('/fleet_master')

        except Exception as e:
            conn.rollback()
            flash(f'Error updating vehicle: {str(e)}', 'danger')
            return redirect('/fleet_master')

    # GET method - show current data
    cursor.execute("SELECT * FROM fleet WHERE vehicle_id = %s", (vehicle_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if not row:
        flash('Vehicle not found.', 'warning')
        return redirect('/fleet_master')

    # Map row to dict with proper keys (adjust indices based on your table structure)
    vehicle_data = {
        'vehicle_id': row[0],
        'vehicle_name': row[1],
        'make': row[2],
        'model': row[3],
        'vin': row[4],
        'type': row[5],
        'group': row[6],
        'status': row[7],
        'license_plate': row[8],
        'current_meter': row[9],
        'capacity_weight_kg': row[10],
        'capacity_vol_cbm': row[11],
        'documents_expiry': row[12].strftime('%Y-%m-%d') if row[12] else '',
        'driver_id': row[13],
        'date_of_join': row[14].strftime('%Y-%m-%d') if row[14] else '',
    }

    return render_template('edit_vehicle.html', vehicle=vehicle_data, user=session.get('user', ''))

# --------- DRIVER MASTER -----------
@app.route('/driver_master', methods=['GET', 'POST'])
def driver_master():
    if 'user' not in session:
        return redirect('/')

    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        form_data = request.form.to_dict()

        # Handle file uploads
        aadhar_file = request.files['aadhar_file']
        license_file = request.files['license_file']

        aadhar_filename = secure_filename(aadhar_file.filename)
        license_filename = secure_filename(license_file.filename)

        aadhar_path = os.path.join(UPLOAD_FOLDER, aadhar_filename)
        license_path = os.path.join(UPLOAD_FOLDER, license_filename)

        aadhar_file.save(aadhar_path)
        license_file.save(license_path)

        # Insert into DB
        cur.execute("""
            INSERT INTO driver_master (
                driver_id, driver_name, license_number,
                contact_number, address, availability, shift_info, aadhar_file, license_file
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            form_data['driver_id'],
            form_data['driver_name'],
            form_data['license_number'],
            form_data['contact_number'],
            form_data['address'],
            form_data['availability'],
            form_data['shift_info'],
            aadhar_filename,
            license_filename
        ))
        conn.commit()

    # Fetch all drivers
    cur.execute("SELECT driver_id, driver_name, license_number, contact_number, address, availability, shift_info, aadhar_file, license_file FROM driver_master")
    rows = cur.fetchall()
    colnames = [desc[0] for desc in cur.description]
    data = [dict(zip(colnames, row)) for row in rows]

    cur.close()
    conn.close()

    return render_template('driver_master.html', data=data)






# --------- VEHICLE Details -----------

vehicles = []
service_records = []
vehicle_counter = 1
service_counter = 1
# Vehicle list & filtering
@app.route('/vehicle_maintenance')
def vehicle_maintenance():
    if 'user' not in session:
        return redirect('/')  # Assuming login route

    filters = {
        'vehicle_id': request.args.get('vehicle_id', '').strip(),
        'assigned_driver': request.args.get('assigned_driver', '').strip(),
        'status': request.args.get('status', '').strip()
    }

    filtered = vehicles
    if filters['vehicle_id']:
        filtered = [v for v in filtered if filters['vehicle_id'].lower() in v['vehicle_id'].lower()]
    if filters['assigned_driver']:
        filtered = [v for v in filtered if filters['assigned_driver'].lower() in v['assigned_driver'].lower()]
    if filters['status']:
        filtered = [v for v in filtered if v['status'] == filters['status']]

    return render_template('vehicle_maintenance.html', vehicles=filtered, filters=filters)

@app.route('/add_vehicle', methods=['GET', 'POST'])
def add_vehicle_form():
    global vehicle_counter
    if request.method == 'POST':
        data = request.form.to_dict()
        data['id'] = vehicle_counter
        data['service_cost'] = float(data.get('service_cost') or 0)
        data['last_service_date'] = datetime.strptime(data.get('last_service_date', ''), '%Y-%m-%d') if data.get('last_service_date') else None
        data['next_service_due'] = datetime.strptime(data.get('next_service_due', ''), '%Y-%m-%d') if data.get('next_service_due') else None
        vehicles.append(data)
        vehicle_counter += 1
        flash("Vehicle added successfully", "success")
        return redirect(url_for('vehicle_maintenance'))

    return render_template('add_vehicle.html')

@app.route('/add_service/<int:vehicle_id>', methods=['GET', 'POST'])
def add_service(vehicle_id):
    global service_counter
    vehicle = next((v for v in vehicles if v['id'] == vehicle_id), None)
    if not vehicle:
        flash("Vehicle not found", "danger")
        return redirect(url_for('vehicle_maintenance'))

    if request.method == 'POST':
        service = request.form.to_dict()
        service['id'] = service_counter
        service['vehicle_id'] = vehicle_id
        service['service_date'] = datetime.strptime(service.get('service_date'), '%Y-%m-%d')
        service['next_service_due'] = datetime.strptime(service.get('next_service_due'), '%Y-%m-%d')
        service['service_cost'] = float(service.get('service_cost') or 0)
        service_records.append(service)
        service_counter += 1

        # Update vehicle's latest service info (only these columns)
        vehicle['last_service_date'] = service['service_date']
        vehicle['next_service_due'] = service['next_service_due']
        vehicle['service_type'] = service.get('service_type')
        vehicle['status'] = service.get('status')
        vehicle['parts_replaced'] = service.get('parts_replaced')
        vehicle['service_cost'] = service['service_cost']
        vehicle['notes'] = service.get('notes')
        flash("Service added successfully", "success")
        return redirect(url_for('vehicle_maintenance'))

    return render_template('add_service.html', vehicle=vehicle)

@app.route('/delete_vehicle_men/<int:vehicle_id>', methods=['POST'])
def delete_vehicle_men(vehicle_id):
    global vehicles
    vehicles = [v for v in vehicles if v['id'] != vehicle_id]
    flash("Vehicle deleted successfully", "success")
    return redirect(url_for('vehicle_maintenance'))



tyres = []
@app.route('/tyre-management', methods=['GET', 'POST'])
def tyre_management():
    if 'user' not in session:
        return redirect('/')

    if request.method == 'POST':
        # Extract form data from the POST request
        serial_number = request.form.get('serial_number')
        vehicle_id = request.form.get('vehicle_id')
        position = request.form.get('position')
        status = request.form.get('status')
        installed_on = request.form.get('installed_on')
        km_run = request.form.get('km_run')
        last_inspection = request.form.get('last_inspection')
        condition = request.form.get('condition')

        # Convert date fields from string to datetime
        installed_on = datetime.strptime(installed_on, '%Y-%m-%d')
        last_inspection = datetime.strptime(last_inspection, '%Y-%m-%d')

        # Add new tyre to the list (simulating DB insert)
        tyres.append({
            'serial_number': serial_number,
            'vehicle_id': vehicle_id,
            'position': position,
            'status': status,
            'installed_on': installed_on,
            'km_run': int(km_run),
            'last_inspection': last_inspection,
            'condition': condition
        })

        # Show success message
        flash('Tyre added successfully!', 'success')

        # Redirect to the same page to show the updated tyre list
        return redirect('/tyre-management')

    return render_template('tyre_management.html', tyres=tyres)

issues = []

@app.route('/issue-management', methods=['GET', 'POST'])
def issue_management():
    if 'user' not in session:
        return redirect('/')

    if request.method == 'POST':
        # Get form data
        title = request.form.get('title')
        vehicle_number = request.form.get('vehicle_number')
        location = request.form.get('location')
        assigned_to = request.form.get('assigned_to')

        # Add to issues list
        issues.append({
            'id': len(issues) + 1,
            'title': title,
            'vehicle_number': vehicle_number,
            'location': location,
            'status': 'Open',  # default
            'assigned_to': assigned_to,
            'created_at': datetime.now()
        })

        flash('Issue created successfully!', 'success')
        return redirect('/issue-management')

    return render_template('issue_management.html', issues=issues)


# @app.route('/assign_vehicle', methods=['POST'])
# def assign_vehicle():
#     vehicle_id = request.form['vehicle_id']
#     order_id = request.form['order_id']
#
#     conn = get_connection()
#     cur = conn.cursor()
#
#     # Update vehicle status
#     cur.execute("""
#         UPDATE vehicles
#         SET status='assigned', order_id=%s, assigned_time=%s
#         WHERE vehicle_id=%s
#     """, (order_id, datetime.now(), vehicle_id))
#
#     # Update order assignment
#     cur.execute("""
#         UPDATE orders
#         SET assigned_vehicle=%s
#         WHERE order_id=%s
#     """, (vehicle_id, order_id))
#
#     conn.commit()
#     conn.close()
#     return redirect(url_for('vehicle'))
#
# # @app.route('/add_vehicle', methods=['POST'])
# # def add_vehicle():
# #     vehicle_id = request.form['vehicle_id']
# #     location = request.form['location']
# #     capacity = int(request.form['capacity'])
# #
# #     conn = get_connection()
# #     cur = conn.cursor()
# #
# #     cur.execute("INSERT INTO vehicles (vehicle_id, location, status) VALUES (%s, %s, 'available')", (vehicle_id, location))
# #     cur.execute("INSERT INTO fleet_master (vehicle_id, capacity_kg) VALUES (%s, %s)", (vehicle_id, capacity))
# #
# #     conn.commit()
# #     conn.close()
# #
# #     return redirect(url_for('vehicle'))

# --------- ORDER MANAGEMENT -----------
@app.route('/orders', methods=['GET', 'POST'])
def orders():
    if 'user' not in session:
        return redirect('/')

    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        data = request.form
        order_id = data['order_id']

        # Check if order exists
        cur.execute("SELECT 1 FROM orders WHERE order_id = %s", (order_id,))
        exists = cur.fetchone()

        if exists:
            # Update existing order
            cur.execute("""
                UPDATE orders SET
                    customer_name = %s,
                    created_date  = %s,
                    order_type = %s,
                    pickup_location_latlon = %s,
                    drop_location_latlon = %s,
                    volume_cbm = %s,
                    weight_kg = %s,
                    delivery_priority = %s,
                    expected_delivery = %s,
                    amount = %s,
                    status = %s
                WHERE order_id = %s
            """, (
                data['customer_name'],
                data['created_date'],
                data['order_type'],
                data['pickup_location_latlon'],
                data['drop_location_latlon'],
                data['volume_cbm'],
                data['weight_kg'],
                data['delivery_priority'],
                data['expected_delivery'],
                data['amount'],
                data['status'],
                order_id
            ))
        else:
            # Insert new order
            cur.execute("""
                INSERT INTO orders (
                    order_id, customer_name, created_date, order_type, pickup_location_latlon,
                    drop_location_latlon, volume_cbm, weight_kg,
                    delivery_priority, expected_delivery, amount, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                data['order_id'],
                data['customer_name'],
                data['created_date'],
                data['order_type'],
                data['pickup_location_latlon'],
                data['drop_location_latlon'],
                data['volume_cbm'],
                data['weight_kg'],
                data['delivery_priority'],
                data['expected_delivery'],
                data['amount'],
                data['status']
            ))

        conn.commit()

    # Fetch all orders
    cur.execute("SELECT * FROM orders ORDER BY expected_delivery")
    rows = cur.fetchall()
    colnames = [desc[0] for desc in cur.description]
    data = [dict(zip(colnames, row)) for row in rows]

    cur.close()
    conn.close()

    return render_template('orders.html', data=data)


@app.route('/delete_order/<order_id>', methods=['POST'])
def delete_order(order_id):
    if 'user' not in session:
        return redirect('/')

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM orders WHERE order_id = %s", (order_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print("Error deleting order:", e)
    finally:
        cur.close()
        conn.close()

    return redirect('/orders')
@app.route('/upload_orders', methods=['POST'])
def upload_orders():
    if 'user' not in session:
        return redirect('/')

    file = request.files['orders_file']
    if file and file.filename.endswith('.csv'):
        import pandas as pd
        df = pd.read_csv(file)
        conn = get_db_connection()
        cur = conn.cursor()

        for _, row in df.iterrows():
            cur.execute("""
                INSERT INTO orders (
                    order_id, customer_name, created_date, order_type, pickup_location_latlon,
                    drop_location_latlon, volume_cbm, weight_kg,
                    delivery_priority, expected_delivery, amount, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (order_id) DO UPDATE SET
                    customer_name = EXCLUDED.customer_name,
                    created_date = EXCLUDED.created_date,
                    order_type = EXCLUDED.order_type,
                    pickup_location_latlon = EXCLUDED.pickup_location_latlon,
                    drop_location_latlon = EXCLUDED.drop_location_latlon,
                    volume_cbm = EXCLUDED.volume_cbm,
                    weight_kg = EXCLUDED.weight_kg,
                    delivery_priority = EXCLUDED.delivery_priority,
                    expected_delivery = EXCLUDED.expected_delivery,
                    amount = EXCLUDED.amount,
                    status = EXCLUDED.status
            """, (
                row['Order_ID'], row['Customer_Name'], row['created_date'], row['Order_Type'],
                row['Pickup_Location_LatLon'], row['Drop_Location_LatLon'],
                row['Volume_CBM'], row['Weight_KG'],
                row['Delivery_Priority'], row['Expected_Delivery'], row['amount'],
                row['Status']
            ))

        conn.commit()
        cur.close()
        conn.close()

    return redirect('/orders')

# ---------------- EDIT (Pre-fill Form) ----------------
@app.route('/edit_order/<order_id>')
def edit_order(order_id):
    if 'user' not in session:
        return redirect('/')

    order = next((o for o in orders_data if o['Order_ID'] == order_id), None)
    if not order:
        return redirect('/orders')
    return render_template('orders.html', data=orders_data, edit_order=order)


city_coords = {
    "Delhi": (28.6139, 77.2090),
    "Noida": (28.5355, 77.3910),
    "Pune": (18.5204, 73.8567),
    "Mumbai": (19.0760, 72.8777),
    "Gujarat": (22.2587, 71.1924),
    "Lucknow": (26.8467, 80.9462),
    "Varanasi": (25.3176, 82.9739),
    "Gurgaon": (28.4595, 77.0266)
}


# --------- ROUTE OPTIMIZATION (OR-Tools) -----------


@app.route('/optimize', methods=['GET'])
def optimize():
    if 'user' not in session:
        return redirect('/')

    conn = get_db_connection()

    fleet_df = pd.read_sql('SELECT * FROM fleet', conn)
    order_df = pd.read_sql("SELECT * FROM orders WHERE status='Pending'", conn)
    driver_df = pd.read_sql('SELECT * FROM driver_master', conn)
    conn.close()

    # City Coordinates (example)
    city_coords = {
        "Delhi": (28.6139, 77.2090),
        "Noida": (28.5355, 77.3910),
        "Pune": (18.5204, 73.8567),
        "Mumbai": (19.0760, 72.8777),
        "Gujarat": (22.2587, 71.1924),
        "Lucknow": (26.8467, 80.9462),
        "Varanasi": (25.3176, 82.9739),
        "Gurgaon": (28.4595, 77.0266)
    }

    def geocode_address(addr):
        return city_coords.get(str(addr).strip().title(), (0.0, 0.0))

    # Add latlon to orders
    order_df['pickup_latlon'] = order_df['pickup_location_latlon'].apply(geocode_address)
    order_df['drop_latlon'] = order_df['drop_location_latlon'].apply(geocode_address)

    # Add latlon to fleet (driver's current location)
    fleet_df['Current_Location_LatLon'] = fleet_df['driver_id'].map(
        lambda did: geocode_address(driver_df[driver_df['driver_id'] == did]['address'].values[0])
        if did in driver_df['driver_id'].values else (0.0, 0.0)
    )
    fleet_df['Current_Lat'] = fleet_df['Current_Location_LatLon'].apply(lambda x: x[0])
    fleet_df['Current_Lon'] = fleet_df['Current_Location_LatLon'].apply(lambda x: x[1])

    # Prepare locations for routing
    fleet_locations = list(zip(fleet_df['Current_Lat'], fleet_df['Current_Lon']))
    drop_locations = list(order_df['drop_latlon'])
    locations = fleet_locations + drop_locations

    # Compute distance matrix (meters)
    def compute_distance_matrix(locations):
        distances = {}
        for i, from_loc in enumerate(locations):
            distances[i] = {}
            for j, to_loc in enumerate(locations):
                if i == j:
                    distances[i][j] = 0
                else:
                    distances[i][j] = int(geodesic(from_loc, to_loc).km * 1000)
        return distances

    distance_matrix = compute_distance_matrix(locations)

    num_vehicles = len(fleet_df)
    vehicle_capacities_weight = fleet_df['capacity_weight_kg'].astype(int).tolist()
    vehicle_capacities_volume = fleet_df['capacity_vol_cbm'].astype(int).tolist()

    demands_weight = [0] * num_vehicles + order_df['weight_kg'].astype(int).tolist()
    demands_volume = [0] * num_vehicles + order_df['volume_cbm'].astype(int).tolist()

    starts = list(range(num_vehicles))
    ends = list(range(num_vehicles))

    manager = pywrapcp.RoutingIndexManager(len(locations), num_vehicles, starts, ends)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        return distance_matrix[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    demand_weight_callback_index = routing.RegisterUnaryTransitCallback(
        lambda from_index: demands_weight[manager.IndexToNode(from_index)]
    )
    routing.AddDimensionWithVehicleCapacity(demand_weight_callback_index, 0, vehicle_capacities_weight, True, 'Weight')

    demand_volume_callback_index = routing.RegisterUnaryTransitCallback(
        lambda from_index: demands_volume[manager.IndexToNode(from_index)]
    )
    routing.AddDimensionWithVehicleCapacity(demand_volume_callback_index, 0, vehicle_capacities_volume, True, 'Volume')

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC

    solution = routing.SolveWithParameters(search_parameters)
    routes_info = []

    # --- AI-inspired helper functions ---

    def estimate_travel_time_km(distance_km):
        """
        Estimate travel time in hours with traffic and vehicle factors
        """
        base_speed_kmh = 40  # base average speed
        traffic_factor = 1.2  # 20% more time due to traffic
        vehicle_factor = 1.1  # 10% extra for vehicle condition/load

        travel_time = distance_km / base_speed_kmh  # base hours
        adjusted_time = travel_time * traffic_factor * vehicle_factor
        return adjusted_time

    def calculate_rest_time(distance_km):
        """
        For every 100 km, assume 15 min rest time
        """
        rest_periods = distance_km // 100
        rest_minutes = rest_periods * 15
        return rest_minutes / 60  # convert to hours

    def estimate_fuel_consumption(distance_km, vehicle_fuel_efficiency_l_per_km=0.2):
        """
        Estimate fuel consumption in liters, default 0.2 L/km (5 km per liter)
        """
        return distance_km * vehicle_fuel_efficiency_l_per_km

    def calculate_delivery_window(distance_km):
        """
        Calculate suggested delivery window based on now + estimated time + rest
        """
        now = datetime.now()
        travel_hours = estimate_travel_time_km(distance_km)
        rest_hours = calculate_rest_time(distance_km)
        total_hours = travel_hours + rest_hours

        start_time = now
        end_time = now + timedelta(hours=total_hours)

        return start_time.strftime('%I:%M %p'), end_time.strftime('%I:%M %p'), total_hours

    if solution:
        for vehicle_id in range(num_vehicles):
            index = routing.Start(vehicle_id)
            route = []
            while not routing.IsEnd(index):
                node_index = manager.IndexToNode(index)
                route.append(node_index)
                index = solution.Value(routing.NextVar(index))
            route.append(manager.IndexToNode(index))

            route_locations = [locations[i] for i in route]
            assigned_orders = [order_df.iloc[i - num_vehicles]['order_id'] for i in route if i >= num_vehicles]

            m = folium.Map(location=route_locations[0], zoom_start=6)
            Fullscreen().add_to(m)

            folium.Marker(route_locations[0],
                          popup=f"Start: {fleet_df.iloc[vehicle_id]['vehicle_id']}",
                          icon=folium.Icon(color='green')).add_to(m)

            for loc, oid in zip(route_locations[1:], assigned_orders):
                folium.Marker(loc, popup=f"Drop: Order {oid}", icon=folium.Icon(color='blue')).add_to(m)

            folium.PolyLine(locations=route_locations, color='blue', weight=3).add_to(m)

            total_distance = sum(
                geodesic(route_locations[i], route_locations[i + 1]).km
                for i in range(len(route_locations) - 1)
            )

            # AI-logic: delivery window & fuel consumption
            window_start, window_end, total_time_hrs = calculate_delivery_window(total_distance)
            fuel_consumed = estimate_fuel_consumption(total_distance,
                                                      fleet_df.iloc[vehicle_id]['fuel_efficiency_l_per_km']
                                                      if 'fuel_efficiency_l_per_km' in fleet_df.columns else 0.2)

            vehicle_id_str = fleet_df.iloc[vehicle_id]['vehicle_id']
            driver_name = "N/A"
            driver_row = driver_df[driver_df['driver_id'] == fleet_df.iloc[vehicle_id]['driver_id']]
            if not driver_row.empty:
                driver_name = driver_row.iloc[0]['driver_name']

            route_id = uuid.uuid4().hex[:8]
            map_path = f"static/maps/{route_id}.html"
            m.save(map_path)

            routes_info.append({
                'vehicle': vehicle_id_str,
                'driver': driver_name,
                'orders': assigned_orders,
                'distance_km': round(total_distance, 2),
                'map_url': map_path,
                'suggested_delivery_window': f"{window_start} – {window_end}",
                'estimated_travel_time_hrs': round(total_time_hrs, 2),
                'estimated_fuel_liters': round(fuel_consumed, 2),
            })
    else:
        return "⚠️ No optimized route found. Please check locations, capacities, and demands."

    return render_template('route_optimize.html', routes=routes_info)


@app.route('/save_manual_route', methods=['POST'])
def save_manual_route():
    data = request.get_json()

    vehicle = data.get('vehicle')
    driver = data.get('driver')
    orders = data.get('orders')

    # Optional: Check if a route already exists for this driver or vehicle
    existing = Route.query.filter_by(vehicle=vehicle, driver=driver).first()
    if existing:
        existing.orders = orders
    else:
        new_route = Route(vehicle=vehicle, driver=driver, orders=orders)
        db.session.add(new_route)

    db.session.commit()

    return jsonify({"status": "success", "message": "Route saved"})



# --------- TRIP HISTORY -----------
# @app.route('/trip-history', methods=['GET'])
# def trip_history():
#     if 'user' not in session:
#         return redirect('/')
#
#     conn = get_db_connection()
#
#     fleet_df = pd.read_sql('SELECT * FROM fleet', conn)
#     orders_df = pd.read_sql("SELECT * FROM orders WHERE status='Delivered'", conn)
#     drivers_df = pd.read_sql('SELECT * FROM driver_master', conn)
#     conn.close()
#
#     # Normalize vehicle id column for matching
#     fleet_df['vehicle_id_clean'] = fleet_df['vehicle_id'].str.strip().str.lower()
#     drivers_df['driver_id'] = drivers_df['driver_id'].astype(str)
#     fleet_df['driver_id'] = fleet_df['driver_id'].astype(str)
#
#     # Merge fleet and drivers to get driver names
#     fleet_merged = fleet_df.merge(drivers_df[['driver_id', 'driver_name']], on='driver_id', how='left')
#
#     # Create lookup dict by vehicle_id_clean
#     vehicle_lookup = fleet_merged.set_index('vehicle_id_clean').to_dict('index')
#
#     # City coordinates for geocoding
#     city_coords = {
#         "Delhi": (28.6139, 77.2090),
#         "Noida": (28.5355, 77.3910),
#         "Pune": (18.5204, 73.8567),
#         "Mumbai": (19.0760, 72.8777),
#         "Gujarat": (22.2587, 71.1924),
#         "Lucknow": (26.8467, 80.9462),
#         "Varanasi": (25.3176, 82.9739),
#         "Gurgaon": (28.4595, 77.0266)
#     }
#
#     def get_coords(city):
#         return city_coords.get(str(city).strip().title(), (0.0, 0.0))
#
#     trip_data = []
#
#     for _, order in orders_df.iterrows():
#         veh_id_raw = str(order.get('assigned_vehicle_id') or order.get('vehicle_id') or '').strip().lower()
#         vehicle_info = vehicle_lookup.get(veh_id_raw, {})
#
#         driver_name = vehicle_info.get('driver_name', 'N/A')
#         vehicle_id = order.get('assigned_vehicle_id') or order.get('vehicle_id') or 'N/A'
#
#         pickup_city = order.get('pickup_location_latlon') or ''
#         drop_city = order.get('drop_location_latlon') or ''
#         pickup_coords = get_coords(pickup_city)
#         drop_coords = get_coords(drop_city)
#
#         # Calculate distance km
#         distance_km = round(geodesic(pickup_coords, drop_coords).km, 2)
#
#         # Expected avg km/L (from fleet)
#         avg_expected = vehicle_info.get('expected_avg', 12)
#         if not avg_expected or avg_expected <= 0:
#             avg_expected = 12
#
#         fuel_used_l = round(distance_km / avg_expected, 2) if avg_expected > 0 else 0
#
#         # Assume fixed fuel cost per liter
#         fuel_cost = round(fuel_used_l * 100, 2)
#
#         # Actual average km/L (dummy calc, if available use real data)
#         avg_actual = round(distance_km / fuel_used_l, 2) if fuel_used_l > 0 else 0
#
#         # Service suggestion
#         service_suggestion = "Yes" if avg_actual < avg_expected else "No"
#
#         amount = float(order.get('amount') or 0)
#         profit = round(amount - fuel_cost, 2)
#
#         # Dates
#         date = order.get('created_date')
#         if isinstance(date, pd.Timestamp):
#             date = date.strftime('%Y-%m-%d')
#
#         trip_data.append({
#             'vehicle_id': vehicle_id,
#             'driver_name': driver_name,
#             'date': date,
#             'pickup': pickup_city,
#             'drop': drop_city,
#             'distance_km': distance_km,
#             'fuel_used_l': fuel_used_l,
#             'fuel_cost': fuel_cost,
#             'avg_expected': avg_expected,
#             'avg_actual': avg_actual,
#             'service_suggestion': service_suggestion,
#             'amount': amount,
#             'profit': profit
#         })
#
#     return render_template('trip_history.html', data=trip_data)


# Mock city coords for geocoding addresses
city_coords = {
    "Delhi": (28.6139, 77.2090),
    "Noida": (28.5355, 77.3910),
    "Pune": (18.5204, 73.8567),
    "Mumbai": (19.0760, 72.8777),
    "Gujarat": (22.2587, 71.1924),
    "Lucknow": (26.8467, 80.9462),
    "Varanasi": (25.3176, 82.9739),
    "Gurgaon": (28.4595, 77.0266)
}

def geocode_address(addr):
    if not addr:
        return (0.0, 0.0)
    addr = str(addr).strip().title()
    return city_coords.get(addr, (0.0, 0.0))

def get_coords(addr):
    # Return lat, lon tuple from address string (for orders pickup/drop)
    return geocode_address(addr)

def get_optimized_routes():
    conn = get_db_connection()
    fleet_df = pd.read_sql('SELECT * FROM fleet', conn)
    order_df = pd.read_sql("SELECT * FROM orders WHERE status='Pending'", conn)
    drivers_df = pd.read_sql('SELECT * FROM driver_master', conn)
    conn.close()

    # Add current driver location lat/lon in fleet_df
    def get_driver_addr(driver_id):
        row = drivers_df[drivers_df['driver_id'] == driver_id]
        if not row.empty:
            return row.iloc[0]['address']
        return None

    fleet_df['driver_address'] = fleet_df['driver_id'].map(get_driver_addr)
    fleet_df['Current_LatLon'] = fleet_df['driver_address'].map(geocode_address)
    fleet_df['Current_Lat'] = fleet_df['Current_LatLon'].apply(lambda x: x[0])
    fleet_df['Current_Lon'] = fleet_df['Current_LatLon'].apply(lambda x: x[1])

    # Location lists: fleet driver starts + order drop locations
    fleet_locations = list(zip(fleet_df['Current_Lat'], fleet_df['Current_Lon']))
    order_df['pickup_latlon'] = order_df['pickup_location_latlon'].map(geocode_address)
    order_df['drop_latlon'] = order_df['drop_location_latlon'].map(geocode_address)
    drop_locations = list(order_df['drop_latlon'])
    locations = fleet_locations + drop_locations

    def compute_distance_matrix(locations):
        distances = {}
        for i, from_loc in enumerate(locations):
            distances[i] = {}
            for j, to_loc in enumerate(locations):
                if i == j:
                    distances[i][j] = 0
                else:
                    distances[i][j] = int(geodesic(from_loc, to_loc).km * 1000)
        return distances

    distance_matrix = compute_distance_matrix(locations)

    num_vehicles = len(fleet_df)
    vehicle_cap_weight = fleet_df['capacity_weight_kg'].astype(int).tolist()
    vehicle_cap_volume = fleet_df['capacity_vol_cbm'].astype(int).tolist()

    demands_weight = [0]*num_vehicles + order_df['weight_kg'].astype(int).tolist()
    demands_volume = [0]*num_vehicles + order_df['volume_cbm'].astype(int).tolist()

    starts = list(range(num_vehicles))
    ends = list(range(num_vehicles))

    manager = pywrapcp.RoutingIndexManager(len(locations), num_vehicles, starts, ends)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        return distance_matrix[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    demand_weight_callback_index = routing.RegisterUnaryTransitCallback(
        lambda from_index: demands_weight[manager.IndexToNode(from_index)]
    )
    routing.AddDimensionWithVehicleCapacity(demand_weight_callback_index, 0, vehicle_cap_weight, True, 'Weight')

    demand_volume_callback_index = routing.RegisterUnaryTransitCallback(
        lambda from_index: demands_volume[manager.IndexToNode(from_index)]
    )
    routing.AddDimensionWithVehicleCapacity(demand_volume_callback_index, 0, vehicle_cap_volume, True, 'Volume')

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC

    solution = routing.SolveWithParameters(search_parameters)
    if not solution:
        return []

    # Helper functions
    def estimate_travel_time_km(distance_km):
        return distance_km / 40 * 1.2 * 1.1  # speed and factors

    def calculate_rest_time(distance_km):
        return (distance_km // 100) * 0.25  # 15 mins in hours

    def estimate_fuel_consumption(distance_km, fuel_efficiency=0.2):
        return distance_km * fuel_efficiency

    def calculate_delivery_window(distance_km):
        now = datetime.now()
        travel_hrs = estimate_travel_time_km(distance_km)
        rest_hrs = calculate_rest_time(distance_km)
        total_hrs = travel_hrs + rest_hrs
        return now.strftime('%I:%M %p'), (now + timedelta(hours=total_hrs)).strftime('%I:%M %p'), total_hrs

    routes_info = []

    for vehicle_id in range(num_vehicles):
        index = routing.Start(vehicle_id)
        route = []
        while not routing.IsEnd(index):
            route.append(manager.IndexToNode(index))
            index = solution.Value(routing.NextVar(index))
        route.append(manager.IndexToNode(index))

        assigned_orders_idx = [i for i in route if i >= num_vehicles]
        assigned_orders = order_df.iloc[
            [i - num_vehicles for i in assigned_orders_idx]] if assigned_orders_idx else pd.DataFrame()

        total_distance = 0
        for i in range(len(route) - 1):
            total_distance += geodesic(locations[route[i]], locations[route[i + 1]]).km
        total_distance = round(total_distance, 2)

        window_start, window_end, total_time_hrs = calculate_delivery_window(total_distance)

        fuel_efficiency = fleet_df.loc[
            vehicle_id, 'fuel_efficiency_l_per_km'] if 'fuel_efficiency_l_per_km' in fleet_df.columns else 0.2
        fuel_consumed = round(estimate_fuel_consumption(total_distance, fuel_efficiency), 2)

        vehicle_id_str = fleet_df.loc[vehicle_id, 'vehicle_id']
        driver_row = drivers_df[drivers_df['driver_id'] == fleet_df.loc[vehicle_id, 'driver_id']]
        driver_name = driver_row.iloc[0]['driver_name'] if not driver_row.empty else "N/A"

        route_coords = [locations[i] for i in route]  # ✅ Get coordinates for map polyline

        # Assigned orders route detail rows
        for _, order in assigned_orders.iterrows():
            dist_km = round(
                geodesic(get_coords(order['pickup_location_latlon']), get_coords(order['drop_location_latlon'])).km, 2)
            expected_avg = fleet_df.loc[vehicle_id, 'expected_avg'] if 'expected_avg' in fleet_df.columns else 12
            fuel_used_l = round(dist_km / expected_avg, 2) if expected_avg > 0 else 0
            fuel_cost = round(fuel_used_l * 100, 2)  # Assume fuel cost = ₹100 per liter
            actual_avg = round(dist_km / fuel_used_l, 2) if fuel_used_l > 0 else 0
            service_suggestion = "Yes" if actual_avg < expected_avg else "No"
            amount = order.get('amount', 0)
            profit = round(amount - fuel_cost, 2)
            date = order.get('created_date')
            if isinstance(date, pd.Timestamp):
                date = date.strftime('%Y-%m-%d')

            routes_info.append({
                'vehicle_id': vehicle_id_str,
                'driver_name': driver_name,
                'date': date or '',
                'pickup': order['pickup_location_latlon'],
                'drop': order['drop_location_latlon'],
                'distance_km': dist_km,
                'fuel_used_l': fuel_used_l,
                'fuel_cost': fuel_cost,
                'avg_expected': expected_avg,
                'avg_actual': actual_avg,
                'service_suggestion': service_suggestion,
                'amount': amount,
                'profit': profit,
                'total_distance': total_distance,
                'estimated_travel_time_hrs': round(total_time_hrs, 2),
                'estimated_fuel_liters': fuel_consumed,
                'delivery_window': f"{window_start} – {window_end}",
                'orders': order['order_id'],
                'route_coords': route_coords  # ✅ Include for map rendering
            })

        # If no assigned orders, still return vehicle route
        if assigned_orders.empty:
            routes_info.append({
                'vehicle_id': vehicle_id_str,
                'driver_name': driver_name,
                'date': '',
                'pickup': '',
                'drop': '',
                'distance_km': 0,
                'fuel_used_l': 0,
                'fuel_cost': 0,
                'avg_expected': '',
                'avg_actual': '',
                'service_suggestion': '',
                'amount': 0,
                'profit': 0,
                'total_distance': total_distance,
                'estimated_travel_time_hrs': round(total_time_hrs, 2),
                'estimated_fuel_liters': fuel_consumed,
                'delivery_window': f"{window_start} – {window_end}",
                'orders': '',
                'route_coords': route_coords  # ✅ Include empty vehicle path
            })

    return routes_info

#
# @app.route('/optimize')
# def optimize():
#     routes = get_optimized_routes()
#     if not routes:
#         return "No routes found"
#
#     return render_template('route_optimize.html', routes=routes)


@app.route('/trip-history')
def trip_history():
    routes = get_optimized_routes()
    if not routes:
        return "No routes found"

    return render_template('trip_history.html', routes=routes)


@app.route('/tracking')
def tracking():
    return render_template('tracking.html')


@app.route('/financial')
def financial():
    routes = get_optimized_routes()
    if not routes:
        return render_template("financial_report.html", routes=[], summary={})

    # Grouping and Summary
    from collections import defaultdict
    summary = {
        'fuel_cost_by_vehicle': defaultdict(float),
        'profit_by_vehicle': defaultdict(float),
        'orders_by_driver': defaultdict(int),
        'unique_vehicles': set(),
        'unique_drivers': set(),
        'unique_dates': set()
    }

    for trip in routes:
        v = trip['vehicle_id']
        d = trip['driver_name']
        date = trip['date']

        summary['fuel_cost_by_vehicle'][v] += trip['fuel_cost']
        summary['profit_by_vehicle'][v] += trip['profit']
        if trip['orders']:
            summary['orders_by_driver'][d] += 1

        summary['unique_vehicles'].add(v)
        summary['unique_drivers'].add(d)
        if date:
            summary['unique_dates'].add(date)

    # Convert sets to sorted lists
    summary['unique_vehicles'] = sorted(summary['unique_vehicles'])
    summary['unique_drivers'] = sorted(summary['unique_drivers'])
    summary['unique_dates'] = sorted(summary['unique_dates'])

    return render_template("financial_dashboard.html", routes=routes, summary=summary)



# --------- REPORTS -----------
@app.route('/download_report')
def download_report():
    path = os.path.join(DATA_PATH, 'trip_logs.csv')
    return send_file(path, as_attachment=True)


if __name__ == '__main__':
    # os.makedirs(DATA_PATH, exist_ok=True)
    # os.makedirs('static/maps', exist_ok=True)
    app.run(debug=True)
