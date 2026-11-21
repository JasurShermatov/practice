# Evidence index — P06

Labels as agreed in L01/P01: **Proposed** (planned, not run), **Simulated** (model / thought
experiment), **Observed** (actually run; command, environment and real output recorded).
Environment for every Observed row: Linux container, Python 3.13.18, pytest 9.1.1, mypy (strict),
Mermaid CLI 11.16.0 with headless Chromium; portfolio build of 2026-11-21. Outputs:
[observed-runs.md](observed-runs.md) and [logs/](logs/).

| ID | Label | Requirement | Action | Expected | Actual | Limitation |
|---|---|---|---|---|---|---|
| E1 | **Observed** | Step 1: lock the behaviour | `unittest -v`, `main.py`, `main.py --race`, `pytest`, `mypy` on the P04 code | 8 OK; nine lines; double booking | 8 OK, 82 passed, mypy clean; nine lines; 2 Confirmed ([O1](observed-runs.md#o1--step-1-the-safety-net-before-any-move)) | — |
| E2 | **Observed** | Step 2: folders; tests still green | Empty packages, then `unittest` | 8 OK | Red first (package/module name clash on `notifications`), green after moving the folder creation into move 3.2 ([O2](observed-runs.md#o2--step-2-the-name-clash)) | — |
| E3 | **Observed** | Steps 3–4: tests after each move | `unittest test_booking_service` + demo `diff` after moves 3.1, 3.2/3.3, 4.1, 4.2 | 8 OK, no diff, each time | As expected ([O3](observed-runs.md#o3--steps-34-after-every-move)) | The pytest suite was adapted once, in Step 5, not after every move |
| E4 | **Observed** | Step 5: only main names internal code | `grep` of the module folders; `test_no_module_imports_another_modules_internal_code`, `test_only_main_creates_concrete_classes_of_the_modules` | No hit in the modules | Only a docstring hit; only `main.py` + tests import internals ([O4](observed-runs.md#o4--step-5-who-names-internal-code)) | — |
| E5 | **Observed** | Step 6: three checks pass | `python -m tests.test_architecture`; `pytest tests/test_architecture.py` | "Contracts: 3 kept, 0 broken." | As expected ([O5](observed-runs.md#o5--step-6-the-three-contracts)) | `lint-imports` itself not run: import-linter not installable here (E13) |
| E6 | **Observed** | Step 7: break the border, read, undo | Bad import added to `reservations/booking.py`, checks run, line removed | Rule 1 red, names booking → notifications.internal; 8 tests green; green after undo | Exactly as predicted; same SHA-256 after undo ([O6](observed-runs.md#o6--step-7-broken-on-purpose)) | — |
| E7 | **Observed** | Each rule can fail (extra) | `break_the_border.py` on a throw-away copy, rules 1–3 | Exactly one contract red per case; 8 tests green | As expected ([O7](observed-runs.md#o7--all-three-rules-broken-on-a-copy)) | — |
| E8 | **Observed** | Step 8: same behaviour at the end | `unittest -v`, demo `diff`, race ×20, `pytest`, `mypy` | 8 OK; no diff; still 2 Confirmed | 8 OK; no diff; 20/20 double-booked; 118 passed; mypy clean ([O8](observed-runs.md#o8--step-8-after)) | — |
| E9 | **Observed** | Behaviour identical v2 → v3 (accepted/full/error + saved records) | `compare_behaviour.py` on the P04 copy and on the P06 project, `diff` | No difference | No difference ([O9](observed-runs.md#o9--before-and-after-scenario-version-2-vs-version-3)) | One fixed scenario |
| E10 | **Observed** | S5 on the new structure | Swap email → SMS in the wiring of a copy | 1 file, 0 module lines; tests + contracts green | 1 line in `main.py`; green ([O10](observed-runs.md#o10--s5-sms-instead-of-email-on-the-p06-structure)) | Done on a copy; the project keeps email |
| E11 | **Observed** | Diagrams render; drawio page shape; as-built diagram = real imports | `mmdc`; `checks/test_p06_docs.py` | No errors; checks pass | OK; 23 passed ([O11](observed-runs.md#o11--diagrams-and-document-checks)) | `.drawio` not opened in the draw.io app here; its XML is checked |
| E12 | **Observed** | Earlier practices still consistent | P05 document checks (code names exist after the move) | 26 passed | 26 passed ([O11](observed-runs.md#o11--diagrams-and-document-checks)) | — |
| E13 | **Observed** | Tool availability (honesty) | `import importlinter`; `pip download import-linter` | — | Not installed; PyPI unreachable ([logs/f-importlinter-unavailable.txt](logs/f-importlinter-unavailable.txt)) | Reason for the stdlib substitute |
| E14 | **Simulated** | Change impact of the other three hotel requests; checker blind spots | Traced on the real module structure ([Architecture-review R7, R10](../Architecture-review.md#r10--change-impact-on-the-real-structure)) | Rooms-only / Payments-only changes | As expected on paper | Becomes Observed when P07/P17 make the changes |
| E15 | **Proposed** | `lint-imports` prints "Contracts: 3 kept, 0 broken." on the Mac | `pip install -r requirements.txt && lint-imports` in `hotel-booking/` | Same three KEPT lines as E5 | Not run — **to do by the student** | — |
| E16 | **Proposed** | Pair work, swapping typist; the draw.io page opened and checked by the partner | Classroom | — | **To do by the student** | — |
