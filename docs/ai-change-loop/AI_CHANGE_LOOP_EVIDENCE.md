# AI Change-Loop Evidence Log

**Note:** this log covers two rounds of real iteration. Attempts 1-2 built a
"night bus" override rule on top of the original adjacency-based safety
check. Attempt 3 replaced that whole check with a simpler reserved-quota
model after manual testing found it blocked legitimate bookings (see
below). The current codebase reflects Attempt 3's design; Attempts 1-2 are
kept here because they're genuine, and the switch itself is the most
useful evidence of the process — not because the intermediate code still
exists.

**Tool used:** Claude (Anthropic), via chat, working directly against the repo.
**Feature requested:**
> "For buses departing at night (after 8 PM), never seat a solo female passenger
> next to an unrelated male — reject the booking with a clear error instead,
> even if the passenger tries to force it."

This is a genuine change-loop run against this repository — the failure below is
real (captured from an actual `pytest` run), not staged for the writeup.

---

## Attempt 1 — implement the rule, but only in one place

**Prompt given to the AI:**
> "Add a `strict_safety` mode to the seat allocator. When true, a solo female
> booking that would end up next to an unrelated male should be rejected
> instead of flagged. Wire it in for night departures (after 8 PM)."

**What the AI changed:**
- Added a `strict_safety: bool = False` parameter to `auto_assign()` in
  `seat_allocator.py`. When `strict_safety=True` and the best available seat
  is still risky, `auto_assign` now raises `NoSeatAvailableError` instead of
  returning `needs_confirmation=True`.
- Added two new tests in `tests/test_seat_allocator.py`:
  - `test_strict_safety_auto_rejects_risky_seat_for_solo_female`
  - `test_strict_safety_manual_rejects_even_with_confirm_true`

**Test run (attempt 1):**
```
tests/test_seat_allocator.py::test_strict_safety_auto_rejects_risky_seat_for_solo_female PASSED
tests/test_seat_allocator.py::test_strict_safety_manual_rejects_even_with_confirm_true FAILED

E   TypeError: manual_assign() got an unexpected keyword argument 'strict_safety'

1 failed, 1 passed in 0.05s
```
(Full output: `attempt1_test_run.txt`)

**What broke:** the AI only added `strict_safety` to `auto_assign()`. The
manual-booking path (`manual_assign()`, used when a passenger clicks a
specific seat on the map) was never touched — so a passenger could still
force a night-bus booking next to a stranger by picking the seat manually
and confirming. The test suite caught this immediately because a test had
already been written for the manual path before the fix was assumed
complete.

## Attempt 2 — fix the gap

**Prompt given to the AI:**
> "manual_assign doesn't accept strict_safety and the test failed with a
> TypeError. Add the same parameter there, and make sure confirm=True can't
> override it when strict_safety is on."

**What the AI changed:**
- Added `strict_safety: bool = False` to `manual_assign()` in
  `seat_allocator.py`. When a chosen seat is risky and `strict_safety=True`,
  it now raises `NeedsConfirmationError` with a message explaining the rule
  cannot be overridden — regardless of the `confirm` flag.
- Updated `app.py`:
  - Added `is_night_departure()` helper (parses the bus's `HH:MM` departure
    time; night = 20:00–05:59).
  - Both the `auto_assign` and `manual_assign` calls in the `/book` route now
    pass `strict_safety=is_night_departure(bus.departure_time)`.
  - Distinguished a hard rejection (`hard_block=True`, night bus) from a soft
    "book anyway" confirmation in the response, so the template can show the
    right message.
- Updated `templates/bus.html` to show a non-overridable message ("cannot be
  overridden on buses departing after 8 PM") instead of a "Book anyway"
  button when `hard_block` is set.

**Test run (attempt 2):**
```
tests/test_seat_allocator.py::test_strict_safety_auto_rejects_risky_seat_for_solo_female PASSED
tests/test_seat_allocator.py::test_strict_safety_manual_rejects_even_with_confirm_true PASSED
...
17 passed in 0.03s
```
(Full output: `attempt2_test_run.txt` — this is the whole suite, confirming
nothing else regressed.)

**Manual verification (live app, not just unit tests):** using the Flask
test client against the seeded night bus (departs 21:30):
1. Booked seat 1A as a male passenger.
2. Attempted to manually book seat 1B (adjacent) as a solo female with
   `confirm=true`.
3. Result: booking rejected, hard-block message shown, seat 1B remained
   free. Confirmed via `/api/bus/1/seats`.

## Summary

| Attempt | Result | Attempts to green |
|---|---|---|
| 1 | Failed — gap between auto and manual paths | — |
| 2 | Passed — 17/17, including manual end-to-end check | 2 |

**Where I had to step in manually:** the AI's first pass covered the
"obvious" path (auto-assign) and missed that the same rule needed to apply
to manual seat selection — a realistic omission, since the two functions
look similar but aren't shared code. I directed the second attempt by
pointing at the actual test failure rather than re-describing the whole
feature, which is what got it fixed in one more pass instead of several.

---

## Attempt 3 — a real design flaw found through manual testing (not automated tests)

After Attempt 2 shipped, I manually tested the app in a browser rather than
just running pytest. That's what caught the real problem: the "risky
adjacency" rule treated *any* stranger of the opposite gender next to a
solo female as something to block or warn about. In practice this broke
completely ordinary cases — a husband and wife, siblings, or a mother and
son booking separately still look like "two unrelated people of different
genders" to that rule, so a legitimate family booking got blocked with a
"cannot be overridden" error.

**This is exactly the kind of thing the automated test suite did NOT catch**
— all 17 tests passed, because the tests were written to check the rule
does what it was designed to do, not whether the rule's design was actually
right for real usage. It took a human clicking through the UI to notice.

**Prompt given to the AI:**
> "The safety rule is blocking legitimate cases — a couple or family
> travelling together shouldn't get blocked just because they booked
> separately and are different genders. Redesign this: instead of trying
> to detect 'risky' adjacency, reserve a fixed number of seat PAIRS on each
> bus as female-only. Every other seat is open to anyone, no restrictions.
> Auto-assign a solo female into a reserved seat first if one's free, but
> never let a male or a group into a reserved seat."

**What the AI changed:**
- Rewrote `seat_allocator.py` from an adjacency-detection model
  (`_is_risky`, `NeedsConfirmationError`, `strict_safety`) to a
  reserved-quota model (`reserved_female` flag per seat, `ReservedSeatError`).
  This is a smaller, simpler ruleset with fewer edge cases to get wrong.
- Rewrote the test suite to match — including a new test that directly
  encodes the bug that was found:
  `test_couple_can_sit_together_in_general_seating_without_any_block`.
- Found (and fixed) a second real bug while rewriting: the first draft of
  the new `make_bus_layout()` only reserved one pair per row regardless of
  how many pairs were requested, so a bus with `female_reserved_pairs=2`
  only ever got 1 pair reserved. Caught immediately by
  `test_group_booking_ignores_reserved_seats_even_if_free`, which expected
  a fully-reserved single-row bus to have zero general seats and failed
  with "DID NOT RAISE" — fixed by reserving pairs globally across the bus
  instead of per-row.
- Updated `app.py` and `templates/bus.html` to remove the whole
  "confirm this booking" flow, since general seating no longer needs one.
- Added bus types (Seater / Sleeper / Seater+Sleeper) and a fare/receipt
  step at the same time, since the layout code needed touching anyway.

**Test run (attempt 3, after both fixes):**
```
17 passed in 0.02s
```
(Full output: `docs/test-evidence/green_run_output.txt`. The red run in
`docs/test-evidence/red_run_output.txt` captures a deliberately-broken
version of the *current* reserved-seat rule, for the same red/green
requirement.)

**Honest note on what this means for the assessment:** the first version
of this feature technically passed every test I wrote for it and still had
a real, user-facing design flaw. The fix here wasn't "write more tests" —
it was recognising the rule itself was wrong and replacing it with a
simpler one that has a smaller surface for that kind of mistake. I think
that's a more useful thing to show than a change loop where nothing ever
goes wrong.

---

## Current Final State

The current codebase keeps the simpler reserved-quota safety model from
Attempt 3, with a further refinement to support safety-pair configuration
on both decks.

The final implementation uses:

- `lower_reserved_pairs` — reserved safety pairs on the lower deck
- `upper_reserved_pairs` — reserved safety pairs on the upper deck

This allows buses to provide reserved safety-pair options on both decks
while preserving the original allocation behavior:

- Solo female passengers are auto-assigned a reserved seat first when one
  is available.
- Male passengers cannot manually book a female-reserved seat.
- Group bookings use general seating.
- General seats remain available without gender-based restrictions.

The test suite was updated to match the new configuration API and an
additional test was added to verify upper-deck reserved-pair creation.

The final local test run contains:

```text
18 tests
18 passed
0 failed
The final testing evidence is stored separately in:

- `docs/test-evidence/green_run_output.txt`
- `docs/test-evidence/red_run_output.txt`
- `docs/test-evidence/final_run.txt`

The RED RUN was deliberately created using an incorrect test expectation
to verify that the test suite detects a violation of the reserved-seat
rule. The production application was not intentionally left in a broken
state.