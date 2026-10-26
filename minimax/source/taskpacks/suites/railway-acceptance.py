"""Hidden acceptance suite for the railway taskpacks.

Injected by the run_eval harness into the workspace only AFTER the agent's
diff is captured (it grades, it never leaks into the prompt). Shared by all
three railway tiers: every tier must deliver the same adjust_departure
interface without regressing the legacy behavior.
"""

from api import submit_adjust_departure
from occupancy import Occupation
from publish import can_publish
from schedule import Train, adjust_departure, arrival_times


def _train() -> Train:
    return Train(train_id="K1", start="08:00", legs={"A->B": 10, "B->C": 15})


def test_adjust_shifts_whole_timetable() -> None:
    after = arrival_times(adjust_departure(_train(), "08:30"))
    assert after == {"A": "08:30", "B": "08:40", "C": "08:55"}


def test_api_entry_returns_adjusted_times() -> None:
    assert submit_adjust_departure(_train(), "09:00")["C"] == "09:25"


def test_adjusted_train_still_blocked_on_conflict() -> None:
    adjusted = adjust_departure(_train(), "08:05")
    ok, _ = can_publish(adjusted, [Occupation("K1", 486, 494)])
    assert not ok
