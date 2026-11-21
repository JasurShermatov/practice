# Individual reflection — Jasur Shermatov

**What I produced:** six quality scenarios with a number in every measure, an 18-word hotel
vocabulary mapped to the P04 code, four bounded contexts (Rooms, Reservations, Payments,
Notifications) with their jobs, words, rules and dependencies, the words that change meaning
between contexts, one owner for each of the eight rule cards, the context map (Mermaid and a
draw.io page) and the exact fields that cross each of its three borders — plus a package-level
plan for P06 and a small test file that checks the documents against the counts the practice asks
for and against the real class names in the code.

**What the design made clearer:** "who owns a rule" has a mechanical answer — the context that
keeps all the data the rule reads. Applying it to the eight cards left no real doubt, and it
showed why the P04 code already felt right for cards 1–3: the booking rule sits with the
reservations. The same question shows what is still wrong: BookingService receives a plain list
of rooms and hands the whole `Reservation` to the sender, so two borders exist only on paper.

**What surprised me:** "Status" is four different things. Writing the sentence about Maya losing
R7 because a confirmation email failed made rule R6 concrete: the danger is not the failed email
but a shared field. A second surprise was a small contradiction in the course example for card 6
(Payments "asks Rooms for the price" would add a fourth arrow to a map where every arrow starts
at Reservations). I resolved it as decision D1 — Rooms prices the stay, Payments applies the 30% —
and wrote the cost down rather than drawing an arrow the map does not allow.

**What I would check with a classmate:** whether "Cancel" in Rooms (take a room off sale) is
really a meaning of the same word, or whether the hotel says "close" or "block" for it. The
ubiquitous language should come from the manager, not from me, so the Words table is a draft to
confirm with the domain expert.

**Open question and next action:** where the stay price is calculated once prices vary by date,
and whether a `Reservation` should keep the whole `Room` or only its number (D2). Next, in P06:
move the classes into the four packages exactly as in *Implications for the code*, give
Notifications its own `Confirmation`, and add the import check that fails when Reservations
names `EmailNotificationSender` — with the same behaviour tests green and the same nine demo
lines.
