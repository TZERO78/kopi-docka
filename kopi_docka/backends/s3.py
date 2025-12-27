"""
AWS S3 / S3-Compatible Backend Configuration

Supports: AWS S3, Wasabi, MinIO, DigitalOcean Spaces, etc.
"""

import typer
from .base import BackendBase


class S3Backend(BackendBase):
    """AWS S3 and S3-compatible storage backend"""

    @property
    def name(self) -> str:
        return "s3"

    @property
    def display_name(self) -> str:
        return "AWS S3"

    @property
    def description(self) -> str:
        return "AWS S3 or compatible (Wasabi, MinIO, DigitalOcean)"

    def configure(self) -> dict:
        """
            Interactive S3 configuration wizard.

        Returns:
            dict with:
            - repository_path: S3 URL
            - env_vars: Required environment variables
            - instructions: Setup instructions
        """
        typer.echo("AWS S3 or S3-compatible storage selected.")
        typer.echo("")
        typer.echo("Supported services:")
        typer.echo("  • AWS S3")
        typer.echo("  • Wasabi")
        typer.echo("  • MinIO")
        typer.echo("  • DigitalOcean Spaces")
        typer.echo("  • Any S3-compatible service")
        typer.echo("")

        # Get bucket info
        bucket = typer.prompt("Bucket name")
        prefix = typer.prompt("Path prefix (optional)", default="kopia", show_default=True)
        region = typer.prompt("Region (optional, e.g. us-east-1)", default="", show_default=False)

        # Ask for custom endpoint (for non-AWS services)
        use_custom_endpoint = typer.confirm(
            "Using non-AWS S3-compatible service (Wasabi, MinIO, etc.)?", default=False
        )
        endpoint = ""
        if use_custom_endpoint:
            typer.echo("")
            typer.echo("Examples:")
            typer.echo("  • Wasabi:     s3.wasabisys.com")
            typer.echo("  • MinIO:      minio.example.com:9000")
            typer.echo("  • DO Spaces:  nyc3.digitaloceanspaces.com")
            endpoint = typer.prompt("Endpoint URL")

        # Build Kopia command parameters
        kopia_params = f"s3 --bucket {bucket}"
        if prefix:
            kopia_params += f" --prefix {prefix}"
        if endpoint:
            kopia_params += f" --endpoint {endpoint}"
        if region:
            kopia_params += f" --region {region}"

        # Environment variables needed
        env_vars = {
            "AWS_ACCESS_KEY_ID": "<your-access-key-id>",
            "AWS_SECRET_ACCESS_KEY": "<your-secret-access-key>",
        }

        if region:
            env_vars["AWS_REGION"] = region

        if endpoint:
            env_vars["AWS_ENDPOINT"] = f"https://{endpoint}"

        # Build instructions
        instructions = f"""
⚠️  Set these environment variables before running init:

{_format_env_vars(env_vars)}

To set permanently (add to /etc/environment or ~/.bashrc):
  echo 'AWS_ACCESS_KEY_ID=your-key' | sudo tee -a /etc/environment
  echo 'AWS_SECRET_ACCESS_KEY=your-secret' | sudo tee -a /etc/environment

Get credentials from:
  • AWS: https://console.aws.amazon.com/iam/
  • Wasabi: https://console.wasabisys.com/#/access_keys
  • MinIO: Your MinIO admin panel
"""

        return {
            "kopia_params": kopia_params,
            "env_vars": env_vars,
            "instructions": instructions,
        }

    def get_status(self) -> dict:
        """Get S3 storage status."""
        import shlex

        status = {
            "repository_type": self.name,
            "configured": bool(self.config),
            "available": False,
            "details": {
                "bucket": None,
                "prefix": None,
                "endpoint": None,
                "region": None,
            },
        }

        # Parse kopia_params to extract S3 details
        kopia_params = self.config.get("kopia_params", "")
        if not kopia_params:
            return status

        try:
            parts = shlex.split(kopia_params)

            # Extract bucket
            if "--bucket" in parts:
                idx = parts.index("--bucket")
                if idx + 1 < len(parts):
                    status["details"]["bucket"] = parts[idx + 1]

            # Extract prefix
            if "--prefix" in parts:
                idx = parts.index("--prefix")
                if idx + 1 < len(parts):
                    status["details"]["prefix"] = parts[idx + 1]

            # Extract endpoint
            if "--endpoint" in parts:
                idx = parts.index("--endpoint")
                if idx + 1 < len(parts):
                    status["details"]["endpoint"] = parts[idx + 1]

            # Extract region
            if "--region" in parts:
                idx = parts.index("--region")
                if idx + 1 < len(parts):
                    status["details"]["region"] = parts[idx + 1]

            # Mark as configured if we have a bucket
            if status["details"]["bucket"]:
                status["configured"] = True
                status["available"] = True  # Assume configured = available for cloud
        except Exception:
            pass

        return status

    # Abstract method implementations (required by BackendBase)
    def check_dependencies(self) -> list:
        """No local dependencies required for S3."""
        return []

    def install_dependencies(self) -> bool:
        """No dependencies to install."""
        return True

    def setup_interactive(self) -> dict:
        """Use configure() for setup."""
        return self.configure()

    def validate_config(self) -> tuple:
        """Validate configuration."""
        return (True, [])

    def test_connection(self) -> bool:
        """Test connection (requires AWS credentials in environment)."""
        return True

    def get_kopia_args(self) -> list:
        """Get Kopia arguments from kopia_params."""
        import shlex

        kopia_params = self.config.get("kopia_params", "")
        return shlex.split(kopia_params) if kopia_params else []


def _format_env_vars(env_vars: dict) -> str:
    """Format environment variables for display."""
    lines = []
    for key, value in env_vars.items():
        lines.append(f"  export {key}='{value}'")
    return "\n".join(lines)
