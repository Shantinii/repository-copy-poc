
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import repository_copy_core as repo

TABLES = repo.EXPECTED_TABLES

source = {
    TABLES[0]: [(1,), (2,)],
    TABLES[1]: [(10,), (20,)],
    TABLES[2]: [(100,), (200,)],
}


def empty_destination():
    return {name: [] for name in TABLES}


print("TEST 1: Empty destination is accepted")
state = repo.validate_destination_state(source, empty_destination())
assert state == repo.DestinationState.EMPTY
print("PASS")


print("\nTEST 2: Exact destination match is accepted")
matching = {name: list(rows) for name, rows in source.items()}
state = repo.validate_destination_state(source, matching)
assert state == repo.DestinationState.EXACT_MATCH
print("PASS")


print("\nTEST 3: Partial destination is rejected")
partial = empty_destination()
partial[TABLES[0]] = [(1,)]

try:
    repo.validate_destination_state(source, partial)
except repo.DatasetValidationError:
    print("PASS: partial destination rejected")
else:
    raise AssertionError("Partial destination was accepted")


print("\nTEST 4: Conflicting destination is rejected")
conflicting = {name: list(rows) for name, rows in source.items()}
conflicting[TABLES[0]] = [(999,), (2,)]

try:
    repo.validate_destination_state(source, conflicting)
except repo.DatasetValidationError:
    print("PASS: conflicting destination rejected")
else:
    raise AssertionError("Conflicting destination was accepted")


print("\nAll four destination-state tests passed.")
