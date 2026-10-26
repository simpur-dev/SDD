import importlib
import sys
from pathlib import Path

work = Path(sys.argv[1])
sys.path.insert(0, str(work / "src"))

api = importlib.import_module("api")
schedule = importlib.import_module("schedule")
occupancy = importlib.import_module("occupancy")
publish = importlib.import_module("publish")
Occupation = occupancy.Occupation
can_publish = publish.can_publish

failures = []


def check(name, fn):
    try:
        fn()
        print(f"PASS {name}")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"{name}: {type(exc).__name__}: {exc}")
        print(f"FAIL {name}: {type(exc).__name__}: {exc}")


def test_exists():
    assert callable(getattr(schedule, "adjust_departure", None)), (
        "schedule.adjust_departure is missing"
    )


def test_api_exists():
    assert callable(getattr(api, "submit_adjust_departure", None)), (
        "api.submit_adjust_departure is missing"
    )


def test_shift():
    train = schedule.Train(train_id="K1", start="08:00", legs={"A->B": 10, "B->C": 15})
    after = schedule.arrival_times(schedule.adjust_departure(train, "08:30"))
    assert after == {"A": "08:30", "B": "08:40", "C": "08:55"}, after


def test_api():
    train = schedule.Train(train_id="K1", start="08:00", legs={"A->B": 10, "B->C": 15})
    assert api.submit_adjust_departure(train, "09:00")["C"] == "09:25"


def test_conflict():
    train = schedule.Train(train_id="K1", start="08:00", legs={"A->B": 10, "B->C": 15})
    adjusted = schedule.adjust_departure(train, "08:05")
    ok, _ = can_publish(adjusted, [Occupation("K1", 486, 494)])
    assert not ok


for name, fn in [
    ("exists", test_exists),
    ("api_exists", test_api_exists),
    ("shift", test_shift),
    ("api", test_api),
    ("conflict", test_conflict),
]:
    check(name, fn)
print("TARGET_RESULT", "PASS" if not failures else "FAIL")
sys.exit(0 if not failures else 1)