"""
Test suite for the reserved-quota seat-allocation engine.

Run with:
    pytest -v
"""

import sys
import os

sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
)

import pytest

from seat_allocator import (
    Seat,
    SeatStatus,
    Gender,
    make_bus_layout,
    auto_assign,
    manual_assign,
    commit_booking,
    cancel_booking,
    InvalidBookingInput,
    NoSeatAvailableError,
    ReservedSeatError,
)


def book(seat, gender, group_id=None, name="X"):
    commit_booking(
        seat,
        gender,
        group_id,
        name
    )


# ---------- 1. Normal path ----------


def test_solo_female_auto_gets_reserved_seat_when_available():

    seats = make_bus_layout(
        5,
        bus_type="SEATER",
        lower_reserved_pairs=1,
        upper_reserved_pairs=0
    )

    result = auto_assign(
        seats,
        "F",
        group_size=1
    )

    assert result["used_reserved"] is True
    assert result["seats"][0].reserved_female is True


def test_solo_male_auto_never_gets_a_reserved_seat():

    # Only 1 pair is reserved.
    # Fill every general seat so only reserved seats remain free.
    # Male booking must fail instead of using a reserved seat.

    seats = make_bus_layout(
        1,
        bus_type="SEATER",
        lower_reserved_pairs=1,
        upper_reserved_pairs=0
    )

    general = [
        s for s in seats
        if not s.reserved_female
    ]

    for i, s in enumerate(general):
        book(
            s,
            "M",
            group_id=i
        )

    with pytest.raises(NoSeatAvailableError):
        auto_assign(
            seats,
            "M",
            group_size=1
        )


def test_solo_female_auto_falls_back_to_general_when_reserved_full():

    seats = make_bus_layout(
        1,
        bus_type="SEATER",
        lower_reserved_pairs=1,
        upper_reserved_pairs=0
    )

    reserved = [
        s for s in seats
        if s.reserved_female
    ]

    for i, s in enumerate(reserved):
        book(
            s,
            "F",
            group_id=i
        )

    result = auto_assign(
        seats,
        "F",
        group_size=1
    )

    assert result["used_reserved"] is False
    assert result["seats"][0].reserved_female is False


# ---------- 2. General seating has no gender restriction ----------


def test_couple_can_sit_together_in_general_seating_without_any_block():

    seats = make_bus_layout(
        2,
        bus_type="SEATER",
        lower_reserved_pairs=0,
        upper_reserved_pairs=0
    )

    seat_a = next(
        s for s in seats
        if s.row == 1 and s.col == "A"
    )

    book(
        seat_a,
        "M",
        group_id=None,
        name="Passenger 1"
    )

    seat_b = next(
        s for s in seats
        if s.row == 1 and s.col == "B"
    )

    chosen = manual_assign(
        seats,
        seat_id=seat_b.id,
        gender="F"
    )

    assert chosen.id == seat_b.id


def test_male_can_manually_book_seat_next_to_unrelated_female_in_general_seating():

    seats = make_bus_layout(
        2,
        bus_type="SEATER",
        lower_reserved_pairs=0,
        upper_reserved_pairs=0
    )

    seat_a = next(
        s for s in seats
        if s.row == 1 and s.col == "A"
    )

    book(
        seat_a,
        "F",
        group_id=None,
        name="Passenger 1"
    )

    seat_b = next(
        s for s in seats
        if s.row == 1 and s.col == "B"
    )

    chosen = manual_assign(
        seats,
        seat_id=seat_b.id,
        gender="M"
    )

    assert chosen.id == seat_b.id


# ---------- 3. Reserved-seat protection ----------


def test_manual_male_booking_of_reserved_seat_is_rejected():

    seats = make_bus_layout(
        3,
        bus_type="SEATER",
        lower_reserved_pairs=1,
        upper_reserved_pairs=0
    )

    reserved_seat = next(
        s for s in seats
        if s.reserved_female
    )

    with pytest.raises(ReservedSeatError):
        manual_assign(
            seats,
            seat_id=reserved_seat.id,
            gender="M"
        )


def test_manual_female_booking_of_reserved_seat_succeeds():

    seats = make_bus_layout(
        3,
        bus_type="SEATER",
        lower_reserved_pairs=1,
        upper_reserved_pairs=0
    )

    reserved_seat = next(
        s for s in seats
        if s.reserved_female
    )

    chosen = manual_assign(
        seats,
        seat_id=reserved_seat.id,
        gender="F"
    )

    assert chosen.id == reserved_seat.id


# ---------- 4. Groups always use general seating ----------


def test_group_booking_ignores_reserved_seats_even_if_free():

    seats = make_bus_layout(
        1,
        bus_type="SEATER",
        lower_reserved_pairs=2,
        upper_reserved_pairs=0
    )

    with pytest.raises(NoSeatAvailableError):
        auto_assign(
            seats,
            "F",
            group_size=2,
            group_id=1
        )


def test_group_booking_finds_contiguous_general_block():

    seats = make_bus_layout(
        2,
        bus_type="SEATER",
        lower_reserved_pairs=0,
        upper_reserved_pairs=0
    )

    result = auto_assign(
        seats,
        "M",
        group_size=2,
        group_id=1
    )

    assert len(result["seats"]) == 2
    assert (
        result["seats"][0].row
        ==
        result["seats"][1].row
    )


# ---------- 5. Bus types / layout ----------


def test_sleeper_layout_has_single_and_double_berths():

    seats = make_bus_layout(
        4,
        bus_type="SLEEPER",
        lower_reserved_pairs=1,
        upper_reserved_pairs=1
    )

    singles = [
        s for s in seats
        if s.pair_id is None
    ]

    doubles = [
        s for s in seats
        if s.pair_id is not None
    ]

    assert len(singles) > 0
    assert len(doubles) > 0

    # Single sleeper berths cannot be reserved.
    assert all(
        not s.reserved_female
        for s in singles
    )


def test_seater_sleeper_mix_has_both_decks():

    seats = make_bus_layout(
        6,
        bus_type="SEATER_SLEEPER",
        lower_reserved_pairs=1,
        upper_reserved_pairs=1
    )

    decks = {
        s.deck
        for s in seats
    }

    assert any(
        "Seater" in (d or "")
        for d in decks
    )

    assert any(
        "Sleeper" in (d or "")
        for d in decks
    )


def test_upper_deck_reserved_pairs_are_created():

    seats = make_bus_layout(
        6,
        bus_type="SEATER_SLEEPER",
        lower_reserved_pairs=1,
        upper_reserved_pairs=2
    )

    upper_reserved = [
        s for s in seats
        if s.deck
        and "Upper" in s.deck
        and s.reserved_female
    ]

    lower_reserved = [
        s for s in seats
        if s.deck
        and "Lower" in s.deck
        and s.reserved_female
    ]

    assert len(upper_reserved) > 0
    assert len(lower_reserved) > 0


def test_unknown_bus_type_raises():

    with pytest.raises(InvalidBookingInput):
        make_bus_layout(
            3,
            bus_type="ROCKET"
        )


# ---------- 6. Invalid input ----------


def test_invalid_gender_raises():

    seats = make_bus_layout(
        2,
        bus_type="SEATER",
        lower_reserved_pairs=0,
        upper_reserved_pairs=0
    )

    with pytest.raises(InvalidBookingInput):
        auto_assign(
            seats,
            "X",
            group_size=1
        )


def test_zero_group_size_raises():

    seats = make_bus_layout(
        2,
        bus_type="SEATER",
        lower_reserved_pairs=0,
        upper_reserved_pairs=0
    )

    with pytest.raises(InvalidBookingInput):
        auto_assign(
            seats,
            "F",
            group_size=0
        )


def test_manual_assign_unknown_seat_id_raises():

    seats = make_bus_layout(
        2,
        bus_type="SEATER",
        lower_reserved_pairs=0,
        upper_reserved_pairs=0
    )

    with pytest.raises(InvalidBookingInput):
        manual_assign(
            seats,
            seat_id=9999,
            gender="F"
        )


def test_manual_assign_already_booked_seat_raises():

    seats = make_bus_layout(
        1,
        bus_type="SEATER",
        lower_reserved_pairs=0,
        upper_reserved_pairs=0
    )

    seat = seats[0]

    book(
        seat,
        "M"
    )

    with pytest.raises(NoSeatAvailableError):
        manual_assign(
            seats,
            seat_id=seat.id,
            gender="F"
        )


# ---------- 7. Cancellation ----------


def test_cancel_frees_seat_but_keeps_reserved_flag():

    seats = make_bus_layout(
        2,
        bus_type="SEATER",
        lower_reserved_pairs=1,
        upper_reserved_pairs=0
    )

    reserved_seat = next(
        s for s in seats
        if s.reserved_female
    )

    book(
        reserved_seat,
        "F"
    )

    cancel_booking(
        reserved_seat
    )

    assert reserved_seat.status == SeatStatus.FREE
    assert reserved_seat.gender is None

    # Reservation flag remains after cancellation.
    assert reserved_seat.reserved_female is True

    # Male still cannot use it.
    with pytest.raises(ReservedSeatError):
        manual_assign(
            seats,
            seat_id=reserved_seat.id,
            gender="M"
        )


# ---------- DELIBERATE RED RUN ----------
# # ---------- DELIBERATE RED RUN ----------
# #
# # This test is intentionally WRONG.
# # It expects a male passenger to successfully book
# # a seat that is reserved for female passengers.
# #
# # The actual application correctly raises ReservedSeatError.
# #
# # This test is used only to demonstrate that the test
# # suite can detect an intentional regression.

# def test_DELIBERATE_RED_RUN_male_should_not_book_reserved_seat():

#     seats = make_bus_layout(
#         3,
#         bus_type="SEATER",
#         lower_reserved_pairs=1,
#         upper_reserved_pairs=0
#     )

#     reserved_seat = next(
#         s for s in seats
#         if s.reserved_female
#     )

#     # WRONG ON PURPOSE:
#     # A male should NOT be allowed to book this seat.
#     # The application will raise ReservedSeatError.
#     chosen = manual_assign(
#         seats,
#         seat_id=reserved_seat.id,
#         gender="M"
#     )

#     assert chosen.id == reserved_seat.id