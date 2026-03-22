"""Tests for history CLI command."""

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import typer
from typer.testing import CliRunner

from kopi_docka.commands.history_commands import register, _format_duration, _format_snapshot_ids

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "metadata"

runner = CliRunner()


@pytest.fixture
def app_with_history(tmp_path):
    """Create a Typer app with history command and test metadata."""
    app = typer.Typer()

    # Copy fixtures to tmp metadata dir
    metadata_dir = tmp_path / "metadata"
    shutil.copytree(FIXTURES_DIR, metadata_dir)

    # Mock config
    cfg = MagicMock()
    cfg.backup_base_path = tmp_path

    @app.callback()
    def init(ctx: typer.Context):
        ctx.ensure_object(dict)
        ctx.obj["config"] = cfg

    register(app)
    return app


@pytest.fixture
def app_no_config():
    """Create a Typer app with history command but no config."""
    app = typer.Typer()

    @app.callback()
    def init(ctx: typer.Context):
        ctx.ensure_object(dict)
        ctx.obj["config"] = None

    register(app)
    return app


@pytest.fixture
def app_empty_metadata(tmp_path):
    """Create a Typer app with empty metadata directory."""
    app = typer.Typer()
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()

    cfg = MagicMock()
    cfg.backup_base_path = tmp_path

    @app.callback()
    def init(ctx: typer.Context):
        ctx.ensure_object(dict)
        ctx.obj["config"] = cfg

    register(app)
    return app


class TestHistoryCommand:
    def test_shows_table(self, app_with_history):
        result = runner.invoke(app_with_history, ["history"])
        assert result.exit_code == 0
        assert "Backup History" in result.output
        assert "traefik" in result.output
        assert "nextcloud" in result.output

    def test_filter_by_unit(self, app_with_history):
        result = runner.invoke(app_with_history, ["history", "--unit", "traefik"])
        assert result.exit_code == 0
        assert "traefik" in result.output
        # nextcloud should not appear as unit column value
        # (it might appear in the header/footer, but not as a row)
        lines = [l for l in result.output.split("\n") if "nextcloud" in l.lower()]
        assert len(lines) == 0

    def test_filter_failed(self, app_with_history):
        result = runner.invoke(app_with_history, ["history", "--failed"])
        assert result.exit_code == 0
        assert "nextcloud" in result.output

    def test_filter_last(self, app_with_history):
        result = runner.invoke(app_with_history, ["history", "--last", "2"])
        assert result.exit_code == 0
        assert "Backup History" in result.output

    def test_filter_since(self, app_with_history):
        result = runner.invoke(app_with_history, ["history", "--since", "2026-02-13"])
        assert result.exit_code == 0
        assert "2026-02-13" in result.output

    def test_invalid_since_format(self, app_with_history):
        result = runner.invoke(app_with_history, ["history", "--since", "not-a-date"])
        assert result.exit_code == 1
        assert "Invalid date format" in result.output

    def test_no_config(self, app_no_config):
        result = runner.invoke(app_no_config, ["history"])
        assert result.exit_code == 1
        assert "No configuration found" in result.output

    def test_empty_metadata(self, app_empty_metadata):
        result = runner.invoke(app_empty_metadata, ["history"])
        assert result.exit_code == 0
        assert "No backup history found" in result.output

    def test_success_status_marker(self, app_with_history):
        result = runner.invoke(app_with_history, ["history"])
        assert "✓" in result.output

    def test_failed_status_marker(self, app_with_history):
        result = runner.invoke(app_with_history, ["history", "--failed"])
        assert "✗" in result.output

    def test_detail_flag(self, app_with_history):
        result = runner.invoke(app_with_history, ["history", "--detail"])
        assert result.exit_code == 0
        # Detail panels show all fields
        assert "Backup ID" in result.output
        assert "Hooks executed" in result.output
        assert "Snapshot IDs" in result.output

    def test_detail_with_unit_filter(self, app_with_history):
        result = runner.invoke(app_with_history, ["history", "--detail", "--unit", "traefik"])
        assert result.exit_code == 0
        assert "traefik" in result.output

    def test_detail_shows_failed_errors(self, app_with_history):
        result = runner.invoke(app_with_history, ["history", "--detail", "--failed"])
        assert result.exit_code == 0
        assert "Failed" in result.output
        assert "permission denied" in result.output

    def test_id_lookup(self, app_with_history):
        result = runner.invoke(
            app_with_history,
            ["history", "--id", "a1b2c3d4-e5f6-7890-abcd-ef1234567890"],
        )
        assert result.exit_code == 0
        assert "traefik" in result.output
        assert "Backup ID" in result.output

    def test_id_not_found(self, app_with_history):
        result = runner.invoke(app_with_history, ["history", "--id", "nonexistent-id"])
        assert result.exit_code == 1
        assert "No backup found" in result.output

    def test_stats(self, app_with_history):
        result = runner.invoke(app_with_history, ["history", "--stats"])
        assert result.exit_code == 0
        assert "Backup Statistics" in result.output
        assert "traefik" in result.output
        assert "nextcloud" in result.output
        assert "Duration" in result.output

    def test_stats_with_unit_filter(self, app_with_history):
        result = runner.invoke(app_with_history, ["history", "--stats", "--unit", "traefik"])
        assert result.exit_code == 0
        assert "traefik" in result.output

    def test_stats_empty(self, app_empty_metadata):
        result = runner.invoke(app_empty_metadata, ["history", "--stats"])
        assert result.exit_code == 0
        assert "No backup history found" in result.output

    def test_json_output(self, app_with_history):
        result = runner.invoke(app_with_history, ["history", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 4  # 4 valid metadata files
        assert all("unit_name" in entry for entry in data)
        assert all("timestamp" in entry for entry in data)

    def test_json_with_filter(self, app_with_history):
        result = runner.invoke(app_with_history, ["history", "--json", "--unit", "traefik"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert all(e["unit_name"] == "traefik" for e in data)

    def test_json_empty(self, app_empty_metadata):
        result = runner.invoke(app_empty_metadata, ["history", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []


class TestFormatHelpers:
    def test_format_duration_seconds(self):
        assert _format_duration(45.2) == "45s"

    def test_format_duration_minutes(self):
        assert _format_duration(135.5) == "2m15s"

    def test_format_snapshot_ids_none(self):
        assert _format_snapshot_ids([]) == "-"

    def test_format_snapshot_ids_one(self):
        assert _format_snapshot_ids(["k1234abcdef99"]) == "k1234abcdef9"

    def test_format_snapshot_ids_multiple(self):
        result = _format_snapshot_ids(["k1234abcdef99", "k5678ghijkl"])
        assert "(+1)" in result
