# L03 notes

Exit check of lecture L03 (DDD, architectural styles and the modular monolith). P05 starts from
answer 1. Destination in the project: `hotel-booking/docs/l03-notes.md`.

1. **Reservations owns the booking rule**, because it keeps every reservation of a room and so is
   the only context that can check that no two Confirmed ones share a night (Rooms knows R7
   exists, not who booked it; a Paid deposit does not free a night; a message decides nothing).
2. **P06 forbids Reservations from naming `EmailNotificationSender`** (internal to Notifications);
   Reservations uses the `NotificationSender` contract and hands it a `Confirmation`, and only the
   wiring in `main.py` chooses the email or SMS sender.
3. **Start as a modular monolith** because one team with one release rhythm runs one app more
   simply, and S2 (no double booking) is checked in one place with local calls; **revisit ADR-001**
   when a module needs its own releases or its own scaling, shown by measurements, not guesses
   (L07/P13).
