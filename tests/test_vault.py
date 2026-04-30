"""Tests for vault file I/O: atomic writes, JSON validation, staleness checks."""

import json
import os
import pytest
from pathlib import Path

from agents.data_collector import _atomic_write_json, _read_json, DataCollector


class TestAtomicWrite:
    def test_writes_valid_json(self, tmp_path):
        path = tmp_path / "test.json"
        data = {"key": "value", "number": 42}
        _atomic_write_json(path, data)
        assert path.exists()
        assert json.loads(path.read_text()) == data

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "nested" / "deep" / "test.json"
        _atomic_write_json(path, [1, 2, 3])
        assert path.exists()

    def test_overwrites_existing(self, tmp_path):
        path = tmp_path / "test.json"
        _atomic_write_json(path, {"v": 1})
        _atomic_write_json(path, {"v": 2})
        assert json.loads(path.read_text()) == {"v": 2}

    def test_no_partial_write_on_error(self, tmp_path):
        path = tmp_path / "test.json"
        _atomic_write_json(path, {"original": True})
        # Try to write non-serializable data
        with pytest.raises(TypeError):
            _atomic_write_json(path, {"bad": set()})
        # Original file should be intact
        assert json.loads(path.read_text()) == {"original": True}


class TestReadJson:
    def test_reads_valid_json(self, tmp_path):
        path = tmp_path / "test.json"
        path.write_text('{"hello": "world"}')
        assert _read_json(path) == {"hello": "world"}

    def test_raises_on_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            _read_json(tmp_path / "nope.json")

    def test_raises_on_empty_file(self, tmp_path):
        path = tmp_path / "empty.json"
        path.write_text("")
        with pytest.raises(ValueError, match="empty"):
            _read_json(path)

    def test_raises_on_invalid_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not valid json")
        with pytest.raises(ValueError, match="invalid JSON"):
            _read_json(path)

    def test_reads_array(self, tmp_path):
        path = tmp_path / "arr.json"
        path.write_text("[1, 2, 3]")
        assert _read_json(path) == [1, 2, 3]


class TestStalenessCheck:
    def test_detects_stale_file(self, tmp_vault):
        collector = DataCollector(brand="coulissehair")
        collector.vault_dir = tmp_vault
        # Make services.json old
        services_path = tmp_vault / "services.json"
        old_time = os.path.getmtime(str(services_path)) - (100 * 86400)  # 100 days ago
        os.utime(str(services_path), (old_time, old_time))
        result = collector._check_staleness()
        assert result["stale"]
        assert any("services.json" in w for w in result["warnings"])

    def test_detects_missing_file(self, tmp_path):
        vault = tmp_path / "vault" / "coulissehair"
        vault.mkdir(parents=True)
        (vault / "reviews.json").write_text("[]")
        collector = DataCollector(brand="coulissehair")
        collector.vault_dir = vault
        result = collector._check_staleness()
        assert result["stale"]
        assert any("missing" in w for w in result["warnings"])

    def test_detects_empty_reviews(self, tmp_vault):
        (tmp_vault / "reviews.json").write_text("[]")
        collector = DataCollector(brand="coulissehair")
        collector.vault_dir = tmp_vault
        result = collector._check_staleness()
        assert any("empty" in w for w in result["warnings"])

    def test_all_fresh(self, tmp_vault):
        collector = DataCollector(brand="coulissehair")
        collector.vault_dir = tmp_vault
        result = collector._check_staleness()
        # reviews.json has data, other files exist and are fresh
        assert not any("services" in w and "old" in w for w in result.get("warnings", []))
