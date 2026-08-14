from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Bus(db.Model):
    __tablename__ = "buses"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    route = db.Column(db.String(200), nullable=False)

    # SEATER / SLEEPER / SEATER_SLEEPER
    bus_type = db.Column(
        db.String(20),
        nullable=False,
        default="SEATER"
    )

    num_rows = db.Column(
        db.Integer,
        nullable=False,
        default=10
    )

    lower_reserved_pairs = db.Column(
    db.Integer,
    nullable=False,
    default=0
    )

    upper_reserved_pairs = db.Column(
        db.Integer,
        nullable=False,
        default=0
    )

    # Separate fares
    seater_fare = db.Column(
        db.Integer,
        nullable=False,
        default=300
    )

    sleeper_fare = db.Column(
        db.Integer,
        nullable=False,
        default=500
    )

    departure_time = db.Column(
        db.String(50),
        nullable=False
    )

    seats = db.relationship(
        "SeatRow",
        backref="bus",
        cascade="all, delete-orphan"
    )


class SeatRow(db.Model):
    """DB-persisted seat."""

    __tablename__ = "seats"

    id = db.Column(db.Integer, primary_key=True)

    bus_id = db.Column(
        db.Integer,
        db.ForeignKey("buses.id"),
        nullable=False
    )

    row = db.Column(
        db.Integer,
        nullable=False
    )

    col = db.Column(
        db.String(1),
        nullable=False
    )

    pair_id = db.Column(
        db.Integer,
        nullable=True
    )

    aisle_after = db.Column(
        db.Boolean,
        default=False
    )

    deck = db.Column(
        db.String(40),
        nullable=True
    )

    reserved_female = db.Column(
        db.Boolean,
        default=False
    )

    status = db.Column(
        db.String(10),
        nullable=False,
        default="FREE"
    )

    gender = db.Column(
        db.String(1),
        nullable=True
    )

    group_id = db.Column(
        db.Integer,
        nullable=True
    )

    passenger_name = db.Column(
        db.String(120),
        nullable=True
    )

    passenger_phone = db.Column(
        db.String(20),
        nullable=True
    )


class BookingLog(db.Model):
    """Audit trail."""

    __tablename__ = "booking_logs"

    id = db.Column(db.Integer, primary_key=True)

    bus_id = db.Column(
        db.Integer,
        nullable=False
    )

    seat_id = db.Column(
        db.Integer,
        nullable=False
    )

    passenger_name = db.Column(
        db.String(120),
        nullable=False
    )

    gender = db.Column(
        db.String(1),
        nullable=False
    )

    group_id = db.Column(
        db.Integer,
        nullable=True
    )

    used_reserved = db.Column(
        db.Boolean,
        default=False
    )

    fare = db.Column(
        db.Integer,
        default=0
    )

    action = db.Column(
        db.String(20),
        nullable=False
    )

    booking_ref = db.Column(
        db.String(20),
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )