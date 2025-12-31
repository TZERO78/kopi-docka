# SafeExitManager - Manual Testing Guide

This guide provides step-by-step procedures for manually testing the SafeExitManager exit safety system.

**Prerequisites:**
- Kopi-Docka installed and configured
- Docker running with at least one container
- Root access (`sudo`)
- Kopia repository initialized

---

## Test 1: Backup Abort → Container Auto-Restart

**Goal:** Verify that containers are automatically restarted when backup is aborted with Ctrl+C.

### Setup

```bash
# 1. Check current containers
docker ps

# 2. Note down a running container name (e.g., "webapp")
CONTAINER_NAME="webapp"  # Replace with your container

# 3. Verify container is running
docker ps | grep $CONTAINER_NAME
```

### Test Procedure

```bash
# 1. Start backup
sudo kopi-docka backup

# 2. Wait until you see container being stopped
# Look for log: "Stopping container: webapp"

# 3. Press Ctrl+C (SIGINT)
# Expected output:
#   Received SIGINT - starting emergency cleanup...
#   EMERGENCY: Terminating X tracked process(es)...
#   ServiceContinuity: Restarting N container(s)...
#     Starting webapp...
#     [OK] webapp started
#   Cleanup complete, exiting with code 130

# 4. Verify containers are back UP
docker ps
```

### Expected Result

✅ **PASS** if:
- All containers show "Up" status in `docker ps`
- No containers remain stopped
- Exit code is 130 (128 + SIGINT)

❌ **FAIL** if:
- Any container remains stopped
- Manual restart needed

### Cleanup

```bash
# If test failed and containers are stopped:
docker start $CONTAINER_NAME
```

---

## Test 2: Backup Abort with systemctl stop

**Goal:** Verify that SIGTERM (systemctl stop) also triggers container restart.

### Prerequisites

```bash
# 1. Install systemd service
sudo kopi-docka advanced service write-units

# 2. Start service manually (one-shot for testing)
sudo systemctl start kopi-docka.service

# In another terminal, monitor logs:
sudo journalctl -u kopi-docka.service -f
```

### Test Procedure

```bash
# Terminal 1: Monitor logs
sudo journalctl -u kopi-docka.service -f

# Terminal 2: Wait for backup to start, then stop service
sudo systemctl stop kopi-docka.service

# Expected in logs:
#   Received SIGTERM - starting emergency cleanup...
#   ServiceContinuity: Restarting N container(s)...
#   Cleanup complete, exiting with code 143
```

### Expected Result

✅ **PASS** if:
- Containers restarted (check `docker ps`)
- Exit code is 143 (128 + SIGTERM)
- systemd receives STOPPING=1 notification

❌ **FAIL** if:
- Containers remain stopped
- Exit code is not 143

---

## Test 3: Restore Abort → Containers Stay Stopped

**Goal:** Verify that containers intentionally stay stopped when restore is aborted (data safety).

### Setup

```bash
# 1. Ensure you have a backup to restore
sudo kopi-docka advanced snapshot list --snapshots

# 2. Start interactive restore
sudo kopi-docka restore
```

### Test Procedure

```bash
# 1. Start restore and select a backup session

# 2. When prompted to select unit, choose one

# 3. During restore (after containers are stopped), press Ctrl+C

# Expected output:
#   Received SIGINT - starting emergency cleanup...
#   DataSafety: Containers remain STOPPED for safety:
#     - webapp
#     - database
#   Manually restart: docker start <container_name>
#   Cleanup complete, exiting with code 130
```

### Expected Result

✅ **PASS** if:
- Containers remain stopped (check `docker ps -a`)
- Log shows "Containers remain STOPPED for safety"
- Temp directories cleaned (check `/tmp/kopia-restore-*`)

❌ **FAIL** if:
- Containers auto-restarted (wrong behavior!)
- Temp dirs remain in `/tmp/`

### Cleanup

```bash
# Manually restart containers
docker start webapp database

# Or restart all stopped containers
docker ps -a --filter "status=exited" --format "{{.Names}}" | xargs docker start
```

---

## Test 4: Disaster Recovery Abort → Temp Cleanup

**Goal:** Verify that temp directories and incomplete archives are cleaned on DR abort.

### Test Procedure

```bash
# 1. Start DR bundle creation
sudo kopi-docka disaster-recovery

# 2. Wait for temp directory creation
# Look for log: "Creating recovery bundle..."

# 3. In another terminal, check temp dir exists:
ls -la /tmp/kopi-docka-recovery-*

# 4. Press Ctrl+C during bundle creation

# Expected output:
#   Received SIGINT - starting emergency cleanup...
#   Cleanup: Running temp_dir
#   Cleanup: Running incomplete_archive
#   Cleanup complete, exiting with code 130
```

### Expected Result

✅ **PASS** if:
- No `/tmp/kopi-docka-recovery-*` directories remain
- No incomplete `.tar.gz.enc` files remain
- Exit code is 130

❌ **FAIL** if:
- Temp directories remain in `/tmp/`
- Incomplete archives remain

### Verification

```bash
# Check for leftover temp dirs
ls -la /tmp/kopi-docka-recovery-* 2>&1 | grep "No such file"

# Check for incomplete archives
find /tmp -name "recovery-bundle-*.tar.gz.enc" -mmin -5
```

---

## Test 5: Zombie Process Prevention

**Goal:** Verify that no zombie processes remain after abort.

### Test Procedure

```bash
# 1. In one terminal, start backup
sudo kopi-docka backup

# 2. In another terminal, monitor processes
watch -n 1 "ps aux | grep -E '(docker|kopia|kopi-docka)' | grep -v grep"

# 3. Press Ctrl+C in backup terminal

# 4. Observe processes being terminated
# Expected: All docker/kopia subprocesses disappear within 6 seconds
```

### Expected Result

✅ **PASS** if:
- All subprocesses terminated within 6 seconds
- No zombie processes (`<defunct>`)
- No orphaned kopia/docker processes

❌ **FAIL** if:
- Zombie processes remain (check `ps aux | grep defunct`)
- kopia processes still running after cleanup

### Verification

```bash
# Check for zombie processes
ps aux | grep defunct

# Check for orphaned kopia processes
ps aux | grep kopia | grep -v grep

# Check for orphaned docker processes (from kopi-docka)
pgrep -a docker | grep -i kopi
```

---

## Test 6: Hook Abort → Hook Process Termination

**Goal:** Verify that hook processes are terminated on abort.

### Prerequisites

```bash
# 1. Create a slow hook script
cat > /tmp/slow-hook.sh << 'EOF'
#!/bin/bash
echo "Hook started"
sleep 60
echo "Hook finished"
EOF

chmod +x /tmp/slow-hook.sh

# 2. Configure hook in kopi-docka config
# Edit config: sudo kopi-docka advanced config edit
# Add:
# "backup": {
#   "hooks": {
#     "pre_backup": "/tmp/slow-hook.sh"
#   }
# }
```

### Test Procedure

```bash
# 1. Start backup (hook will execute)
sudo kopi-docka backup

# 2. Hook will start and sleep for 60s

# 3. Press Ctrl+C during hook execution

# Expected output:
#   Received SIGINT - starting emergency cleanup...
#   EMERGENCY: Terminating X tracked process(es)...
#     SIGTERM -> /tmp/slow-hook.sh (PID 12345)
#   Cleanup complete, exiting with code 130
```

### Expected Result

✅ **PASS** if:
- Hook process terminated (check `pgrep -f slow-hook.sh`)
- Exit code is 130
- No hung hook processes

❌ **FAIL** if:
- Hook process still running after cleanup
- Hook runs to completion despite abort

---

## Test 7: SIGKILL Limitation

**Goal:** Verify that SIGKILL cannot be caught (documented limitation).

### Test Procedure

```bash
# 1. Start backup in one terminal
sudo kopi-docka backup

# 2. In another terminal, get PID
PID=$(pgrep -f "kopi-docka backup")

# 3. Send SIGKILL
sudo kill -9 $PID

# 4. Check container status
docker ps
```

### Expected Result

✅ **DOCUMENTED LIMITATION**:
- Containers remain stopped (cleanup did NOT run)
- No graceful cleanup possible
- This is expected behavior for SIGKILL

**User should use SIGTERM instead:**
```bash
sudo kill -15 $PID  # Correct
```

---

## Test 8: Double SIGINT → Force Exit

**Goal:** Verify that second SIGINT during cleanup forces immediate exit.

### Test Procedure

```bash
# 1. Start backup
sudo kopi-docka backup

# 2. Press Ctrl+C once
# Cleanup starts...

# 3. IMMEDIATELY press Ctrl+C again (within 1 second)

# Expected output:
#   Received SIGINT - starting emergency cleanup...
#   Received SIGINT during cleanup - forcing exit
#   (exits immediately with code 130)
```

### Expected Result

✅ **PASS** if:
- First Ctrl+C starts cleanup
- Second Ctrl+C forces immediate exit
- Exit code is 130

---

## Integration Test Execution

To run the automated integration tests (requires root):

```bash
# Run all integration tests
sudo venv/bin/python -m pytest tests/integration/test_safe_exit_abort_scenarios.py -v

# Run specific test class
sudo venv/bin/python -m pytest tests/integration/test_safe_exit_abort_scenarios.py::TestBackupAbort -v

# Run with detailed output
sudo venv/bin/python -m pytest tests/integration/test_safe_exit_abort_scenarios.py -v -s
```

**Integration tests included:**
- ✅ `TestBackupAbort` (2 tests): Container restart, LIFO order
- ✅ `TestRestoreAbort` (2 tests): Containers stay stopped, temp cleanup
- ✅ `TestDisasterRecoveryAbort` (2 tests): Temp dir cleanup, archive removal
- ✅ `TestProcessLayerTermination` (2 tests): SIGTERM/SIGKILL subprocess termination
- ✅ `TestSignalHandlerEndToEnd` (1 test): Full e2e SIGINT scenario

**Total: 9 integration tests**

---

## Troubleshooting

### Container Not Restarting After Backup Abort

```bash
# Check ServiceContinuityHandler logs
sudo journalctl -u kopi-docka.service | grep ServiceContinuity

# Manual restart
docker start <container_name>
```

### Temp Directories Not Cleaned

```bash
# Should NOT happen - but if it does:
ls -la /tmp/kopi-docka-*
sudo rm -rf /tmp/kopi-docka-*

# Report issue:
# https://github.com/TZERO78/kopi-docka/issues
```

### Zombie Processes Remain

```bash
# Check for zombies
ps aux | grep defunct

# Should NOT happen - report if found
```

---

## Success Criteria Summary

All manual tests should PASS for SafeExitManager to be considered production-ready:

- [x] Test 1: Backup abort → containers restart ✅
- [x] Test 2: systemctl stop → containers restart ✅
- [x] Test 3: Restore abort → containers stay stopped ✅
- [x] Test 4: DR abort → temp cleanup ✅
- [x] Test 5: No zombie processes ✅
- [x] Test 6: Hook processes terminated ✅
- [x] Test 7: SIGKILL limitation documented ✅
- [x] Test 8: Double SIGINT force exit ✅

**Integration Tests:** 9/9 created (skipped without root, run with `sudo pytest`)

---

## Reporting Issues

If any test fails:

1. Capture logs: `sudo journalctl -u kopi-docka.service -n 100`
2. Check container states: `docker ps -a`
3. Check for zombies: `ps aux | grep defunct`
4. Report at: https://github.com/TZERO78/kopi-docka/issues

Include:
- Test name that failed
- Expected vs actual behavior
- Full log output
- Docker version: `docker version`
- OS version: `uname -a`
