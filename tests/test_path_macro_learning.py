from packages.opus_solver import learn_action_windows


def test_learns_distinct_contiguous_windows_and_retains_idle_frames():
    actions = [
        {"arm-a": "grab"},
        {},
        {"arm-a": "rotate_cw", "arm-b": "pivot_ccw"},
        {"arm-a": "drop"},
    ]

    macros = learn_action_windows(actions, lengths=(2, 3), tag="rotor-path")

    assert [macro.name for macro in macros] == [
        "rotor-path-000-001",
        "rotor-path-001-002",
        "rotor-path-002-003",
        "rotor-path-000-002",
        "rotor-path-001-003",
    ]
    assert macros[0].actions[1] == {}
    assert macros[1].actions[1] == {
        "arm-a": "rotate_cw",
        "arm-b": "pivot_ccw",
    }
    assert {"trajectory", "mechanical", "length-3"} <= macros[-1].tags


def test_deduplicates_identical_motion_windows():
    actions = [
        {"arm": "rotate_cw"},
        {"arm": "rotate_ccw"},
        {"arm": "rotate_cw"},
        {"arm": "rotate_ccw"},
    ]

    macros = learn_action_windows(actions, lengths=(2,))

    assert len(macros) == 2
    assert [macro.actions for macro in macros] == [
        ({"arm": "rotate_cw"}, {"arm": "rotate_ccw"}),
        ({"arm": "rotate_ccw"}, {"arm": "rotate_cw"}),
    ]


def test_empty_or_oversized_windows_produce_no_macros():
    assert learn_action_windows([], lengths=(2,)) == ()
    assert learn_action_windows([{"arm": "grab"}], lengths=(2, 3)) == ()
