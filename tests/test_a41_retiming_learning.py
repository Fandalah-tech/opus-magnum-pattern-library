from tools.analyze_a41_retiming_results import summarize


def test_summarize_ranks_improving_instruction_groups_first():
    data = {
        "baselineCycles": 1112,
        "rounds": [
            {"candidates": [
                {"shift": {"part": "part-1", "instruction": "rotate_cw", "cycle": 100}, "valid": True, "cycles": 1108},
                {"shift": {"part": "part-1", "instruction": "rotate_cw", "cycle": 120}, "valid": True, "cycles": 1112},
                {"shift": {"part": "part-9", "instruction": "grab", "cycle": 140}, "valid": False, "cycles": None},
            ]}
        ],
    }

    result = summarize(data)
    assert result["observations"] == 3
    assert result["byPartInstruction"][0]["part"] == "part-1"
    assert result["byPartInstruction"][0]["instruction"] == "rotate_cw"
    assert result["byPartInstruction"][0]["improved"] == 1
    assert result["byPartInstruction"][0]["bestCycles"] == 1108
