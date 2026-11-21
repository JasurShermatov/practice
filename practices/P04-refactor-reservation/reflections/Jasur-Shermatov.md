# Individual reflection — Jasur Shermatov

**What I produced:** six characterization tests that passed on the unchanged P03 code, a written
list of what the P03 design breaks, the "after" class diagram, the refactoring itself in the six moves
of the activity sheet with a test run after each one, the proof that the demo, the race and the saved
records did not change, and then — as separate steps — rule R6 and an SMS sender. Version 2 of the
`hotel-booking` code has `BookingService` depending only on `ReservationStore` and
`NotificationSender`, and `main.py` as the one place that picks the real classes.

**What made the refactoring safe:** writing the tests *before* touching anything, and keeping the
construction of the service in one helper. When the classes were renamed, only `new_service()` and an
import line changed; the six test bodies did not, and the diff shows it. Running the checks after every
move meant I never had to wonder which change broke something — nothing turned red that I had not
expected.

**What surprised me:** I pointed the UML-conformance test at the target diagram before moving any
code, so it stayed red through the moves while the behaviour tests stayed green. That separation was
useful: red design tests said "not there yet", green behaviour tests said "nothing broken". The second
surprise was how small R6 became once the sender was a promise: a fake that raises, a red test, then a
`try` around one call. In P03 I could not even have written that test.

**What I learned about the limits:** a `Protocol` is checked by shape. mypy accepted a sender that
cancels the reservation it is asked to confirm — the right method name, the wrong promise. Only a
behaviour test (the same scenario must give the same records for every sender) caught it. So
"implements the interface" is a type fact, while Liskov substitution is something tests have to show.

**What I did not change on purpose:** the race. Both requests still pass `has_overlap` before either
`save`; refactoring must not fix bugs, and the test that pins the double booking is still green. The
demo pause inside `reserve()` is also still there and written down as a smell.

**Open question and next action:** R6 now *reports* a failed confirmation, but nobody resends it. Should
the retry belong to the booking side or to the messaging side? My guess is messaging (an outbox or a
queue, P10), so that `BookingService` keeps one reason to change. Next: P05/P06 split the app into
business areas and modules, starting from this folder.
