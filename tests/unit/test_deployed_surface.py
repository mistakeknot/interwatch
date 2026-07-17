"""Unit tests for deployed-surface signal evaluators (mk-nhx).

Network is never touched: tests pre-seed scan_module._surface_cache
(the per-run fetch cache) or set INTERWATCH_OFFLINE. The offline
posture under test: network-level failure (status 0) is "cannot
check", never drift; an HTTP answer (404/empty) IS drift.
"""

import json
import os

import pytest


@pytest.fixture(autouse=True)
def clean_surface_state(scan_module):
    """Isolate the module-level fetch cache and notes between tests."""
    scan_module._surface_cache.clear()
    scan_module._surface_notes.clear()
    yield
    scan_module._surface_cache.clear()
    scan_module._surface_notes.clear()


URL = "https://example.test/llms.txt"


def _watchable(**over):
    w = {"name": "deployed-llms", "path": "src/pages/llms.txt.ts", "url": URL}
    w.update(over)
    return w


# ─── eval_deployed_surface_unreachable ───────────────────────────────


def test_unreachable_no_url_is_zero(scan_module):
    assert scan_module.eval_deployed_surface_unreachable({"name": "x", "path": "p"}, {}) == 0


def test_unreachable_network_failure_is_not_drift(scan_module):
    scan_module._surface_cache[URL] = (0, "")
    assert scan_module.eval_deployed_surface_unreachable(_watchable(), {}) == 0


def test_unreachable_404_is_drift(scan_module):
    scan_module._surface_cache[URL] = (404, "")
    assert scan_module.eval_deployed_surface_unreachable(_watchable(), {}) == 1


def test_unreachable_200_empty_body_is_drift(scan_module):
    scan_module._surface_cache[URL] = (200, "   \n")
    assert scan_module.eval_deployed_surface_unreachable(_watchable(), {}) == 1


def test_unreachable_200_with_body_is_green(scan_module):
    scan_module._surface_cache[URL] = (200, "# llms.txt\n")
    assert scan_module.eval_deployed_surface_unreachable(_watchable(), {}) == 0


def test_offline_env_skips_fetch_with_note(scan_module, monkeypatch):
    monkeypatch.setenv("INTERWATCH_OFFLINE", "1")
    status, body = scan_module._fetch_surface("https://never-fetched.test/x")
    assert status == 0
    assert any("INTERWATCH_OFFLINE" in n for n in scan_module._surface_notes)


# ─── eval_deployed_provenance_drift ──────────────────────────────────


def _recorded(tmp_path, monkeypatch, sha):
    """Point STATE_DIR-relative deploy-state.json at tmp_path."""
    monkeypatch.chdir(tmp_path)
    os.makedirs(".interwatch", exist_ok=True)
    with open(".interwatch/deploy-state.json", "w") as f:
        json.dump({"sha": sha}, f)


def test_provenance_missing_stamp_is_drift(scan_module, tmp_path, monkeypatch):
    _recorded(tmp_path, monkeypatch, "abc1234")
    scan_module._surface_cache[URL] = (200, "# llms.txt — no provenance here\n")
    sig = {"type": "deployed_provenance_drift", "expect": "recorded"}
    assert scan_module.eval_deployed_provenance_drift(_watchable(), sig) == 1


def test_provenance_match_full_vs_short_prefix(scan_module, tmp_path, monkeypatch):
    _recorded(tmp_path, monkeypatch, "abc1234def5678900000000000000000000000ff")
    scan_module._surface_cache[URL] = (200, "source: gsvdotcom@abc1234\n")
    sig = {"type": "deployed_provenance_drift", "expect": "recorded"}
    assert scan_module.eval_deployed_provenance_drift(_watchable(), sig) == 0


def test_provenance_mismatch_is_drift(scan_module, tmp_path, monkeypatch):
    _recorded(tmp_path, monkeypatch, "abc1234")
    scan_module._surface_cache[URL] = (200, "source: gsvdotcom@deadbee\n")
    sig = {"type": "deployed_provenance_drift", "expect": "recorded"}
    assert scan_module.eval_deployed_provenance_drift(_watchable(), sig) == 1


def test_provenance_recorded_state_missing_skips_with_note(scan_module, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no .interwatch/deploy-state.json here
    scan_module._surface_cache[URL] = (200, "source: gsvdotcom@abc1234\n")
    sig = {"type": "deployed_provenance_drift", "expect": "recorded"}
    assert scan_module.eval_deployed_provenance_drift(_watchable(), sig) == 0
    assert any("expect=recorded" in n for n in scan_module._surface_notes)


def test_provenance_non_200_defers_to_unreachable_signal(scan_module):
    scan_module._surface_cache[URL] = (404, "")
    assert scan_module.eval_deployed_provenance_drift(_watchable(), {}) == 0


def test_provenance_custom_pattern(scan_module, tmp_path, monkeypatch):
    _recorded(tmp_path, monkeypatch, "abc1234")
    scan_module._surface_cache[URL] = (200, "<!-- build abc1234 -->")
    sig = {"provenance_pattern": r"build ([0-9a-f]{7,40})", "expect": "recorded"}
    assert scan_module.eval_deployed_provenance_drift(_watchable(), sig) == 0


# ─── eval_deployed_jsonld_invalid ────────────────────────────────────


def _page(*blocks):
    scripts = "".join(
        f'<script type="application/ld+json">{b}</script>' for b in blocks)
    return f"<html><head>{scripts}</head><body>x</body></html>"


def test_jsonld_zero_blocks_on_registered_surface_is_drift(scan_module):
    scan_module._surface_cache[URL] = (200, "<html><body>no ld</body></html>")
    assert scan_module.eval_deployed_jsonld_invalid(_watchable(), {}) == 1


def test_jsonld_valid_with_id_is_green(scan_module):
    block = json.dumps({"@context": "https://schema.org", "@id": "https://x/#GSV-C2", "@type": "SoftwareApplication"})
    scan_module._surface_cache[URL] = (200, _page(block))
    assert scan_module.eval_deployed_jsonld_invalid(_watchable(), {}) == 0


def test_jsonld_parse_error_counts(scan_module):
    scan_module._surface_cache[URL] = (200, _page('{"@id": broken'))
    assert scan_module.eval_deployed_jsonld_invalid(_watchable(), {}) == 1


def test_jsonld_graph_node_missing_id_counts(scan_module):
    block = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@id": "https://x/#a", "@type": "Thing"},
        {"@type": "Thing"},  # missing @id
    ]})
    scan_module._surface_cache[URL] = (200, _page(block))
    assert scan_module.eval_deployed_jsonld_invalid(_watchable(), {}) == 1


def test_jsonld_multiple_blocks_count_independently(scan_module):
    good = json.dumps({"@id": "https://x/#a", "@type": "Thing"})
    bad = json.dumps({"@type": "Thing"})
    scan_module._surface_cache[URL] = (200, _page(good, bad, "not json"))
    assert scan_module.eval_deployed_jsonld_invalid(_watchable(), {}) == 2


# ─── dispatch integration through scan_watchable ─────────────────────


def test_scan_watchable_provenance_drift_is_deterministic_certain(scan_module, tmp_path, monkeypatch):
    _recorded(tmp_path, monkeypatch, "abc1234")
    scan_module._surface_cache[URL] = (200, "# llms.txt\nsource: gsvdotcom@deadbee\n")
    w = _watchable(signals=[
        {"type": "deployed_surface_unreachable", "weight": 3},
        {"type": "deployed_provenance_drift", "weight": 3, "expect": "recorded"},
    ], staleness_days=0)
    result = scan_module.scan_watchable(w)
    assert result["signals"]["deployed_provenance_drift"]["count"] == 1
    assert result["signals"]["deployed_surface_unreachable"]["count"] == 0
    assert result["confidence"] == "Certain"


def test_scan_watchable_healthy_surface_is_green(scan_module, tmp_path, monkeypatch):
    _recorded(tmp_path, monkeypatch, "abc1234")
    scan_module._surface_cache[URL] = (200, "# llms.txt\nsource: gsvdotcom@abc1234\n")
    w = _watchable(signals=[
        {"type": "deployed_surface_unreachable", "weight": 3},
        {"type": "deployed_provenance_drift", "weight": 3, "expect": "recorded"},
    ], staleness_days=0)
    result = scan_module.scan_watchable(w)
    assert result["score"] == 0
    assert result["confidence"] == "Green"
