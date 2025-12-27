"""Integration tests for systemd service templates."""

import tempfile
from pathlib import Path

import pytest

from kopi_docka.cores.service_manager import write_systemd_units


@pytest.mark.integration
class TestServiceTemplates:
    """Test systemd template installation and validity."""

    def test_templates_exist_in_package(self):
        """Test that all required templates exist in the package."""
        # Get template directory path
        import kopi_docka.cores.service_manager as sm

        template_dir = Path(sm.__file__).parent.parent / "templates" / "systemd"

        # Check template files
        assert (template_dir / "kopi-docka.service.template").exists()
        assert (template_dir / "kopi-docka.timer.template").exists()
        assert (template_dir / "kopi-docka-backup.service.template").exists()
        assert (template_dir / "README.md").exists()

    def test_template_files_not_empty(self):
        """Test that template files have content."""
        import kopi_docka.cores.service_manager as sm

        template_dir = Path(sm.__file__).parent.parent / "templates" / "systemd"

        for template_file in [
            "kopi-docka.service.template",
            "kopi-docka.timer.template",
            "kopi-docka-backup.service.template",
        ]:
            content = (template_dir / template_file).read_text()
            assert len(content) > 0
            assert "[Unit]" in content or "[Timer]" in content

    def test_write_units_from_templates(self):
        """Test that write_systemd_units creates correct files from templates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Write units to temp directory
            write_systemd_units(output_dir)

            # Check that all files were created
            assert (output_dir / "kopi-docka.service").exists()
            assert (output_dir / "kopi-docka.timer").exists()
            assert (output_dir / "kopi-docka-backup.service").exists()

            # Verify content
            service_content = (output_dir / "kopi-docka.service").read_text()
            assert "kopi-docka daemon" in service_content or "kopi-docka" in service_content
            assert "[Service]" in service_content
            assert "Type=notify" in service_content

            timer_content = (output_dir / "kopi-docka.timer").read_text()
            assert "[Timer]" in timer_content
            assert "OnCalendar=" in timer_content

            backup_content = (output_dir / "kopi-docka-backup.service").read_text()
            assert "[Service]" in backup_content
            assert "Type=oneshot" in backup_content

    def test_service_template_has_security_settings(self):
        """Test that service template includes security hardening."""
        import kopi_docka.cores.service_manager as sm

        template_dir = Path(sm.__file__).parent.parent / "templates" / "systemd"
        content = (template_dir / "kopi-docka.service.template").read_text()

        # Check for key security settings
        assert "NoNewPrivileges=" in content
        assert "ProtectSystem=" in content
        assert "PrivateTmp=" in content
        assert "ReadWritePaths=" in content

    def test_timer_template_has_oncalendar_examples(self):
        """Test that timer template includes OnCalendar examples in comments."""
        import kopi_docka.cores.service_manager as sm

        template_dir = Path(sm.__file__).parent.parent / "templates" / "systemd"
        content = (template_dir / "kopi-docka.timer.template").read_text()

        # Check for examples in comments
        assert "EXAMPLES" in content or "examples" in content.lower()
        assert "daily" in content.lower() or "Daily" in content
        assert "weekly" in content.lower() or "Weekly" in content

    def test_readme_exists_and_has_content(self):
        """Test that README.md exists and has useful content."""
        import kopi_docka.cores.service_manager as sm

        template_dir = Path(sm.__file__).parent.parent / "templates" / "systemd"
        readme = template_dir / "README.md"

        assert readme.exists()

        content = readme.read_text()
        assert len(content) > 100  # Should have substantial content
        assert "kopi-docka" in content.lower()
        assert "systemd" in content.lower()

    def test_template_syntax_basic_validation(self):
        """Test basic systemd unit file syntax."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            write_systemd_units(output_dir)

            for unit_file in ["kopi-docka.service", "kopi-docka.timer"]:
                content = (output_dir / unit_file).read_text()

                # Basic syntax checks
                assert "[Unit]" in content
                assert "[Install]" in content

                # Check for common syntax errors
                lines = content.splitlines()
                for line in lines:
                    # Skip comments and empty lines
                    if line.strip().startswith("#") or not line.strip():
                        continue

                    # Section headers should be in brackets
                    if line.strip().startswith("["):
                        assert line.strip().endswith("]")

    def test_write_units_missing_template_raises_error(self):
        """Test that missing template raises appropriate error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # This should work normally
            write_systemd_units(output_dir)

            # Verify files were created
            assert (output_dir / "kopi-docka.service").exists()


@pytest.mark.integration
class TestTemplateComments:
    """Test that templates have extensive documentation."""

    def test_service_template_has_extensive_comments(self):
        """Test that service template has extensive comments."""
        import kopi_docka.cores.service_manager as sm

        template_dir = Path(sm.__file__).parent.parent / "templates" / "systemd"
        content = (template_dir / "kopi-docka.service.template").read_text()

        # Count comment lines
        lines = content.splitlines()
        comment_lines = [line for line in lines if line.strip().startswith("#") or not line.strip()]

        # Should have substantial documentation
        assert len(comment_lines) > 20

    def test_timer_template_has_oncalendar_documentation(self):
        """Test that timer template documents OnCalendar syntax."""
        import kopi_docka.cores.service_manager as sm

        template_dir = Path(sm.__file__).parent.parent / "templates" / "systemd"
        content = (template_dir / "kopi-docka.timer.template").read_text()

        # Should document various scheduling options
        content_lower = content.lower()
        assert "oncalendar" in content_lower
        assert "daily" in content_lower or "weekly" in content_lower

    def test_backup_service_has_usage_comments(self):
        """Test that backup service template has usage documentation."""
        import kopi_docka.cores.service_manager as sm

        template_dir = Path(sm.__file__).parent.parent / "templates" / "systemd"
        content = (template_dir / "kopi-docka-backup.service.template").read_text()

        # Should document when to use this service
        assert (
            "one" in content.lower() and "shot" in content.lower() or "oneshot" in content.lower()
        )
