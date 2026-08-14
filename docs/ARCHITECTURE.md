# Architecture Document — SafeSeat Bus Reservation

## 1. Overview

SafeSeat is a small web app for booking bus seats, built around one
specific piece of functionality: a **reserved-quota safety seating system**
for female passengers — a fixed number of seat pairs on each bus are
"Ladies Reserved" (female passengers only), while every other seat is open
to anyone, no restrictions. This mirrors how real reserved-seat systems
work (e.g. ladies seats on public buses/trains) rather than trying to
guess who "belongs" next to whom.

## 2. Components

```
┌─────────────┐      HTTP       ┌───────────────────┐
│   Browser    │ ───────────────▶│   Flask app        │
│ (Jinja HTML, │◀─────────────── │   (app.py)          │
│  minimal JS) │                 └─────────┬──────────┘
└─────────────┘                            │
                                            │ calls
                                            ▼
                                 ┌────────────────────┐
                                 │ seat_allocator.py   │
                                 │ (pure business      │
                                 │  logic, no DB/Flask │
                                 │  dependency)        │
                                 └─────────┬───────────┘
                                            │ reads/writes via
                                            ▼
                                 ┌────────────────────┐
                                 │ models.py (SQLAlchemy)│
                                 │ Bus / SeatRow / Log  │
                                 └─────────┬───────────┘
                                            ▼
                                   SQLite (default) or
                                   MySQL (via DATABASE_URL)
```

- **`seat_allocator.py`** — the core of the assessment. Contains the seat
  safety rules as plain, framework-free Python functions operating on a
  lightweight `Seat` dataclass. It has no knowledge of Flask, SQL, or HTTP.
- **`app.py`** — Flask routes. Converts DB rows to `Seat` objects, calls the
  allocator, writes results back to the DB, handles validation/CSRF/auth.
- **`models.py`** — SQLAlchemy models: `Bus`, `SeatRow` (persisted seat
  state), `BookingLog` (audit trail of every book/cancel action, including
  whether a safety confirmation was involved).
- **Templates/static** — server-rendered Jinja2 HTML + a small stylesheet.
  No JS framework; a seat map renders as clickable buttons, kept intentionally
  simple so the assessment's automated tests can drive it without needing a
  full SPA build step.

## 3. Why this stack

- **Flask over FastAPI/Django** — the functionality being assessed is one
  focused rule engine plus a handful of routes. Flask keeps the surface area
  small so the grader (and the AI change-loop) can reason about the whole
  app quickly.
- **SQLAlchemy over raw SQL** — lets the same code run on SQLite (zero
  setup, so anyone can `git clone` and run it) or MySQL (`DATABASE_URL` env
  var) without changing a line of application code. MySQL was the developer's
  strongest DB background, so it was kept as a first-class option rather
  than the only option — SQLite exists purely so a grader with no local
  MySQL install can still run the repo from the README in under a minute.
- **The allocator is deliberately decoupled from Flask/SQLAlchemy** — it
  takes and returns plain `Seat` dataclasses. This was a specific design
  choice: it makes the safety logic unit-testable with 17 fast, deterministic
  pytest cases that need no database, no HTTP client, and no fixtures beyond
  a list of seats — which is exactly what an AI coding agent needs in order
  to run a tight test → fail → fix loop (Stage 3) without also having to
  spin up a database each time.
- **Server-rendered HTML, not React** — the feature being assessed is
  backend logic (an allocation rule), not a rich frontend. A JS framework
  would have added build tooling without adding to what's actually graded.

## 4. Data flow — a booking request

1. Browser submits the booking form (`name`, `phone`, `gender`, `mode`,
   optionally `seat_id`, `group_size`) to `POST /bus/<id>/book`.
2. `app.py` validates input (name pattern, 10-digit phone, gender enum).
3. Current seat state is loaded from `SeatRow` and converted to
   `seat_allocator.Seat` objects.
4. `app.py` calls `seat_allocator.auto_assign()` (system picks the seat) or
   `.manual_assign()` (passenger picked a specific seat).
   - Auto: a solo female is offered a free Ladies-reserved seat first, else
     a general seat. A male or a group booking only ever draws from general
     seating.
   - Manual: any free general seat can be booked by anyone. A reserved seat
     can only be booked manually by a female passenger.
5. On success, `app.py` commits the booking, writes a `BookingLog` row, and
   renders a receipt/bill (seat, fare, total).
6. On failure (`NoSeatAvailableError`, `ReservedSeatError`,
   `InvalidBookingInput`), the passenger is shown a clear message and
   nothing is booked.

## 5. Security choices

- All DB access goes through SQLAlchemy's ORM (parameterised queries — no
  raw string-built SQL, so no SQL injection surface).
- CSRF protection (`Flask-WTF`) on every state-changing form.
- Server-side input validation on name/phone/gender (never trust the client;
  the HTML5 `pattern` attributes are a UX nicety, not the real check).
- Admin dashboard is behind a password-gated session (`ADMIN_PASSWORD`),
  not exposed to the public routes.
- No secrets committed: `SECRET_KEY` and `ADMIN_PASSWORD` are read from
  environment variables (`.env`, which is git-ignored); `.env.example` ships
  instead with placeholder values.
- No tracking of any kind — the "safety seat" feature reasons only about
  gender and grouping data the passenger already provided at booking time.
  No location, device, or third-party data is collected or required.

## 6. Known limitations / what I'd do with more time

- Row/pair adjacency is the only safety signal considered; a real system
  might also account for berths across the aisle for sleeper buses.
- No payment integration — bookings are free-form for the assessment.
- No real-time seat locking for concurrent bookings (two people racing for
  the same seat within milliseconds); a production version would need a DB
  row lock or a short-lived reservation hold.
