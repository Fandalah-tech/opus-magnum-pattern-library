from packages.opus_solver.mechanical_macros import (
    MechanicalMacro,
    apply_mechanical_macro,
    enumerate_macro_successors,
    select_macros,
)


class FakeSimulator:
    def __init__(self, position=0):
        self.position = position

    def step(self, action):
        delta = action.get("arm")
        if delta == "plus":
            self.position += 1
        elif delta == "minus":
            self.position -= 1
        elif delta == "crash":
            return {"phase": "error"}
        return {"phase": "complete"}


def test_macro_application_is_atomic_and_does_not_mutate_input(monkeypatch):
    monkeypatch.setattr(
        "packages.opus_solver.mechanical_macros.canonical_state_key",
        lambda simulator: (simulator.position,),
    )
    simulator = FakeSimulator()
    macro = MechanicalMacro.from_actions(
        "confined-rotation",
        [{"arm": "plus"}, {"arm": "plus"}, {"arm": "minus"}],
        tags={"rotation", "confined"},
    )

    applied = apply_mechanical_macro(simulator, macro)

    assert simulator.position == 0
    assert applied is not None
    assert applied.simulator.position == 1
    assert len(applied.actions) == 3


def test_invalid_macro_is_rejected_as_a_whole():
    simulator = FakeSimulator()
    macro = MechanicalMacro.from_actions(
        "unsafe",
        [{"arm": "plus"}, {"arm": "crash"}, {"arm": "plus"}],
    )

    assert apply_mechanical_macro(simulator, macro) is None
    assert simulator.position == 0


def test_successors_are_deduplicated_by_resulting_state(monkeypatch):
    monkeypatch.setattr(
        "packages.opus_solver.mechanical_macros.canonical_state_key",
        lambda simulator: (simulator.position,),
    )
    macros = (
        MechanicalMacro.from_actions("direct", [{"arm": "plus"}]),
        MechanicalMacro.from_actions(
            "detour",
            [{"arm": "plus"}, {"arm": "plus"}, {"arm": "minus"}],
        ),
    )

    successors = enumerate_macro_successors(FakeSimulator(), macros)

    assert [successor.macro.name for successor in successors] == ["direct"]


def test_macro_selection_supports_mechanical_vocabulary():
    macros = (
        MechanicalMacro.from_actions(
            "confined-rotation",
            [{"arm": "plus"}],
            tags={"rotation", "confined"},
        ),
        MechanicalMacro.from_actions(
            "nucleus-store",
            [{"arm": "minus"}],
            tags={"storage", "nucleus"},
        ),
    )

    assert [macro.name for macro in select_macros(macros, required_tags={"storage"})] == [
        "nucleus-store"
    ]
