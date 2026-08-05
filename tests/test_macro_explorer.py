from packages.opus_solver.macro_explorer import explore_simulator_macro_beam
from packages.opus_solver.mechanical_macros import MechanicalMacro


class FakeSimulator:
    def __init__(self, position=0):
        self.position = position

    def step(self, action):
        self.position += action.get("delta", 0)
        return {"phase": "complete"}


def test_macro_search_crosses_a_score_plateau(monkeypatch):
    monkeypatch.setattr(
        "packages.opus_solver.mechanical_macros.canonical_state_key",
        lambda simulator: (simulator.position,),
    )
    monkeypatch.setattr(
        "packages.opus_solver.macro_explorer.canonical_state_key",
        lambda simulator: (simulator.position,),
    )
    macros = (
        MechanicalMacro.from_actions(
            "confined-rotation",
            [{"delta": -1}, {"delta": 3}],
            tags={"rotation", "confined"},
        ),
        MechanicalMacro.from_actions(
            "nucleus-store-recover",
            [{"delta": -2}, {"delta": 3}],
            tags={"storage", "nucleus"},
        ),
    )

    result = explore_simulator_macro_beam(
        FakeSimulator(),
        macros,
        lambda simulator: simulator.position >= 3,
        lambda simulator: simulator.position,
        max_depth=2,
        beam_width=2,
    )

    assert result.found
    assert result.macros == ["confined-rotation", "nucleus-store-recover"]
    assert result.simulator.position == 3
    assert len(result.actions) == 4


def test_macro_search_reports_best_partial_state(monkeypatch):
    monkeypatch.setattr(
        "packages.opus_solver.mechanical_macros.canonical_state_key",
        lambda simulator: (simulator.position,),
    )
    monkeypatch.setattr(
        "packages.opus_solver.macro_explorer.canonical_state_key",
        lambda simulator: (simulator.position,),
    )
    macro = MechanicalMacro.from_actions("advance", [{"delta": 1}])

    result = explore_simulator_macro_beam(
        FakeSimulator(),
        (macro,),
        lambda simulator: simulator.position >= 5,
        lambda simulator: simulator.position,
        max_depth=2,
    )

    assert not result.found
    assert result.stopped_reason == "depth-limit"
    assert result.best_score == 2
    assert result.macros == ["advance", "advance"]
