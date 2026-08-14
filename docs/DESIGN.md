# Design Document — SafeSeat Bus Reservation

## 1. Data Model

**Bus**
| Field | Type | Notes |
|---|---|---|
| id | int (PK) | |
| name, route | string | |
| bus_type | string | SEATER / SLEEPER / SEATER_SLEEPER |
| num_rows | int | |
| lower_reserved_pairs | int | how many reserved seat pairs are configured on the lower deck |
| upper_reserved_pairs | int | how many reserved seat pairs are configured on the upper deck |
| fare_per_seat | int | ₹ per seat |
| departure_time | string "HH:MM" | |

**Seat**
| Field | Type | Notes |
|---|---|---|
| id | int (PK) | |
| bus_id | int (FK) | |
| row, col | int, string | col is A/B/C/D (seater) or A/B/C (sleeper) |
| pair_id | int or null | seats sharing a pair_id are physically adjacent; null = no neighbour (single berth) |
| aisle_after | bool | where to draw the aisle gap when rendering |
| deck | string or null | e.g. "Lower Deck" — cosmetic grouping only |
| reserved_female | bool | true = Ladies-reserved seat |
| status | string | FREE / BOOKED |
| gender | string or null | F / M, set once booked |
| group_id | int or null | shared by passengers who booked together |
| passenger_name, passenger_phone | string or null | |

**BookingLog** (audit trail / bill history)
| Field | Type | Notes |
|---|---|---|
| id, bus_id, seat_id | int | |
| passenger_name, gender, group_id | | |
| used_reserved | bool | was this a Ladies-reserved seat |
| fare | int | |
| action | string | BOOK / CANCEL |
| booking_ref | string | groups seats booked in one transaction, for the bill |
| created_at | datetime | |

## 2. Seat Layouts

- **Seater**: each row has 4 seats — `A,B` (a pair) `‖ aisle ‖` `C,D` (a pair).
- **Sleeper**: each row has 3 berths — `A` (single, no neighbour) `‖ aisle ‖`
  `B,C` (a double berth, paired).
- **Seater + Sleeper**: lower deck uses the Seater layout, upper deck uses
  the Sleeper layout.

Only paired seats can be Ladies-reserved (a single berth has no adjacency
risk to begin with). Reserved pairs are configured independently for the lower and upper
decks using `lower_reserved_pairs` and `upper_reserved_pairs`.
Reserved pairs are assigned to available paired seats on the corresponding
deck. All other seats remain general seating and are open to anyone.


## 3. Key Flow: Booking a Seat

1. Passenger fills in name, phone, gender, and either:
   - **Auto**: system assigns the best seat.
     - Solo female → a free Ladies-reserved seat first, else any free
       general seat.
     - Male, or a group of any gender mix → general seating only, even if
       reserved seats are free.
   - **Manual**: passenger picks a specific free seat on the map.
     - Any free **general** seat: booked instantly for anyone.
     - A **reserved** seat: only bookable if the passenger is female.
2. On success, a bill/receipt is shown (seat, fare, total) and the booking
   is logged.

There is no "confirm this booking" step for general seating — a couple,
siblings, or family members booking separately can sit next to each other
freely, since general seats have no gender restriction at all. The only
restriction anywhere on the bus is: reserved seats are female-only.

## 4. Key Flow: Cancelling a Seat

1. Passenger (or admin) cancels a booked seat.
2. Seat is reset to FREE, passenger fields cleared.
3. `reserved_female` is **not** cleared — it's a property of the bus's
   seat map, not of any particular booking, so a cancelled reserved seat
   stays reserved for the next female passenger.

## 5. Interface (Routes)

| Route | Method | Purpose |
|---|---|---|
| `/` | GET | List buses |
| `/bus/<id>` | GET | Seat map + booking form |
| `/bus/<id>/book` | POST | Book seat(s) — returns a bill on success |
| `/bus/<id>/cancel/<seat_id>` | POST | Cancel a booking |
| `/admin/login` | GET/POST | Admin login |
| `/admin` | GET | Dashboard: buses + recent booking activity |
| `/api/bus/<id>/seats` | GET | JSON seat state (used for testing) |

## 6. Error Handling

| Situation | Behaviour |
|---|---|
| Invalid name/phone/gender | Form re-shown with an inline error, nothing booked |
| Seat already booked (race) | Rejected with a clear message |
| No free seats at all | Rejected with a clear message |
| Group size bigger than any row | Rejected with a clear message |
| Male tries to book a reserved seat | Rejected: "This seat is reserved for female passengers" |
| Unknown bus type | Rejected at layout-generation time |
| Wrong admin password | Login form re-shown, no session created |

All of the above are backed by real exceptions in `seat_allocator.py`
(`InvalidBookingInput`, `NoSeatAvailableError`, `ReservedSeatError`) that
`app.py` catches and turns into a message the passenger can act on.
