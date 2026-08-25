from foremanctl import FEATURE_MAP
from foremanctl import conflicting_features
from foremanctl import foreman_plugins
from foremanctl import resolved_features


def _asymmetric_conflicts():
    errors = []
    for feature, meta in FEATURE_MAP.items():
        for conflict in meta.get('conflicts', []):
            if conflict not in FEATURE_MAP:
                errors.append(f"{feature} declares conflict with unknown feature {conflict}")
            elif feature not in FEATURE_MAP.get(conflict, {}).get('conflicts', []):
                errors.append(f"{feature} declares conflict with {conflict}, but {conflict} does not declare conflict with {feature}")
    return errors


def test_no_conflicts():
    assert conflicting_features(['foreman', 'hammer']) == []


def test_detects_conflict(monkeypatch):
    monkeypatch.setitem(FEATURE_MAP, 'test-a', {'conflicts': ['test-b']})
    monkeypatch.setitem(FEATURE_MAP, 'test-b', {'conflicts': ['test-a']})
    result = conflicting_features(['test-a', 'test-b'])
    assert len(result) == 1
    assert 'test-a conflicts with test-b' in result


def test_deduplicates_conflict_pairs(monkeypatch):
    monkeypatch.setitem(FEATURE_MAP, 'test-a', {'conflicts': ['test-b']})
    monkeypatch.setitem(FEATURE_MAP, 'test-b', {'conflicts': ['test-a']})
    result = conflicting_features(['test-b', 'test-a'])
    assert len(result) == 1


def test_no_conflict_when_only_one_present(monkeypatch):
    monkeypatch.setitem(FEATURE_MAP, 'test-a', {'conflicts': ['test-b']})
    monkeypatch.setitem(FEATURE_MAP, 'test-b', {'conflicts': ['test-a']})
    assert conflicting_features(['test-a', 'foreman']) == []


def test_no_asymmetric_conflicts_in_features_yaml():
    errors = _asymmetric_conflicts()
    assert errors == [], f"Asymmetric conflicts found: {errors}"


def test_asymmetric_conflict_detected(monkeypatch):
    monkeypatch.setitem(FEATURE_MAP, 'test-a', {'conflicts': ['test-b']})
    monkeypatch.setitem(FEATURE_MAP, 'test-b', {})
    errors = _asymmetric_conflicts()
    assert any('test-a declares conflict with test-b' in e for e in errors)


def test_conflict_with_unknown_feature_detected(monkeypatch):
    monkeypatch.setitem(FEATURE_MAP, 'test-a', {'conflicts': ['nonexistent']})
    errors = _asymmetric_conflicts()
    assert any('unknown feature nonexistent' in e for e in errors)


def test_resolved_features_is_sorted(monkeypatch):
    monkeypatch.setitem(FEATURE_MAP, 'test-a', {'dependencies': ['test-c', 'test-b']})
    monkeypatch.setitem(FEATURE_MAP, 'test-b', {})
    monkeypatch.setitem(FEATURE_MAP, 'test-c', {})
    result = resolved_features(['test-a'])
    assert result == sorted(result)


def test_resolved_features_deduplicates_requested_and_dependency(monkeypatch):
    monkeypatch.setitem(FEATURE_MAP, 'test-a', {'dependencies': ['test-b']})
    monkeypatch.setitem(FEATURE_MAP, 'test-b', {})
    result = resolved_features(['test-b', 'test-a'])
    assert result.count('test-b') == 1


def test_foreman_plugins_does_not_duplicate_plugin_for_requested_dependency(monkeypatch):
    monkeypatch.setitem(FEATURE_MAP, 'test-a', {'dependencies': ['test-b'], 'foreman': {'plugin_name': 'plugin_a'}})
    monkeypatch.setitem(FEATURE_MAP, 'test-b', {'foreman': {'plugin_name': 'plugin_b'}})
    result = foreman_plugins(['test-b', 'test-a'])
    assert result.count('plugin_b') == 1
