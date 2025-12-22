# Investigation: Lock File Creation Bug Report

## Summary

**Bug Report:** "Lock File Created Every Time Wizard Runs"

**Investigation Result:** **NO BUG FOUND** - The wizard code does NOT create lock files.

**Root Cause:** Likely user misunderstanding or system configuration issue.

---

## Investigation Details

### Code Analysis

Conducted extensive investigation of the entire codebase:

1. **Lock File References:** Only 2 locations reference `/run/kopi-docka/kopi-docka.lock`:
   - `service_manager.py:68` - `LockFile.__init__` method definition
   - `service_helper.py:232` - `get_lock_status()` method (READ-ONLY)

2. **Lock Creation:** Lock files are ONLY created by:
   - `LockFile.acquire()` method in `service_manager.py:72-80`
   - Which is ONLY called by `KopiDockaService.start()` on line 191
   - Which is ONLY called by the daemon command (`kopi-docka admin service daemon`)
   - The wizard (`kopi-docka admin service manage`) **NEVER** calls the daemon

3. **Wizard Code Path:**
   ```
   cmd_manage()
     → ServiceHelper()  # No lock creation
       → get_lock_status()  # READ-ONLY
         → Path.exists()  # READ-ONLY
         → Path.read_text()  # READ-ONLY
         → os.kill(pid, 0)  # READ-ONLY process check
   ```

4. **No Suspicious Code:**
   - No module-level code that runs on import
   - No subprocess calls that start the daemon
   - No file writes to `/run/kopi-docka/`
   - All systemctl commands are read-only (`is-active`, `is-enabled`, `is-failed`)

### Likely Explanations

1. **Service is Already Running:**
   - The kopi-docka.service may be enabled and auto-starting at boot
   - User runs wizard and sees lock from running service
   - Service may be unstable and restarting frequently

2. **Stale Lock Files:**
   - Previous service crashed leaving stale lock
   - User associates checking wizard status with seeing the lock
   - Lock file persists across multiple wizard runs

3. **External Configuration:**
   - Custom systemd units or hooks
   - Shell aliases or wrappers
   - Monitoring tools that start the service

---

## Improvements Implemented

Even though no bug was found, added improvements for better diagnostics and UX:

### 1. Enhanced `get_lock_status()` Method

**File:** `kopi_docka/cores/service_helper.py`

**Changes:**
- Added extensive documentation clarifying it's READ-ONLY
- Improved logging with DEBUG messages:
  - "No lock file found"
  - "Lock file found with PID: X"
  - "Process X is running"
  - "Process X is not running (stale lock)"
- Changed from `subprocess.run(["kill", "-0"])` to `os.kill(pid, 0)`:
  - More portable and efficient
  - Handles `ProcessLookupError` and `PermissionError`
- Upgraded error logging from DEBUG to WARNING level

### 2. New `remove_stale_lock()` Method

**File:** `kopi_docka/cores/service_helper.py`

**Purpose:** Safely remove stale lock files from dead processes

**Logic:**
- Checks if lock exists
- Verifies process is NOT running (won't remove active locks)
- Safely removes stale lock file
- Logs actions and errors

### 3. Improved Lock Status Display

**File:** `kopi_docka/commands/service_commands.py`

**Changes:**
- Replaced simple warning message with Rich Panel for better visibility
- **Active Lock:** Shows clear explanation that daemon is running
- **Stale Lock:** Explains what a stale lock is and how to remove it
- Includes PID and process status
- User-friendly help text

### 4. Added "Remove Stale Lock File" Menu Option

**File:** `kopi_docka/commands/service_commands.py`

**Location:** Control Service menu → Option [6]

**Features:**
- Checks lock status before attempting removal
- Shows informative panel if lock is active (cannot remove)
- Shows informative panel if lock is stale (can remove)
- Requires user confirmation before removal
- Provides clear success/failure feedback
- Prevents accidental removal of active locks

---

## Testing Recommendations

To diagnose if the issue persists:

1. **Check if service is running:**
   ```bash
   sudo systemctl status kopi-docka.service
   sudo systemctl is-enabled kopi-docka.service
   ```

2. **Check lock file before wizard:**
   ```bash
   ls -la /run/kopi-docka/kopi-docka.lock
   cat /run/kopi-docka/kopi-docka.lock
   echo "Current PID: $$"
   ```

3. **Run wizard with debug logging:**
   ```bash
   sudo kopi-docka --log-level=DEBUG admin service manage
   ```

4. **Check for auto-start:**
   ```bash
   sudo systemctl disable kopi-docka.service
   sudo reboot
   # After reboot, check if lock file exists
   ```

---

## Conclusion

**No bug exists in the codebase.** The wizard does NOT create lock files.

The improvements add better diagnostics, clearer messaging, and a utility to clean up stale locks, which should help users understand what's happening and resolve any issues.

If the user continues to see this behavior after these improvements, they should:
1. Check if the service is auto-starting
2. Review systemd unit configurations
3. Check for custom scripts or hooks
4. Provide debug logs for further investigation

---

**Investigation Date:** 2025-12-22
**Files Modified:**
- `kopi_docka/cores/service_helper.py`
- `kopi_docka/commands/service_commands.py`
