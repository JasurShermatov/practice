"""Hotel booking app - version 7 (after P10): one program, four modules.

The module structure dates from version 3 (P06): the P04 app sorted into the four bounded
contexts designed in P05:

- ``hotel_booking.rooms``         which rooms the hotel sells
- ``hotel_booking.reservations``  who has which room for which nights (owns the booking rule)
- ``hotel_booking.payments``      deposits and whether they were paid (used from P17)
- ``hotel_booking.notifications`` telling guests what happened

Each module's ``__init__.py`` is its *public contract*: the only names other
modules may import. Its ``internal.py`` holds the classes that keep that
contract; only the module itself, the wiring (``main.py``) and the tests may
import them. ``.importlinter`` lists the borders and
``tests/test_architecture.py`` fails the build when one is crossed.

This package root deliberately re-exports nothing (it did up to P04): importing
``hotel_booking`` must not hand anyone a module's internal classes.
"""
