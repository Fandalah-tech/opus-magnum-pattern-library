from packages.opus_engine import ArmState, Atom, Simulator, World
from packages.opus_solver.beam_explorer import _immediately_reverses
from packages.opus_solver.explorer import enumerate_joint_actions, explore_simulator_states


def test_joint_action_enumeration_omits_all_idle_by_default() -> None:
    actions = enumerate_joint_actions({
        "a": (None, "grab"),
        "b": (None, "rotate_cw"),
    })

    assert {} not in actions
    assert actions == [
        {"b": "rotate_cw"},
        {"a": "grab"},
        {"a": "grab", "b": "rotate_cw"},
    ]


def test_immediate_inverse_pruning_only_removes_exact_kinematic_undo() -> None:
    assert _immediately_reverses({"a": "rotate_cw"}, {"a": "rotate_ccw"})
    assert _immediately_reverses(
        {"a": "extend", "b": "track_plus"},
        {"a": "retract", "b": "track_minus"},
    )
    assert not _immediately_reverses({"a": "grab"}, {"a": "drop"})
    assert not _immediately_reverses({"a": "rotate_cw"}, {"b": "rotate_ccw"})
    assert not _immediately_reverses(
        {"a": "extend", "b": "track_plus"},
        {"a": "retract"},
    )


def test_explorer_finds_simple_grab_and_rotation_sequence() -> None:
    world = World()
    world.add_atom(Atom("target", "salt", (1, 0)))
    simulator = Simulator(
        world,
        {"arm": ArmState("arm", "arm1", (0, 0), 0, 1)},
    )

    result = explore_simulator_states(
        simulator,
        {"arm": (None, "grab", "rotate_ccw")},
        lambda state: state.world.atoms["target"].position == (0, 1),
        max_depth=3,
    )

    assert result.found is True
    assert result.actions == [
        {"arm": "grab"},
        {"arm": "rotate_ccw"},
    ]
    assert result.depth == 2
    assert result.simulator is not None


def test_explorer_rejects_collision_paths_and_reports_exhaustion() -> None:
    world = World()
    world.add_atom(Atom("target", "salt", (1, 0)))
    world.add_atom(Atom("blocker", "water", (0, 1)))
    simulator = Simulator(
        world,
        {"arm": ArmState("arm", "arm1", (0, 0), 0, 1)},
    )

    result = explore_simulator_states(
        simulator,
        {"arm": (None, "grab", "rotate_ccw")},
        lambda state: state.world.atoms["target"].position == (0, 1),
        max_depth=3,
    )

    assert result.found is False
    assert result.stopped_reason == "exhausted"


def test_explorer_preserves_disjoint_components_during_search() -> None:
    world = World()
    world.add_atom(Atom("moving", "salt", (1, 0)))
    world.add_atom(Atom("remote", "salt", (4, 0)))
    simulator = Simulator(
        world,
        {"arm": ArmState("arm", "arm1", (0, 0), 0, 1)},
    )

    result = explore_simulator_states(
        simulator,
        {"arm": (None, "grab", "rotate_ccw")},
        lambda state: state.world.atoms["moving"].position == (0, 1),
        max_depth=3,
    )

    assert result.found is True
    assert result.simulator.world.atoms["remote"].position == (4, 0)
