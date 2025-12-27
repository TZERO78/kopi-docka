# Notifications

[← Back to README](../README.md)

## Overview

Kopi-Docka can automatically send notifications about backup status via popular messaging platforms. Get instant alerts when backups succeed or fail, without having to manually check logs.

**Supported Services:**
- 🔔 **Telegram** - Free, popular messaging app
- 💬 **Discord** - Webhook-based notifications
- 📧 **Email** - SMTP-based email alerts
- 🔗 **Webhook** - JSON POST to custom endpoints (n8n, Make, Zapier, etc.)
- 🔧 **Custom** - Any Apprise-compatible URL

**Key Features:**
- ✅ Fire-and-forget pattern - never blocks backups
- ✅ 10-second timeout protection
- ✅ Separate notifications for success/failure
- ✅ Secure secret management (file or config)
- ✅ Environment variable support in URLs
- ✅ Interactive setup wizard

---

## Quick Start

### 1. Setup Notifications

Use the interactive wizard to configure notifications:

```bash
sudo kopi-docka advanced notification setup
```

The wizard will guide you through:
1. **Service selection** - Choose from Telegram, Discord, Email, Webhook, or Custom
2. **Service configuration** - Enter service-specific details
3. **Secret storage** - Store tokens/passwords securely
4. **Test notification** - Verify setup works

### 2. Test Notifications

Send a test notification to verify everything works:

```bash
sudo kopi-docka advanced notification test
```

### 3. Check Status

View current notification configuration:

```bash
sudo kopi-docka advanced notification status
```

### 4. Enable/Disable

Toggle notifications on/off without losing configuration:

```bash
sudo kopi-docka advanced notification disable
sudo kopi-docka advanced notification enable
```

---

## Service Setup Guides

### Telegram

**Why Telegram?**
- Free and reliable
- Works on all platforms
- Instant delivery

**Setup Steps:**

1. **Create a Bot:**
   - Open Telegram and message [@BotFather](https://t.me/BotFather)
   - Send `/newbot` and follow the instructions
   - Copy the **Bot Token** (looks like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

2. **Get Your Chat ID:**
   - Message [@userinfobot](https://t.me/userinfobot)
   - Copy your **Chat ID** (looks like: `987654321`)

3. **Configure Kopi-Docka:**
   ```bash
   sudo kopi-docka advanced notification setup
   # Select: 1 (Telegram)
   # Bot Token: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   # Chat ID: 987654321
   ```

4. **Test it:**
   ```bash
   sudo kopi-docka advanced notification test
   ```

**Manual Configuration:**

```json
{
  "notifications": {
    "enabled": true,
    "service": "telegram",
    "url": "987654321",
    "secret_file": "/etc/kopi-docka-telegram-token",
    "on_success": true,
    "on_failure": true
  }
}
```

Secret file content:
```bash
echo "123456789:ABCdefGHIjklMNOpqrsTUVwxyz" > /etc/kopi-docka-telegram-token
chmod 600 /etc/kopi-docka-telegram-token
```

---

### Discord

**Why Discord?**
- Great for teams
- Rich formatting support
- Easy webhook setup

**Setup Steps:**

1. **Create a Webhook:**
   - Go to your Discord server
   - Settings → Integrations → Webhooks
   - Click "New Webhook"
   - Choose a channel and copy the **Webhook URL**
   - URL format: `https://discord.com/api/webhooks/123456/WEBHOOK_TOKEN`

2. **Configure Kopi-Docka:**
   ```bash
   sudo kopi-docka advanced notification setup
   # Select: 2 (Discord)
   # Webhook URL: https://discord.com/api/webhooks/123456/WEBHOOK_TOKEN
   ```

3. **Test it:**
   ```bash
   sudo kopi-docka advanced notification test
   ```

**Manual Configuration:**

```json
{
  "notifications": {
    "enabled": true,
    "service": "discord",
    "url": "https://discord.com/api/webhooks/123456/WEBHOOK_TOKEN",
    "on_success": true,
    "on_failure": true
  }
}
```

---

### Email (SMTP)

**Why Email?**
- Universal
- Works with existing email infrastructure
- Good for audit trails

**Setup Steps:**

1. **Get SMTP Credentials:**
   - **Gmail:** Use an [App Password](https://support.google.com/accounts/answer/185833)
   - **Outlook/Office365:** Use account password or app password
   - **Custom SMTP:** Get credentials from your mail server admin

2. **Configure Kopi-Docka:**
   ```bash
   sudo kopi-docka advanced notification setup
   # Select: 3 (Email)
   # SMTP Server: smtp.gmail.com (or your server)
   # SMTP Port: 587
   # Username: your-email@gmail.com
   # Password: your-app-password
   # Display Name: Kopi-Docka Backup (shows as sender name)
   # Recipient: admin@example.com
   ```

3. **Test it:**
   ```bash
   sudo kopi-docka advanced notification test
   ```

**Common SMTP Servers:**

| Provider | Server | Port |
|----------|--------|------|
| Gmail | `smtp.gmail.com` | 587 |
| Outlook | `smtp.office365.com` | 587 |
| Yahoo | `smtp.mail.yahoo.com` | 587 |
| Custom | Your server | Usually 587 or 465 |

**Manual Configuration:**

```json
{
  "notifications": {
    "enabled": true,
    "service": "email",
    "url": "mailto://user@smtp.gmail.com:587?to=admin@example.com&from=Kopi-Docka<user@gmail.com>",
    "secret_file": "/etc/kopi-docka-email-password",
    "on_success": true,
    "on_failure": true
  }
}
```

---

### Webhook

**Why Webhooks?**
- Integration with automation tools
- Custom processing logic
- Universal HTTP endpoint

**Supported Tools:**
- n8n
- Make (Integromat)
- Zapier
- Custom HTTP endpoints

**Setup Steps:**

1. **Create Webhook in Your Tool:**
   - Create a new workflow/scenario
   - Add a webhook trigger
   - Copy the webhook URL

2. **Configure Kopi-Docka:**
   ```bash
   sudo kopi-docka advanced notification setup
   # Select: 4 (Webhook)
   # Webhook URL: https://your-automation-tool.com/webhook/abc123
   ```

3. **Test it:**
   ```bash
   sudo kopi-docka advanced notification test
   ```

**Payload Format:**

Kopi-Docka sends JSON POST requests with:
```json
{
  "title": "Backup OK: mystack",
  "body": "Unit: mystack\nStatus: SUCCESS\nVolumes: 3\nNetworks: 2\nDuration: 45.2s\nBackup-ID: backup_a..."
}
```

**Manual Configuration:**

```json
{
  "notifications": {
    "enabled": true,
    "service": "webhook",
    "url": "https://your-automation-tool.com/webhook/abc123",
    "on_success": true,
    "on_failure": true
  }
}
```

---

### Custom (Advanced)

**Why Custom?**
- Support for any Apprise-compatible service
- Maximum flexibility

**Supported Services:**

Kopi-Docka uses [Apprise](https://github.com/caronc/apprise), which supports 100+ notification services including:
- Slack
- Matrix
- Pushover
- Gotify
- And many more!

**Setup:**

1. **Find Your Service URL:**
   - Check the [Apprise documentation](https://github.com/caronc/apprise/wiki)
   - Example for Slack: `slack://TokenA/TokenB/TokenC`

2. **Configure:**
   ```bash
   sudo kopi-docka advanced notification setup
   # Select: 5 (Skip)
   # Then manually edit config.json
   ```

**Manual Configuration:**

```json
{
  "notifications": {
    "enabled": true,
    "service": "custom",
    "url": "slack://TokenA/TokenB/TokenC",
    "on_success": true,
    "on_failure": true
  }
}
```

---

## Configuration Reference

### Complete Example

```json
{
  "notifications": {
    "enabled": true,
    "service": "telegram",
    "url": "987654321",
    "secret": null,
    "secret_file": "/etc/kopi-docka-telegram-token",
    "on_success": true,
    "on_failure": true
  }
}
```

### Field Descriptions

| Field | Type | Description | Required |
|-------|------|-------------|----------|
| `enabled` | boolean | Enable/disable notifications | Yes |
| `service` | string | Service type: `telegram`, `discord`, `email`, `webhook`, `custom` | Yes |
| `url` | string | Service URL or identifier (supports `${ENV_VAR}` substitution) | Yes |
| `secret` | string | Token/password (stored in config - less secure) | No |
| `secret_file` | string | Path to file containing secret (recommended) | No |
| `on_success` | boolean | Send notification on backup success | No (default: true) |
| `on_failure` | boolean | Send notification on backup failure | No (default: true) |

### Secret Management

**3-Way Priority System:**

Secrets are resolved in this order:

1. **`secret_file`** (Recommended - Most Secure)
   - Read from external file
   - File should have `600` permissions
   - Example: `/etc/kopi-docka-telegram-token`

2. **`secret`** (Config - Less Secure)
   - Stored directly in config.json
   - Convenient but visible in config
   - Use only if file storage isn't possible

3. **None** (Optional)
   - Some services embed secrets in URL
   - Example: Discord webhooks, generic webhooks

**Best Practice:**

```bash
# Create secret file
echo "YOUR_SECRET_TOKEN" > /etc/kopi-docka-secret
chmod 600 /etc/kopi-docka-secret

# Reference in config
{
  "notifications": {
    "secret_file": "/etc/kopi-docka-secret"
  }
}
```

### Environment Variables

You can use environment variables in the `url` field:

**Example:**

```json
{
  "notifications": {
    "service": "telegram",
    "url": "${TELEGRAM_CHAT_ID}",
    "secret_file": "/etc/telegram-token"
  }
}
```

Then set the environment variable:
```bash
export TELEGRAM_CHAT_ID="987654321"
```

**Supported Format:**
- Pattern: `${VARIABLE_NAME}`
- Only uppercase variables are matched
- Unknown variables are kept as-is (with warning in logs)

---

## Notification Messages

### Success Message

```
Backup OK: mystack

Unit: mystack
Status: SUCCESS
Volumes: 3
Networks: 2
Duration: 45.2s
Backup-ID: backup_a...
```

### Failure Message

```
BACKUP FAILED: mystack

Unit: mystack
Status: FAILED
Errors: Docker connection failed; Timeout occurred
Duration: 12.5s
```

**Note:** Error lists are truncated to 3 errors. Additional errors are shown as "+N more".

---

## Troubleshooting

### Test Command Returns False

**Possible Causes:**
1. **Wrong credentials** - Double-check tokens/passwords
2. **Network issues** - Check internet connectivity
3. **Service down** - Telegram/Discord API might be temporarily unavailable
4. **Timeout** - Notification took longer than 10 seconds

**Debug:**
```bash
sudo kopi-docka advanced notification test --log-level=DEBUG
```

### No Notifications Received

**Check:**

1. **Is it enabled?**
   ```bash
   sudo kopi-docka advanced notification status
   ```

2. **Check config:**
   ```bash
   sudo kopi-docka advanced config show
   ```

3. **Check logs:**
   ```bash
   sudo tail -f /var/log/kopi-docka.log
   ```

4. **Test manually:**
   ```bash
   sudo kopi-docka advanced notification test
   ```

### Telegram: "Unauthorized" Error

**Solution:**
- Make sure you've sent `/start` to your bot
- Verify the Bot Token is correct
- Check that Chat ID matches your account

### Email: "Authentication Failed"

**Solution:**
- Use an App Password (not your regular password)
- Check SMTP server and port
- Verify username format (some servers need full email, others just username)

### Discord: Messages Not Appearing

**Solution:**
- Verify webhook URL is correct
- Check webhook hasn't been deleted
- Ensure bot has permissions to post in the channel

---

## Advanced Usage

### Disable Success Notifications

Only get notified on failures:

```json
{
  "notifications": {
    "enabled": true,
    "service": "telegram",
    "url": "987654321",
    "secret_file": "/etc/telegram-token",
    "on_success": false,
    "on_failure": true
  }
}
```

### Multiple Recipients (Email)

Send to multiple email addresses:

```json
{
  "notifications": {
    "service": "email",
    "url": "mailto://user@smtp.gmail.com:587?to=admin1@example.com,admin2@example.com"
  }
}
```

### Rate Limiting

**Built-in Protection:**
- 10-second timeout per notification
- Fire-and-forget pattern
- Notification failures never block backups

**If you need more control:**
- Use webhooks + automation tool
- Implement your own rate limiting logic
- Batch notifications in your automation tool

---

## Security Best Practices

1. **Use `secret_file` instead of `secret`**
   - Keeps secrets out of config file
   - Easier to rotate credentials
   - Better permission control

2. **Set proper file permissions:**
   ```bash
   chmod 600 /etc/kopi-docka-secret
   chown root:root /etc/kopi-docka-secret
   ```

3. **Use environment variables for URLs:**
   - Keeps dynamic values out of config
   - Easier CI/CD integration

4. **Rotate credentials regularly:**
   - Change tokens/passwords periodically
   - Update secret files
   - Test after rotation

5. **Monitor notification failures:**
   - Check logs for failed notifications
   - Set up secondary alerting if critical

---

## How It Works

### Fire-and-Forget Pattern

Notifications use a fire-and-forget pattern to ensure they **never block backup operations:**

1. Backup completes (success or failure)
2. Notification is sent in background thread
3. 10-second timeout applied
4. If timeout or error occurs:
   - Error is logged
   - Backup operation continues normally

**Result:** Your backups always complete, even if notification service is down.

### Integration Point

Notifications are sent automatically at the end of each backup unit:

```
1. Stop containers
2. Backup volumes
3. Backup networks
4. Start containers
5. → Send notification ← (you are here)
6. Return to caller
```

**Single notification per backup unit** - not per volume.

---

## Examples

### Example 1: Telegram for Personal Server

```bash
# Setup
sudo kopi-docka advanced notification setup
# → Select Telegram
# → Enter bot token and chat ID
# → Store token in file: Yes

# Test
sudo kopi-docka advanced notification test

# Run backup (notification sent automatically)
sudo kopi-docka backup
```

### Example 2: Discord for Team

```bash
# Setup
sudo kopi-docka advanced notification setup
# → Select Discord
# → Enter webhook URL

# Status check
sudo kopi-docka advanced notification status

# Run backup
sudo kopi-docka backup myapp
```

### Example 3: Email for Production

```bash
# Setup
sudo kopi-docka advanced notification setup
# → Select Email
# → SMTP: smtp.office365.com
# → Port: 587
# → User: backups@company.com
# → Password: [app password]
# → To: admin@company.com

# Test
sudo kopi-docka advanced notification test

# Schedule with cron
0 2 * * * /usr/local/bin/kopi-docka backup --all
```

### Example 4: Webhook with n8n

```bash
# In n8n:
# 1. Create workflow with Webhook trigger
# 2. Copy webhook URL

# In Kopi-Docka:
sudo kopi-docka advanced notification setup
# → Select Webhook
# → Paste n8n webhook URL

# Test
sudo kopi-docka advanced notification test

# In n8n workflow:
# - Parse JSON body
# - Check if "FAILED" in title
# - Send urgent alert if failure
# - Log success to database
```

---

## FAQ

**Q: Can I send to multiple services?**
A: Currently, one service per configuration. Use webhooks + automation tool for multiple destinations.

**Q: Are notifications sent for scheduled backups?**
A: Yes! All backups (manual, cron, scheduled) send notifications automatically.

**Q: What happens if notification fails?**
A: Error is logged, but backup continues normally. Fire-and-forget pattern ensures no blocking.

**Q: Can I customize message format?**
A: Currently, messages use hardcoded templates. Custom templates are planned for future releases.

**Q: Does this work with `kopi-docka backup --all`?**
A: Yes! One notification is sent per backup unit (not per volume).

**Q: Can I test without running a backup?**
A: Yes! Use `kopi-docka advanced notification test`

**Q: How do I disable notifications temporarily?**
A: `kopi-docka advanced notification disable` (re-enable with `enable`)

---

## Related Documentation

- [Configuration Guide](CONFIGURATION.md) - Full config reference
- [Hooks Documentation](HOOKS.md) - Pre/post backup hooks
- [Usage Guide](USAGE.md) - General usage examples

---

## Support

**Issues?**
- Check the [Troubleshooting](#troubleshooting) section above
- Review logs: `/var/log/kopi-docka.log`
- Open an issue on [GitHub](https://github.com/TZERO78/kopi-docka/issues)

**Feature Requests?**
- Multiple notification destinations
- Custom message templates
- Notification history/log
- Additional services

Submit your ideas on GitHub!
