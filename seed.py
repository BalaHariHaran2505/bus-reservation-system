"""Creates the DB tables and inserts sample buses + seats, covering all
three bus types (SEATER, SLEEPER, SEATER_SLEEPER) with Ladies-reserved
seat pairs.

Run once: python seed.py
"""
from app import app
from models import db, Bus, SeatRow
import seat_allocator as sa

with app.app_context():
    db.drop_all()
    db.create_all()

    buses = [
    Bus(
        name="Express 101",
        route="Trichy -> Chennai",
        bus_type="SEATER",
        num_rows=10,
        lower_reserved_pairs=2,
        upper_reserved_pairs=0,
        seater_fare=350,
        sleeper_fare=0,
        departure_time="21:30"
    ),

    Bus(
        name="Night Rider Sleeper",
        route="Trichy -> Bangalore",
        bus_type="SLEEPER",
        num_rows=12,
        lower_reserved_pairs=1,
        upper_reserved_pairs=2,
        seater_fare=0,
        sleeper_fare=800,
        departure_time="22:00"
    ),

    Bus(
        name="City Hopper 22",
        route="Trichy -> Coimbatore",
        bus_type="SEATER_SLEEPER",
        num_rows=14,
        lower_reserved_pairs=2,
        upper_reserved_pairs=2,
        seater_fare=550,
        sleeper_fare=750,
        departure_time="07:00"
    ),
    ]
    db.session.add_all(buses)
    db.session.commit()

    for bus in buses:
        layout = sa.make_bus_layout(
            num_rows=bus.num_rows,
            bus_type=bus.bus_type,
            lower_reserved_pairs=bus.lower_reserved_pairs,
            upper_reserved_pairs=bus.upper_reserved_pairs,
        )
        for seat in layout:
            db.session.add(SeatRow(
                bus_id=bus.id, row=seat.row, col=seat.col, pair_id=seat.pair_id,
                aisle_after=seat.aisle_after, deck=seat.deck,
                reserved_female=seat.reserved_female, status="FREE",
            ))
    db.session.commit()

    print(f"Seeded {len(buses)} buses (Seater, Sleeper, Seater+Sleeper).")
