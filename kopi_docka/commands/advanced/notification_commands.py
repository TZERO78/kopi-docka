#!/usr/bin/env python3
################################################################################
# KOPI-DOCKA
#
# @file:        notification_commands.py
# @module:      kopi_docka.commands.advanced
# @description: Notification management commands (advanced notification subgroup)
# @author:      Markus F. (TZERO78) & AI Assistants
# @repository:  https://github.com/TZERO78/kopi-docka
# @version:     1.0.0
#
# ------------------------------------------------------------------------------
# Copyright (c) 2025 Markus F. (TZERO78)
# MIT License: see LICENSE or https://opensource.org/licenses/MIT
################################################################################

"""
Notification management commands under 'advanced notification'.

Commands:
- advanced notification setup  - Interactive setup wizard
- advanced notification test   - Send test notification
- advanced notification status - Show notification config status
"""

import typer
from urllib.parse import quote
from rich.console import Console
from rich.panel import Panel

from ...helpers.config import Config

console = Console()

# Create notification subcommand group
notification_app = typer.Typer(
    name="notification",
    help="Notification management commands.",
    no_args_is_help=True,
)


# --- Service Handlers ---


def _setup_telegram() -> dict:
    """Interactive Telegram setup."""
    console.print("\n[bold cyan]Telegram Setup[/bold cyan]")
    console.print("1. Message @BotFather on Telegram")
    console.print("2. Create a bot with /newbot and copy the token")
    console.print("3. Get your Chat ID from @userinfobot\n")

    bot_token = typer.prompt("Bot Token")
    chat_id = typer.prompt("Chat ID")

    return {
        "service": "telegram",
        "url": chat_id,
        "secret": bot_token,
    }


def _setup_discord() -> dict:
    """Interactive Discord setup."""
    console.print("\n[bold cyan]Discord Setup[/bold cyan]")
    console.print("1. Go to Server Settings > Integrations > Webhooks")
    console.print("2. Create a webhook and copy the URL\n")

    webhook_url = typer.prompt("Webhook URL")

    return {
        "service": "discord",
        "url": webhook_url,
        "secret": None,
    }


def _setup_email() -> dict:
    """Interactive Email setup."""
    console.print("\n[bold cyan]Email (SMTP) Setup[/bold cyan]")
    console.print("Common SMTP servers:")
    console.print("  - Gmail: smtp.gmail.com:587")
    console.print("  - Outlook: smtp.office365.com:587")
    console.print("  - Custom: your-server:port\n")

    smtp_server = typer.prompt("SMTP Server", default="smtp.gmail.com")
    smtp_port = typer.prompt("SMTP Port", default="587")
    username = typer.prompt("Username/Email")
    password = typer.prompt("Password (or App Password)", hide_input=True)
    display_name = typer.prompt("Sender Display Name", default="Kopi-Docka")
    recipient = typer.prompt("Recipient Email")

    # Build mailto URL with URL-encoded from parameter
    # 1. Construct from-header: "Display Name <username>"
    from_header = f"{display_name} <{username}>"

    # 2. URL-encode the from-header to handle spaces and special characters
    encoded_from = quote(from_header, safe='')

    # 3. Build final mailto URL with encoded from parameter
    # Example: mailto://user@smtp.gmail.com:587?to=recip@test.com&from=Kopi-Docka%20%3Cuser@test.com%3E
    url = f"mailto://{username}@{smtp_server}:{smtp_port}?to={recipient}&from={encoded_from}"

    return {
        "service": "email",
        "url": url,
        "secret": password,
    }


def _setup_webhook() -> dict:
    """Interactive Webhook setup."""
    console.print("\n[bold cyan]Webhook Setup[/bold cyan]")
    console.print("Supports: n8n, Make, Zapier, custom endpoints")
    console.print("URL will receive JSON POST with title and body\n")

    webhook_url = typer.prompt("Webhook URL (https://...)")

    return {
        "service": "webhook",
        "url": webhook_url,
        "secret": None,
    }


SERVICE_HANDLERS = {
    "telegram": _setup_telegram,
    "discord": _setup_discord,
    "email": _setup_email,
    "webhook": _setup_webhook,
}


# --- Core Setup Function (importable) ---


def run_notification_setup(config: Config) -> bool:
    """
    Run the notification setup wizard.

    Args:
        config: Config object to update

    Returns:
        bool: True if setup was successful, False if skipped
    """
    console.print(Panel("[bold]Notification Setup Wizard[/bold]", border_style="cyan"))

    # Service selection
    console.print("\nAvailable services:")
    console.print("  1. [cyan]telegram[/cyan] - Telegram Bot")
    console.print("  2. [cyan]discord[/cyan]  - Discord Webhook")
    console.print("  3. [cyan]email[/cyan]    - Email via SMTP")
    console.print("  4. [cyan]webhook[/cyan]  - Generic Webhook (JSON)")
    console.print("  5. [yellow]skip[/yellow]     - Skip setup\n")

    service = typer.prompt(
        "Select service",
        default="telegram",
    )

    if service == "skip" or service == "5":
        console.print("[yellow]Notification setup skipped.[/yellow]")
        return False

    # Map numbers to service names
    service_map = {"1": "telegram", "2": "discord", "3": "email", "4": "webhook"}
    service = service_map.get(service, service)

    # Validate service
    if service not in SERVICE_HANDLERS:
        console.print(f"[red]Unknown service: {service}[/red]")
        console.print(f"Valid options: {', '.join(SERVICE_HANDLERS.keys())}")
        raise typer.Exit(1)

    # Run service-specific handler
    handler = SERVICE_HANDLERS[service]
    result = handler()

    # Save to config
    config.set("notifications", "enabled", True)
    config.set("notifications", "service", result["service"])
    config.set("notifications", "url", result["url"])

    # Handle secret storage
    if result.get("secret"):
        use_file = typer.confirm("\nStore secret in separate file? (recommended)", default=True)
        if use_file:
            secret_file = config.config_file.parent / ".notification-secret"
            secret_file.write_text(result["secret"], encoding="utf-8")
            secret_file.chmod(0o600)
            config.set("notifications", "secret_file", str(secret_file))
            config.set("notifications", "secret", None)
            console.print(f"[green]Secret stored in: {secret_file}[/green]")
        else:
            config.set("notifications", "secret", result["secret"])
            config.set("notifications", "secret_file", None)
            console.print("[yellow]Secret stored in config (less secure)[/yellow]")
    else:
        config.set("notifications", "secret", None)
        config.set("notifications", "secret_file", None)

    # Save config
    config.save()
    console.print("\n[green]Notification configuration saved![/green]")

    return True


# --- Registration ---


def register(app: typer.Typer):
    """Register notification commands under 'advanced notification'."""

    @notification_app.command("setup")
    def _notification_setup_cmd(ctx: typer.Context):
        """Interactive notification setup wizard."""
        config: Config = ctx.obj.get("config")
        if not config:
            console.print("[red]Error: Could not load configuration[/red]")
            raise typer.Exit(1)

        # Run setup
        success = run_notification_setup(config)

        # Offer test if successful
        if success and typer.confirm("\nSend test notification?", default=True):
            _notification_test_cmd(ctx)

    @notification_app.command("test")
    def _notification_test_cmd(ctx: typer.Context):
        """Send a test notification."""
        config: Config = ctx.obj.get("config")
        if not config:
            console.print("[red]Error: Could not load configuration[/red]")
            raise typer.Exit(1)

        from ...cores.notification_manager import NotificationManager

        nm = NotificationManager(config)

        with console.status("[bold cyan]Sending test notification...[/bold cyan]"):
            success = nm.send_test()

        if success:
            console.print("[green]Test notification sent successfully![/green]")
        else:
            console.print("[red]Failed to send test notification.[/red]")
            console.print("[dim]Check logs for details: --log-level=DEBUG[/dim]")
            raise typer.Exit(1)

    @notification_app.command("status")
    def _notification_status_cmd(ctx: typer.Context):
        """Show notification configuration status."""
        config: Config = ctx.obj.get("config")
        if not config:
            console.print("[red]Error: Could not load configuration[/red]")
            raise typer.Exit(1)

        enabled = config.getboolean("notifications", "enabled", fallback=False)
        service = config.get("notifications", "service", fallback="not configured")
        url = config.get("notifications", "url", fallback="not configured")
        has_secret = bool(
            config.get("notifications", "secret", fallback=None)
            or config.get("notifications", "secret_file", fallback=None)
        )
        on_success = config.getboolean("notifications", "on_success", fallback=True)
        on_failure = config.getboolean("notifications", "on_failure", fallback=True)

        # Mask URL for security
        masked_url = url[:20] + "..." if url and len(url) > 20 else url

        status_text = f"""
[bold]Notification Status[/bold]

Enabled:     {"[green]Yes[/green]" if enabled else "[red]No[/red]"}
Service:     {service or "[dim]not set[/dim]"}
URL:         {masked_url or "[dim]not set[/dim]"}
Has Secret:  {"[green]Yes[/green]" if has_secret else "[yellow]No[/yellow]"}

On Success:  {"[green]Yes[/green]" if on_success else "[yellow]No[/yellow]"}
On Failure:  {"[green]Yes[/green]" if on_failure else "[yellow]No[/yellow]"}
        """

        console.print(Panel(status_text.strip(), border_style="cyan"))

    @notification_app.command("disable")
    def _notification_disable_cmd(ctx: typer.Context):
        """Disable notifications."""
        config: Config = ctx.obj.get("config")
        if not config:
            console.print("[red]Error: Could not load configuration[/red]")
            raise typer.Exit(1)

        config.set("notifications", "enabled", False)
        config.save()
        console.print("[green]Notifications disabled.[/green]")

    @notification_app.command("enable")
    def _notification_enable_cmd(ctx: typer.Context):
        """Enable notifications (requires prior setup)."""
        config: Config = ctx.obj.get("config")
        if not config:
            console.print("[red]Error: Could not load configuration[/red]")
            raise typer.Exit(1)

        # Check if configured
        service = config.get("notifications", "service", fallback=None)
        if not service:
            console.print("[red]Notifications not configured.[/red]")
            console.print("Run: [cyan]kopi-docka advanced notification setup[/cyan]")
            raise typer.Exit(1)

        config.set("notifications", "enabled", True)
        config.save()
        console.print("[green]Notifications enabled.[/green]")

    # Add notification subgroup to admin app
    app.add_typer(
        notification_app, name="notification", help="Notification management (setup, test, status)"
    )
