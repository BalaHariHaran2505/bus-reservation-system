"""
seat_allocator.py

Core business logic for the Bus Seat Reservation "Safety Seat" feature.

DESIGN (v2 - reserved-quota model)
-----------------------------------
Earlier version tried to detect "risky" adjacency (stranger of the opposite
gender sitting next to a solo female) and block/warn on it. Real testing
showed this breaks ordinary, legitimate cases: a couple, siblings, or a
mother and son booking separately still look like "two strangers of
different genders" to that logic, so they'd get blocked for no good reason.

Redesigned around how real reserved-ladies-seat systems actually work
(e.g. reserved seats on public buses/trains):

- A bus reserves a fixed NUMBER OF SEAT PAIRS as "female only". Both seats
  in a reserved pair can only ever be booked by a female passenger.
- Every other seat on the bus ("general seating") is open to anyone,
  regardless of who is sitting next to them. No gender-adjacency checks,
  no confirmation prompts - couples, families, mixed groups can sit
  wherever there's a free general seat.
- Auto-assign: a solo female passenger is offered a reserved seat first
  (guaranteed safe option) if one is free, otherwise a general seat.
  A male passenger (or any group booking) only ever draws from general
  seating - reserved seats are never touched for them, even if general
  seating is full.
- Manual pick: anyone can manually pick any free GENERAL seat. A manual
  pick on a RESERVED seat is only allowed for a female passenger.

Layout model
------------
A bus is a grid of rows containing seats. Seats that are physically next to
each other share a `pair_id` (used only to decide which two seats form a
"reserved pair" - it does not otherwise restrict who can sit there in
general seating). A seat with `pair_id=None` has no neighbour (e.g. a single
sleeper berth).

No tracking of any kind is involved. This is pure seat-allocation logic
based on data already collected at booking time (the gender field on the
booking form). No location data, no device data, no third-party lookups.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List


class Gender(str, Enum):
    FEMALE = "F"
    MALE = "M"


class SeatStatus(str, Enum):
    FREE = "FREE"
    BOOKED = "BOOKED"


class BusType(str, Enum):
    SEATER = "SEATER"
    SLEEPER = "SLEEPER"
    SEATER_SLEEPER = "SEATER_SLEEPER"


class SeatAllocationError(Exception):
    """Base class for allocator errors."""


class InvalidBookingInput(SeatAllocationError):
    """Raised for bad input: bad gender, bad group size, unknown bus type, etc."""


class NoSeatAvailableError(SeatAllocationError):
    """Raised when there is no free seat (or no contiguous general block for a group)."""


class ReservedSeatError(SeatAllocationError):
    """Raised when a non-female passenger tries to manually book a seat
    reserved for female passengers."""

    def __init__(self, seat_id, message="This seat is reserved for female "
                                          "passengers. Please choose another seat."):
        self.seat_id = seat_id
        super().__init__(message)


@dataclass
class Seat:
    id: int
    row: int
    col: str
    pair_id: Optional[int] = None
    aisle_after: bool = False        # render an aisle gap after this seat
    deck: Optional[str] = None       # cosmetic grouping label, e.g. "Lower Deck"
    reserved_female: bool = False
    status: SeatStatus = SeatStatus.FREE
    gender: Optional[Gender] = None
    group_id: Optional[int] = None
    passenger_name: Optional[str] = None


def _validate_gender(gender):
    if gender not in (Gender.FEMALE, Gender.MALE, "F", "M"):
        raise InvalidBookingInput(f"gender must be 'F' or 'M', got {gender!r}")
    return Gender(gender)


def _free_seats(seats: List[Seat]) -> List[Seat]:
    return [s for s in seats if s.status == SeatStatus.FREE]


def _find_contiguous_block(pool: List[Seat], size: int) -> Optional[List[Seat]]:
    """Find `size` free seats in the same row, in column order, within the
    given pool of seats (used for group bookings, which only draw from
    general - non-reserved - seating)."""
    by_row = {}
    for s in pool:
        by_row.setdefault(s.row, []).append(s)

    for row_seats in by_row.values():
        row_seats = sorted(row_seats, key=lambda s: s.col)
        free_run = [s for s in row_seats if s.status == SeatStatus.FREE]
        if len(free_run) >= size:
            return free_run[:size]
    return None


def auto_assign(
    seats: List[Seat],
    gender,
    group_size: int = 1,
    group_id: Optional[int] = None,
) -> dict:
    """
    Auto-assign seat(s) for a new booking.

    Returns: {"seats": [Seat, ...], "used_reserved": bool}
    Raises: InvalidBookingInput, NoSeatAvailableError
    """
    gender = _validate_gender(gender)
    if group_size < 1:
        raise InvalidBookingInput("group_size must be >= 1")

    general_free = [s for s in seats if s.status == SeatStatus.FREE and not s.reserved_female]
    reserved_free = [s for s in seats if s.status == SeatStatus.FREE and s.reserved_female]

    if group_size > 1:
        # Groups (mixed or same gender) always use general seating - a
        # reserved ladies seat is a single-passenger safety guarantee, not
        # a group perk.
        block = _find_contiguous_block(general_free, group_size)
        if block is None:
            raise NoSeatAvailableError(
                f"No contiguous block of {group_size} general seats available"
            )
        return {"seats": block, "used_reserved": False}

    if gender == Gender.FEMALE and reserved_free:
        chosen = sorted(reserved_free, key=lambda s: (s.row, s.col))[0]
        return {"seats": [chosen], "used_reserved": True}

    if not general_free:
        raise NoSeatAvailableError("No free seats available for this passenger")

    chosen = sorted(general_free, key=lambda s: (s.row, s.col))[0]
    return {"seats": [chosen], "used_reserved": False}


def manual_assign(seats: List[Seat], seat_id: int, gender) -> Seat:
    """
    Book a specific seat chosen by the passenger.

    Raises:
        InvalidBookingInput - bad gender / unknown seat_id
        NoSeatAvailableError - seat already booked
        ReservedSeatError - seat is reserved for female passengers and this
            passenger is not female
    """
    gender = _validate_gender(gender)
    seat = next((s for s in seats if s.id == seat_id), None)
    if seat is None:
        raise InvalidBookingInput(f"No such seat_id: {seat_id}")
    if seat.status == SeatStatus.BOOKED:
        raise NoSeatAvailableError(f"Seat {seat_id} is already booked")
    if seat.reserved_female and gender != Gender.FEMALE:
        raise ReservedSeatError(seat.id)

    return seat


def commit_booking(seat: Seat, gender, group_id, passenger_name) -> None:
    gender = _validate_gender(gender)
    seat.status = SeatStatus.BOOKED
    seat.gender = gender
    seat.group_id = group_id
    seat.passenger_name = passenger_name


def cancel_booking(seat: Seat) -> None:
    seat.status = SeatStatus.FREE
    seat.gender = None
    seat.group_id = None
    seat.passenger_name = None
    # Note: reserved_female is a property of the seat itself (bus config),
    # not of the booking - it is NOT cleared on cancel.


def make_bus_layout(
    num_rows: int,
    bus_type="SEATER",
    lower_reserved_pairs: int = 0,
    upper_reserved_pairs: int = 0,
    start_id: int = 1,
) -> List[Seat]:

    """
    Generate a fresh seat layout.

    SEATER:
        Lower deck only.

    SLEEPER:
        Lower + Upper deck.

    SEATER_SLEEPER:
        Lower deck = Seater
        Upper deck = Sleeper

    Safety/Ladies pairs are configured independently
    for lower and upper decks.
    """

    if num_rows < 1:
        raise InvalidBookingInput(
            "num_rows must be at least 1"
        )

    if lower_reserved_pairs < 0:
        raise InvalidBookingInput(
            "lower_reserved_pairs cannot be negative"
        )

    if upper_reserved_pairs < 0:
        raise InvalidBookingInput(
            "upper_reserved_pairs cannot be negative"
        )

    seats: List[Seat] = []

    sid = start_id
    pair_counter = 0

    def add_seater_row(row, deck=None):
        nonlocal sid, pair_counter

        pair_a = pair_counter
        pair_counter += 1

        pair_c = pair_counter
        pair_counter += 1

        seats.extend([
            Seat(
                id=sid,
                row=row,
                col="A",
                pair_id=pair_a,
                aisle_after=False,
                deck=deck
            ),

            Seat(
                id=sid + 1,
                row=row,
                col="B",
                pair_id=pair_a,
                aisle_after=True,
                deck=deck
            ),

            Seat(
                id=sid + 2,
                row=row,
                col="C",
                pair_id=pair_c,
                aisle_after=False,
                deck=deck
            ),

            Seat(
                id=sid + 3,
                row=row,
                col="D",
                pair_id=pair_c,
                aisle_after=False,
                deck=deck
            ),
        ])

        sid += 4

    def add_sleeper_row(row, deck=None):
        nonlocal sid, pair_counter

        double_pid = pair_counter
        pair_counter += 1

        seats.extend([
            Seat(
                id=sid,
                row=row,
                col="A",
                pair_id=None,
                aisle_after=True,
                deck=deck
            ),

            Seat(
                id=sid + 1,
                row=row,
                col="B",
                pair_id=double_pid,
                aisle_after=False,
                deck=deck
            ),

            Seat(
                id=sid + 2,
                row=row,
                col="C",
                pair_id=double_pid,
                aisle_after=False,
                deck=deck
            ),
        ])

        sid += 3

    # ----------------------------------------
    # CREATE SEAT LAYOUT
    # ----------------------------------------

    if bus_type == BusType.SEATER:

        for row in range(1, num_rows + 1):
            add_seater_row(
                row,
                deck="Lower Deck"
            )

    elif bus_type == BusType.SLEEPER:

        lower = (num_rows + 1) // 2

        for row in range(1, lower + 1):
            add_sleeper_row(
                row,
                deck="Lower Deck"
            )

        for row in range(
            1,
            num_rows - lower + 1
        ):
            add_sleeper_row(
                row,
                deck="Upper Deck"
            )

    elif bus_type == BusType.SEATER_SLEEPER:

        seater_rows = (num_rows + 1) // 2
        sleeper_rows = num_rows - seater_rows

        for row in range(
            1,
            seater_rows + 1
        ):
            add_seater_row(
                row,
                deck="Lower Deck (Seater)"
            )

        for row in range(
            1,
            sleeper_rows + 1
        ):
            add_sleeper_row(
                row,
                deck="Upper Deck (Sleeper)"
            )

    else:

        raise InvalidBookingInput(
            f"Unknown bus type: {bus_type}"
        )

    # ----------------------------------------
    # RESERVE SAFETY PAIRS PER DECK
    # ----------------------------------------

    def reserve_pairs_for_deck(
        deck_type,
        number_of_pairs
    ):

        if number_of_pairs <= 0:
            return

        ordered_pair_ids = []
        seen = set()

        for seat in seats:

            # Identify which deck this seat belongs to
            if deck_type == "LOWER":

                if seat.deck is not None and "Lower" not in seat.deck:
                    continue

            elif deck_type == "UPPER":

                if seat.deck is None or "Upper" not in seat.deck:
                    continue

            # Ignore single sleeper berths
            if seat.pair_id is None:
                continue

            if seat.pair_id not in seen:

                ordered_pair_ids.append(
                    seat.pair_id
                )

                seen.add(
                    seat.pair_id
                )

        reserved_pair_ids = set(
            ordered_pair_ids[
                :number_of_pairs
            ]
        )

        for seat in seats:

            if seat.pair_id in reserved_pair_ids:

                seat.reserved_female = True

    # Lower-deck safety pairs
    reserve_pairs_for_deck(
        "LOWER",
        lower_reserved_pairs
    )

    # Upper-deck safety pairs
    reserve_pairs_for_deck(
        "UPPER",
        upper_reserved_pairs
    )

    return seats