# L02 notes

Exit check of lecture L02 (Object-oriented design, UML and SOLID), the starting point of this folder.

1. **Cancel() belongs in Reservation**, because the status it changes is the reservation's own data
   and the "already cancelled → false" rule must live in one place (encapsulation).
2. **Guest 1 —— 0..\* Reservation** says Maya can have zero, one or many reservations, and each
   reservation belongs to exactly one guest (Maya for R101).
3. **Open–closed (together with dependency inversion)** lets the hotel add SMS without editing
   BookingService: once BookingService depends on a notification interface, SMS is a new class.
   (That refactoring is P04; in P03 BookingService still uses the concrete EmailSender.)
