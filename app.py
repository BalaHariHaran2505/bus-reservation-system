import os
import re
import secrets
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_wtf import CSRFProtect
from dotenv import load_dotenv

from models import db, Bus, SeatRow, BookingLog
import seat_allocator as sa


load_dotenv()

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    secrets.token_hex(32)
)

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL",
    "sqlite:///bus_reservation.db"
)

# To use MySQL instead, set DATABASE_URL in .env to e.g.:
# mysql+pymysql://user:password@localhost/bus_reservation

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

csrf = CSRFProtect(app)

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "changeme123"
)

PHONE_RE = re.compile(r"^\d{10}$")


# ---------------- helpers ----------------

def row_to_seat(row: SeatRow) -> sa.Seat:
    return sa.Seat(
        id=row.id,
        row=row.row,
        col=row.col,
        pair_id=row.pair_id,
        aisle_after=row.aisle_after,
        deck=row.deck,
        reserved_female=row.reserved_female,
        status=sa.SeatStatus(row.status),
        gender=sa.Gender(row.gender) if row.gender else None,
        group_id=row.group_id,
        passenger_name=row.passenger_name,
    )


def bus_seats_as_sa(bus_id):
    rows = (
        SeatRow.query
        .filter_by(bus_id=bus_id)
        .order_by(SeatRow.row, SeatRow.col)
        .all()
    )

    return rows, [row_to_seat(r) for r in rows]


def apply_seat_to_row(seat: sa.Seat, row: SeatRow):
    row.status = seat.status.value
    row.gender = seat.gender.value if seat.gender else None
    row.group_id = seat.group_id
    row.passenger_name = seat.passenger_name


def get_seat_fare(bus, seat):
    """
    Return the correct fare based on the bus type
    and the deck of the selected seat.
    """

    # Normal seater bus
    if bus.bus_type == "SEATER":
        return bus.seater_fare

    # Normal sleeper bus
    if bus.bus_type == "SLEEPER":
        return bus.sleeper_fare

    # Mixed Seater + Sleeper bus
    if bus.bus_type == "SEATER_SLEEPER":

        # Sleeper seats are on the upper deck
        if seat.deck and "Sleeper" in seat.deck:
            return bus.sleeper_fare

        # Seater seats are on the lower deck
        return bus.seater_fare

    # Safety fallback
    return bus.seater_fare


def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not session.get("is_admin"):
            flash("Admin login required.", "error")
            return redirect(url_for("admin_login"))

        return f(*a, **kw)

    return wrapper


def validate_passenger_input(name, phone, gender):
    errors = []

    name = (name or "").strip()

    if not (2 <= len(name) <= 80):
        errors.append(
            "Name must be between 2 and 80 characters."
        )

    if not re.match(r"^[A-Za-z .'-]+$", name):
        errors.append(
            "Name contains invalid characters."
        )

    if not PHONE_RE.match((phone or "").strip()):
        errors.append(
            "Phone number must be exactly 10 digits."
        )

    if gender not in ("F", "M"):
        errors.append(
            "Gender must be selected."
        )

    return errors


# ---------------- public routes ----------------

@app.route("/")
def index():
    buses = Bus.query.all()

    return render_template(
        "index.html",
        buses=buses
    )


@app.route("/bus/<int:bus_id>")
def bus_detail(bus_id):
    bus = Bus.query.get_or_404(bus_id)

    rows, _ = bus_seats_as_sa(bus_id)

    return render_template(
        "bus.html",
        bus=bus,
        seats=rows
    )


@app.route("/bus/<int:bus_id>/book", methods=["POST"])
def book_seat(bus_id):

    bus = Bus.query.get_or_404(bus_id)

    name = request.form.get("name")
    phone = request.form.get("phone")
    gender = request.form.get("gender")

    mode = request.form.get(
        "mode",
        "auto"
    )

    seat_id = request.form.get(
        "seat_id",
        type=int
    )

    group_size = request.form.get(
        "group_size",
        type=int
    ) or 1

    errors = validate_passenger_input(
        name,
        phone,
        gender
    )

    if errors:

        for e in errors:
            flash(e, "error")

        return redirect(
            url_for(
                "bus_detail",
                bus_id=bus_id
            )
        )

    rows, seats = bus_seats_as_sa(bus_id)

    group_id = None

    if group_size > 1:
        group_id = secrets.randbelow(
            10**9
        )

    try:

        if mode == "manual":

            if seat_id is None:

                flash(
                    "No seat selected.",
                    "error"
                )

                return redirect(
                    url_for(
                        "bus_detail",
                        bus_id=bus_id
                    )
                )

            chosen_seat = sa.manual_assign(
                seats,
                seat_id=seat_id,
                gender=gender
            )

            chosen = [chosen_seat]

        else:

            result = sa.auto_assign(
                seats,
                gender=gender,
                group_size=group_size,
                group_id=group_id
            )

            chosen = result["seats"]

    except sa.ReservedSeatError as e:

        flash(
            str(e),
            "error"
        )

        return redirect(
            url_for(
                "bus_detail",
                bus_id=bus_id
            )
        )

    except sa.NoSeatAvailableError as e:

        flash(
            str(e),
            "error"
        )

        return redirect(
            url_for(
                "bus_detail",
                bus_id=bus_id
            )
        )

    except sa.InvalidBookingInput as e:

        flash(
            str(e),
            "error"
        )

        return redirect(
            url_for(
                "bus_detail",
                bus_id=bus_id
            )
        )

    # ------------------------------------------------
    # Commit booking(s) and build bill
    # ------------------------------------------------

    booking_ref = (
        f"BK{secrets.randbelow(10**8):08d}"
    )

    bill_items = []

    for seat in chosen:

        # Update seat status
        sa.commit_booking(
            seat,
            gender,
            group_id,
            name
        )

        # Find corresponding DB row
        db_row = next(
            r for r in rows
            if r.id == seat.id
        )

        apply_seat_to_row(
            seat,
            db_row
        )

        db_row.passenger_phone = phone

        # IMPORTANT:
        # Get fare based on the selected seat/deck
        seat_fare = get_seat_fare(
            bus,
            seat
        )

        # Save booking log
        db.session.add(
            BookingLog(
                bus_id=bus_id,
                seat_id=seat.id,
                passenger_name=name,
                gender=gender,
                group_id=group_id,
                used_reserved=seat.reserved_female,
                fare=seat_fare,
                action="BOOK",
                booking_ref=booking_ref,
            )
        )

        # Add to receipt
        bill_items.append(
            {
                "seat_label": f"{seat.row}{seat.col}",
                "reserved": seat.reserved_female,
                "fare": seat_fare,
            }
        )

    db.session.commit()

    total = sum(
        item["fare"]
        for item in bill_items
    )

    return render_template(
        "receipt.html",
        bus=bus,
        items=bill_items,
        total=total,
        booking_ref=booking_ref,
        passenger_name=name,
        gender=gender,
    )


@app.route(
    "/bus/<int:bus_id>/cancel/<int:seat_id>",
    methods=["POST"]
)
def cancel_seat(bus_id, seat_id):

    row = (
        SeatRow.query
        .filter_by(
            id=seat_id,
            bus_id=bus_id
        )
        .first_or_404()
    )

    if row.status != "BOOKED":

        flash(
            "Seat is not booked.",
            "error"
        )

        return redirect(
            url_for(
                "bus_detail",
                bus_id=bus_id
            )
        )

    db.session.add(
        BookingLog(
            bus_id=bus_id,
            seat_id=seat_id,
            passenger_name=row.passenger_name or "",
            gender=row.gender or "M",
            group_id=row.group_id,
            used_reserved=row.reserved_female,
            fare=0,
            action="CANCEL",
        )
    )

    row.status = "FREE"
    row.gender = None
    row.group_id = None
    row.passenger_name = None
    row.passenger_phone = None

    db.session.commit()

    flash(
        "Booking cancelled.",
        "success"
    )

    return redirect(
        url_for(
            "bus_detail",
            bus_id=bus_id
        )
    )


# ---------------- admin ----------------

@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():

    if request.method == "POST":

        if request.form.get("password") == ADMIN_PASSWORD:

            session["is_admin"] = True

            return redirect(
                url_for(
                    "admin_dashboard"
                )
            )

        flash(
            "Incorrect password.",
            "error"
        )

    return render_template(
        "admin_login.html"
    )


@app.route("/admin/logout")
def admin_logout():

    session.pop(
        "is_admin",
        None
    )

    return redirect(
        url_for("index")
    )


@app.route(
    "/admin/bus/add",
    methods=["POST"]
)
@login_required
def add_bus():

    name = request.form.get(
        "name",
        ""
    ).strip()

    route = request.form.get(
        "route",
        ""
    ).strip()

    bus_type = request.form.get(
        "bus_type",
        "SEATER"
    )

    try:

        num_rows = int(
            request.form.get(
                "num_rows",
                10
            )
        )

        seater_fare = int(
            request.form.get(
                "seater_fare",
                300
            )
        )

        sleeper_fare = int(
            request.form.get(
                "sleeper_fare",
                500
            )
        )

        lower_reserved_pairs = int(
            request.form.get(
                "lower_reserved_pairs",
                0
            )
        )

        upper_reserved_pairs = int(
            request.form.get(
                "upper_reserved_pairs",
                0
            )
        )

    except ValueError:

        flash(
            "Please enter valid numbers.",
            "error"
        )

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    departure_time = request.form.get(
        "departure_time",
        ""
    ).strip()

    if not name or not route or not departure_time:

        flash(
            "Bus name, route and departure time are required.",
            "error"
        )

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    if bus_type not in (
        "SEATER",
        "SLEEPER",
        "SEATER_SLEEPER"
    ):

        flash(
            "Invalid bus type.",
            "error"
        )

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    if num_rows < 1:

        flash(
            "Number of rows must be at least 1.",
            "error"
        )

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    if seater_fare < 0 or sleeper_fare < 0:

        flash(
            "Fare cannot be negative.",
            "error"
        )

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    if lower_reserved_pairs < 0 or upper_reserved_pairs < 0:

        flash(
            "Ladies safety pairs cannot be negative.",
            "error"
        )

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    try:

        bus = Bus(
            name=name,
            route=route,
            bus_type=bus_type,
            num_rows=num_rows,
            lower_reserved_pairs=lower_reserved_pairs,
            upper_reserved_pairs=upper_reserved_pairs,
            seater_fare=seater_fare,
            sleeper_fare=sleeper_fare,
            departure_time=departure_time
        )

        db.session.add(bus)

        db.session.flush()

        layout = sa.make_bus_layout(
            num_rows=bus.num_rows,
            bus_type=bus.bus_type,
            lower_reserved_pairs=bus.lower_reserved_pairs,
            upper_reserved_pairs=bus.upper_reserved_pairs
        )

        for seat in layout:

            db.session.add(
                SeatRow(
                    bus_id=bus.id,
                    row=seat.row,
                    col=seat.col,
                    pair_id=seat.pair_id,
                    aisle_after=seat.aisle_after,
                    deck=seat.deck,
                    reserved_female=seat.reserved_female,
                    status="FREE"
                )
            )

        db.session.commit()

        flash(
            f"Bus '{bus.name}' added successfully.",
            "success"
        )

    except Exception as e:

        db.session.rollback()

        flash(
            f"Could not add bus: {e}",
            "error"
        )

    return redirect(
        url_for(
            "admin_dashboard"
        )
    )


@app.route("/admin")
@login_required
def admin_dashboard():

    buses = Bus.query.all()

    logs = (
        BookingLog.query
        .order_by(
            BookingLog.created_at.desc()
        )
        .limit(50)
        .all()
    )

    return render_template(
        "admin.html",
        buses=buses,
        logs=logs
    )


# ---------------- JSON API ----------------
# Used by tests / AI agents

@app.route(
    "/api/bus/<int:bus_id>/seats"
)
def api_bus_seats(bus_id):

    rows, _ = bus_seats_as_sa(
        bus_id
    )

    return jsonify(
        [
            {
                "id": r.id,
                "row": r.row,
                "col": r.col,
                "status": r.status,
                "gender": r.gender,
                "group_id": r.group_id,
                "reserved_female": r.reserved_female
            }
            for r in rows
        ]
    )


if __name__ == "__main__":

    with app.app_context():
        db.create_all()

    app.run(
        debug=os.environ.get(
            "FLASK_DEBUG",
            "0"
        ) == "1"
    )