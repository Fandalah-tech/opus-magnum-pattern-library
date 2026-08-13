from packages.opus_solver.ordered_chemistry import analyze_persistent_chemistry


PAIR = ("fire", "converted")


def _frame(cycle, *, element="fire", channels=(), normal=False, events=()):
    bonds = [
        {"fromAtomId": PAIR[0], "toAtomId": PAIR[1], "type": f"triplex-{channel}"}
        for channel in channels
    ]
    if normal:
        bonds.append({"fromAtomId": PAIR[0], "toAtomId": PAIR[1], "type": "normal"})
    return {
        "cycle": cycle,
        "phase": "after-instructions",
        "events": list(events),
        "world": {
            "atoms": [
                {"id": PAIR[0], "element": "fire", "position": [0, 0]},
                {"id": PAIR[1], "element": element, "position": [1, 0]},
            ],
            "bonds": bonds,
            "molecules": [{"atomIds": list(PAIR)}],
        },
    }


def _duplication_events():
    return [
        {
            "kind": "atom-duplicated",
            "cycle": 0,
            "sourceAtomId": PAIR[0],
            "transformedAtomId": PAIR[1],
            "toElement": "fire",
        },
        {
            "kind": "bond-removed",
            "cycle": 0,
            "fromAtomId": PAIR[0],
            "toAtomId": PAIR[1],
        },
    ]


def test_reversible_event_volume_does_not_count_as_persistent_progress():
    replay = {
        "frames": [
            _frame(0, element="salt", normal=True),
            _frame(1, channels=("red",), events=_duplication_events()),
            _frame(2, element="salt", normal=True),
            _frame(3, channels=("red",)),
        ],
    }

    progress = analyze_persistent_chemistry(replay, persistence_frames=2)

    assert progress["eventCounts"]["atom-duplicated"] == 1
    assert progress["eventCounts"]["bond-removed"] == 1
    assert progress["maxPersistentTriplexChannelCount"] == 0
    assert progress["hasPersistentCompleteTriplex"] is False
    assert progress["orderedStageCount"] == 0


def test_three_channels_on_the_same_pair_count_as_a_persistent_ordered_state():
    channels = ("black", "red", "yellow")
    replay = {
        "frames": [
            _frame(0, element="salt", normal=True),
            _frame(1, channels=channels, events=_duplication_events()),
            _frame(2, channels=channels),
            _frame(3, channels=channels),
        ],
    }

    progress = analyze_persistent_chemistry(replay, persistence_frames=2)

    assert progress["maxPersistentTriplexChannelCount"] == 3
    assert progress["hasPersistentCompleteTriplex"] is True
    assert progress["hasPersistentCalcifiedCompleteTriplex"] is False
    assert progress["orderedStageCount"] == 5
    assert progress["bestDuplicatedPair"]["persistentCompleteTriplexCycle"] == 1


def test_calcification_only_counts_after_complete_triplex_state_persists():
    channels = ("black", "red", "yellow")
    replay = {
        "frames": [
            _frame(0, element="salt", normal=True),
            _frame(1, channels=channels, events=_duplication_events()),
            _frame(2, channels=channels),
            _frame(
                3,
                element="salt",
                channels=channels,
                events=[
                    {
                        "kind": "atom-calcified",
                        "cycle": 2,
                        "atomId": PAIR[1],
                    },
                ],
            ),
            _frame(4, element="salt", channels=channels),
        ],
    }

    progress = analyze_persistent_chemistry(replay, persistence_frames=2)

    assert progress["hasPersistentCalcifiedCompleteTriplex"] is True
    assert progress["orderedStageCount"] == 6
    assert (
        progress["bestDuplicatedPair"]["persistentCalcifiedCompleteTriplexCycle"]
        == 3
    )
