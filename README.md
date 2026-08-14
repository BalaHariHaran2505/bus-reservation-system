# SafeSeat — Bus Seat Reservation with Ladies-Reserved Seating

A bus seat booking app built for the Tactive internship assessment. Core
feature: each bus reserves a fixed number of seat **pairs** exclusively for
female passengers (like reserved-ladies seating on real buses/trains).
Every other seat is open to anyone, so couples, siblings, or family booking
separately are never blocked from sitting together. No location tracking,
no third-party data — the whole feature runs on booking data already
collected on the form.

## What's in this repo

```
app.py                     Flask routes
models.py                   DB models (SQLAlchemy)
seat_allocator.py            Core seat-allocation logic (the graded feature)
seed.py                      Creates sample buses (Seater, Sleeper, Seater+Sleeper)
tests/test_seat_allocator.py  17 pytest tests, incl. a deliberate red run
templates/, static/           UI
docs/
  ARCHITECTURE.md
  DESIGN.md
  USER_GUIDE.md
  test-evidence/              Captured red-run and green-run pytest output
  ai-change-loop/             Real AI change-loop evidence (Stage 3), incl.
                                a real design flaw found during manual testing
```

## How to run it

Requires Python 3.10+.

```bash
git clone <this repo>
cd bus-reservation
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env              # then edit SECRET_KEY / ADMIN_PASSWORD
python seed.py                    # creates the SQLite DB with sample buses
python app.py
```

Open http://127.0.0.1:5000

Admin dashboard: http://127.0.0.1:5000/admin (password = whatever you set
in `.env` as `ADMIN_PASSWORD`).

### Using MySQL instead of SQLite

Set `DATABASE_URL` in `.env`, e.g.:
```
DATABASE_URL=mysql+pymysql://user:password@localhost/bus_reservation
```
(install `pymysql` separately: `pip install pymysql`). No code changes
needed — SQLAlchemy handles both.

## Running the tests

```bash
pytest -v
```
17 tests should pass — normal booking path, edge cases, invalid input, and
the reserved-seat rule.

A deliberately-wrong test is included (commented out) at the bottom of
`tests/test_seat_allocator.py` to demonstrate a red run. Uncomment
`test_DELIBERATE_RED_RUN_male_should_not_book_reserved_seat` and run
`pytest -v -k red_run` to see it fail. Captured output for both the red run
and the full green run is in `docs/test-evidence/`.

## AI tools used

- **Claude (Anthropic)** — used to design and write the seat allocation
  logic, the Flask app, tests, and documentation, and to run the AI
  change-loop (see `docs/ai-change-loop/AI_CHANGE_LOOP_EVIDENCE.md`). That
  log also documents a real design flaw the first version had (it blocked
  legitimate couples/family bookings) that was only caught by manual
  testing, not the automated tests — and how it was fixed.

## Security notes

- No secrets committed — `.env` is git-ignored, `.env.example` ships with
  placeholders only.
- All DB queries go through the SQLAlchemy ORM (parameterised, no SQL
  injection surface).
- CSRF protection on every form.
- Server-side validation on all booking input (name, 10-digit phone,
  gender) — not just HTML form constraints.
- Admin routes are behind a password-gated session.

## What I'd do with another week

- Add proper seat-locking for concurrent bookings.
- Add Selenium/Playwright browser tests on top of the current pytest unit
  tests, covering the click-to-book UI flow end to end.
- Let an admin configure `female_reserved_pairs` per bus from the
  dashboard instead of only via `seed.py`.
