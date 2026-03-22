"""Tests for MetadataReader helper."""

import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from kopi_docka.helpers.metadata_reader import MetadataReader
from kopi_docka.types import BackupMetadata

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "metadata"


@pytest.fixture
def metadata_dir(tmp_path):
    """Copy fixture metadata files to a temp directory."""
    dest = tmp_path / "metadata"
    shutil.copytree(FIXTURES_DIR, dest)
    return dest


@pytest.fixture
def empty_dir(tmp_path):
    """Empty metadata directory."""
    d = tmp_path / "metadata"
    d.mkdir()
    return d


class TestMetadataReader:
    def test_read_all_returns_sorted_newest_first(self, metadata_dir):
        reader = MetadataReader(metadata_dir)
        results = reader.read_all()
        # corrupt_file.json is skipped, so 4 valid entries
        assert len(results) == 4
        # Newest first
        assert results[0].timestamp > results[-1].timestamp

    def test_read_all_empty_directory(self, empty_dir):
        reader = MetadataReader(empty_dir)
        results = reader.read_all()
        assert results == []

    def test_read_all_nonexistent_directory(self, tmp_path):
        reader = MetadataReader(tmp_path / "does_not_exist")
        results = reader.read_all()
        assert results == []

    def test_read_all_skips_corrupt_files(self, metadata_dir):
        reader = MetadataReader(metadata_dir)
        results = reader.read_all()
        # 5 files total, 1 corrupt → 4 valid
        assert len(results) == 4
        unit_names = [m.unit_name for m in results]
        assert "traefik" in unit_names
        assert "nextcloud" in unit_names

    def test_filter_by_unit_name(self, metadata_dir):
        reader = MetadataReader(metadata_dir)
        results = reader.read_all(unit_name="traefik")
        assert len(results) == 2
        assert all(m.unit_name == "traefik" for m in results)

    def test_filter_only_failed(self, metadata_dir):
        reader = MetadataReader(metadata_dir)
        results = reader.read_all(only_failed=True)
        assert len(results) == 1
        assert results[0].success is False
        assert results[0].unit_name == "nextcloud"

    def test_filter_since(self, metadata_dir):
        reader = MetadataReader(metadata_dir)
        since = datetime(2026, 2, 13, 0, 0, 0)
        results = reader.read_all(since=since)
        assert len(results) == 2
        assert all(m.timestamp >= since for m in results)

    def test_filter_limit(self, metadata_dir):
        reader = MetadataReader(metadata_dir)
        results = reader.read_all(limit=2)
        assert len(results) == 2

    def test_combined_filters(self, metadata_dir):
        reader = MetadataReader(metadata_dir)
        results = reader.read_all(unit_name="traefik", limit=1)
        assert len(results) == 1
        assert results[0].unit_name == "traefik"

    def test_read_latest(self, metadata_dir):
        reader = MetadataReader(metadata_dir)
        latest = reader.read_latest()
        assert latest is not None
        # Newest entry is nextcloud at 2026-02-13 03:01:00
        assert latest.unit_name == "nextcloud"
        assert latest.timestamp == datetime(2026, 2, 13, 3, 1, 0)

    def test_read_latest_for_unit(self, metadata_dir):
        reader = MetadataReader(metadata_dir)
        latest = reader.read_latest(unit_name="traefik")
        assert latest is not None
        assert latest.unit_name == "traefik"
        assert latest.timestamp == datetime(2026, 2, 13, 3, 0, 0)

    def test_read_latest_empty(self, empty_dir):
        reader = MetadataReader(empty_dir)
        assert reader.read_latest() is None

    def test_get_unit_names(self, metadata_dir):
        reader = MetadataReader(metadata_dir)
        names = reader.get_unit_names()
        assert names == ["nextcloud", "traefik"]

    def test_get_unit_names_empty(self, empty_dir):
        reader = MetadataReader(empty_dir)
        assert reader.get_unit_names() == []


class TestBackupMetadataFromDict:
    def test_full_dict(self):
        data = {
            "unit_name": "traefik",
            "timestamp": "2026-02-13T03:00:00",
            "duration_seconds": 45.2,
            "backup_id": "abc-123",
            "success": True,
            "error_message": None,
            "kopia_snapshot_ids": ["snap1"],
            "volumes_backed_up": 2,
            "databases_backed_up": 0,
            "errors": [],
            "backup_scope": "standard",
            "networks_backed_up": 1,
            "docker_config_backed_up": False,
            "hooks_executed": ["pre_backup"],
            "backup_format": "direct",
        }
        meta = BackupMetadata.from_dict(data)
        assert meta.unit_name == "traefik"
        assert meta.timestamp == datetime(2026, 2, 13, 3, 0, 0)
        assert meta.duration_seconds == 45.2
        assert meta.backup_id == "abc-123"
        assert meta.kopia_snapshot_ids == ["snap1"]

    def test_minimal_dict(self):
        data = {
            "unit_name": "test",
            "timestamp": "2026-01-01T00:00:00",
            "backup_id": "id-1",
        }
        meta = BackupMetadata.from_dict(data)
        assert meta.unit_name == "test"
        assert meta.duration_seconds == 0.0
        assert meta.success is True
        assert meta.backup_scope == "standard"
        assert meta.backup_format == "direct"

    def test_roundtrip(self):
        original = BackupMetadata(
            unit_name="roundtrip",
            timestamp=datetime(2026, 3, 1, 12, 0, 0),
            duration_seconds=99.9,
            backup_id="rt-id",
            success=False,
            error_message="test error",
            errors=["err1", "err2"],
        )
        data = original.to_dict()
        restored = BackupMetadata.from_dict(data)
        assert restored.unit_name == original.unit_name
        assert restored.timestamp == original.timestamp
        assert restored.duration_seconds == original.duration_seconds
        assert restored.success == original.success
        assert restored.error_message == original.error_message
        assert restored.errors == original.errors
