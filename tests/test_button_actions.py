from types import SimpleNamespace

from tink_agent.button_actions import (
    slot_number, catalog_index_of, ButtonActionsController,
)
from tink_agent.actions import ACTION_CATALOG


def test_slot_number_maps_bank_and_button_to_1_to_8():
    assert slot_number(0, 0) == 1     # Bank A, button 1
    assert slot_number(0, 3) == 4     # Bank A, button 4
    assert slot_number(1, 0) == 5     # Bank B, button 1
    assert slot_number(1, 3) == 8     # Bank B, button 4


def test_catalog_index_roundtrips():
    for i, a in enumerate(ACTION_CATALOG):
        assert catalog_index_of(a["id"]) == i


def test_catalog_index_unknown_falls_back_to_noop_entry():
    noop_i = next(i for i, a in enumerate(ACTION_CATALOG) if a["id"] == "noop")
    assert catalog_index_of("nope") == noop_i


def test_apply_action_index_calls_delegate_with_slot_number_and_id():
    calls = []
    fake_app = SimpleNamespace(set_slot_action=lambda n, a: calls.append((n, a)))
    # Build a controller without its AppKit window (plain init, then inject state).
    c = ButtonActionsController.alloc().init()
    c.app = fake_app
    c._mode_index = 1
    c._slot_index = 2                 # -> slot_number(1, 2) == 7
    enter_i = catalog_index_of("enter")
    c._apply_action_index(enter_i)
    assert calls == [(7, "enter")]
