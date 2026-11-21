# Individual reflection — Jasur Shermatov

**My contribution:** I drafted the scope, the three functional needs and the booking rules
with their checkable examples (sold out, last ticket, repeat request, email failure, lost
reply), the quality concerns and the evidence index, and checked the context sketch and
glossary for consistent use of "Confirmed".

**One booking rule in my own words:** for each concert, the app may never hold more confirmed
bookings than the concert's capacity. When Friday already has 20 of 20, a Book request must show
*Sold out* and save nothing — and when two requests compete for the last ticket, only one may be
saved, even though both saw "1 available" a moment earlier.

**One uncertainty:** I can state the required result for overlapping requests, but I do not yet
know which mechanism keeps the check and the save together so that the second request sees the
updated count — whether a transaction alone is enough, or whether the database needs a lock or
a constraint.

**Learning goal and next action:** in P02 I want to understand how a running process holds
temporary working data (like the "19" each request read) and why that data is different from the
saved booking. Next action: bring that question to P02 and later compare database protection
options in P11.
