from packages.opus_solver.repair_policy import recommend_repair_order


def _route(validation, layout=None, temporal=True, geometry=True):
    return recommend_repair_order(
        validation,
        layout or {},
        temporal_enabled=temporal,
        geometric_enabled=geometry,
    )


def test_blocked_input_routes_geometry_first():
    result = _route({
        "failureMode": "blocked-input-at-start",
        "blockedInputsAtStart": ["input-b"],
    })
    assert result["order"] == ["geometry", "timing"]
    assert "blocked-input-at-start" in result["geometrySignals"]


def test_exact_static_conflict_routes_geometry_first():
    result = _route(
        {"failureMode": "no-product-delivered"},
        {"exactStaticConflictCount": 2},
    )
    assert result["order"] == ["geometry", "timing"]
    assert "exact-static-footprint-conflict" in result["geometrySignals"]


def test_collision_engine_error_routes_geometry_first():
    result = _route({
        "failureMode": "simulation-error",
        "firstError": {"message": "Atom a collides with stationary atom b at (2, 1)"},
    })
    assert result["order"] == ["geometry", "timing"]
    assert "collision-like-engine-error" in result["geometrySignals"]


def test_no_delivery_without_geometry_signal_routes_timing_first():
    result = _route({"failureMode": "no-product-delivered"})
    assert result["order"] == ["timing", "geometry"]


def test_insufficient_delivery_routes_timing_first():
    result = _route({"failureMode": "insufficient-product-delivery", "totalDelivered": 2})
    assert result["order"] == ["timing", "geometry"]


def test_disabled_preferred_search_falls_back_to_available_repair():
    result = _route(
        {"failureMode": "blocked-input-at-start", "blockedInputsAtStart": ["input-b"]},
        temporal=True,
        geometry=False,
    )
    assert result["preferred"] == "geometry"
    assert result["order"] == ["timing"]


def test_no_enabled_search_returns_empty_route():
    result = _route({"failureMode": "no-product-delivered"}, temporal=False, geometry=False)
    assert result["order"] == []
