################################################################################
# KOPI-DOCKA
#
# @file:        test_process_lock.py
# @description: Unit tests for ProcessLock helper
################################################################################

"""Unit tests for ProcessLock - prevents concurrent backup execution."""

import os
import tempfile
import multiprocessing
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from kopi_docka.helpers.process_lock import (
    ProcessLock,
    DEFAULT_LOCK_PATH,
    FALLBACK_LOCK_PATH,
)


class TestProcessLockBasic:
    """Basic functionality tests."""

    def test_acquire_and_release(self, tmp_path):
        """Test basic lock acquisition and release."""
        lock_file = tmp_path / "test.lock"
        lock = ProcessLock(str(lock_file))
        
        assert lock.acquire() is True
        assert lock.is_locked() is True
        assert lock_file.exists()
        
        lock.release()
        assert lock.is_locked() is False

    def test_lock_writes_pid(self, tmp_path):
        """Test that lock file contains PID."""
        lock_file = tmp_path / "test.lock"
        lock = ProcessLock(str(lock_file))
        
        lock.acquire()
        
        content = lock_file.read_text().strip()
        assert content == str(os.getpid())
        
        lock.release()

    def test_get_holder_pid(self, tmp_path):
        """Test reading holder PID from lock file."""
        lock_file = tmp_path / "test.lock"
        lock = ProcessLock(str(lock_file))
        
        lock.acquire()
        
        holder_pid = lock.get_holder_pid()
        assert holder_pid == os.getpid()
        
        lock.release()

    def test_context_manager(self, tmp_path):
        """Test using ProcessLock as context manager."""
        lock_file = tmp_path / "test.lock"
        
        with ProcessLock(str(lock_file)) as lock:
            assert lock.is_locked() is True
        
        # After context, should be released
        lock2 = ProcessLock(str(lock_file))
        assert lock2.acquire() is True
        lock2.release()


class TestProcessLockContention:
    """Tests for lock contention scenarios."""

    def test_second_lock_fails(self, tmp_path):
        """Test that second lock acquisition fails."""
        lock_file = tmp_path / "test.lock"
        
        lock1 = ProcessLock(str(lock_file))
        lock2 = ProcessLock(str(lock_file))
        
        assert lock1.acquire() is True
        assert lock2.acquire() is False  # Should fail - already locked
        
        lock1.release()
        
        # Now lock2 should succeed
        assert lock2.acquire() is True
        lock2.release()

    def test_context_manager_raises_on_locked(self, tmp_path):
        """Test that context manager raises if lock is held."""
        lock_file = tmp_path / "test.lock"
        
        lock1 = ProcessLock(str(lock_file))
        lock1.acquire()
        
        with pytest.raises(BlockingIOError) as exc_info:
            with ProcessLock(str(lock_file)):
                pass
        
        assert "Lock held by another process" in str(exc_info.value)
        lock1.release()


class TestProcessLockMultiprocess:
    """Tests involving multiple processes."""

    def test_cross_process_locking(self, tmp_path):
        """Test that lock works across processes."""
        lock_file = tmp_path / "test.lock"
        result_file = tmp_path / "result.txt"
        
        def child_process(lock_path, result_path):
            """Child process tries to acquire lock."""
            lock = ProcessLock(lock_path)
            result = lock.acquire()
            Path(result_path).write_text(str(result))
            if result:
                lock.release()
        
        # Parent acquires lock
        parent_lock = ProcessLock(str(lock_file))
        parent_lock.acquire()
        
        # Start child process
        p = multiprocessing.Process(
            target=child_process,
            args=(str(lock_file), str(result_file))
        )
        p.start()
        p.join(timeout=5)
        
        # Child should have failed to acquire
        result = result_file.read_text()
        assert result == "False"
        
        # Release parent lock
        parent_lock.release()
        
        # Now child should succeed
        p2 = multiprocessing.Process(
            target=child_process,
            args=(str(lock_file), str(result_file))
        )
        p2.start()
        p2.join(timeout=5)
        
        result = result_file.read_text()
        assert result == "True"


class TestProcessLockPathSelection:
    """Tests for lock path selection logic."""

    def test_uses_run_if_writable(self):
        """Test that /run is used if writable."""
        with patch("os.access", return_value=True):
            lock = ProcessLock()
            assert lock.lock_path == Path(DEFAULT_LOCK_PATH)

    def test_uses_fallback_if_run_not_writable(self):
        """Test fallback to /tmp if /run not writable."""
        with patch("os.access", return_value=False):
            lock = ProcessLock()
            assert lock.lock_path == Path(FALLBACK_LOCK_PATH)

    def test_custom_path_override(self, tmp_path):
        """Test that custom path overrides default."""
        custom_path = tmp_path / "custom.lock"
        lock = ProcessLock(str(custom_path))
        assert lock.lock_path == custom_path


class TestProcessLockEdgeCases:
    """Edge case and error handling tests."""

    def test_get_holder_pid_no_file(self, tmp_path):
        """Test get_holder_pid when lock file doesn't exist."""
        lock = ProcessLock(str(tmp_path / "nonexistent.lock"))
        assert lock.get_holder_pid() is None

    def test_get_holder_pid_invalid_content(self, tmp_path):
        """Test get_holder_pid with invalid file content."""
        lock_file = tmp_path / "test.lock"
        lock_file.write_text("not-a-number")
        
        lock = ProcessLock(str(lock_file))
        assert lock.get_holder_pid() is None

    def test_release_without_acquire(self, tmp_path):
        """Test that release without acquire doesn't crash."""
        lock = ProcessLock(str(tmp_path / "test.lock"))
        lock.release()  # Should not raise

    def test_double_release(self, tmp_path):
        """Test that double release doesn't crash."""
        lock_file = tmp_path / "test.lock"
        lock = ProcessLock(str(lock_file))
        
        lock.acquire()
        lock.release()
        lock.release()  # Should not raise

    def test_destructor_releases_lock(self, tmp_path):
        """Test that destructor releases the lock."""
        lock_file = tmp_path / "test.lock"
        
        def create_and_destroy():
            lock = ProcessLock(str(lock_file))
            lock.acquire()
            # Lock goes out of scope and __del__ is called
        
        create_and_destroy()
        
        # Should be able to acquire now
        lock2 = ProcessLock(str(lock_file))
        assert lock2.acquire() is True
        lock2.release()


class TestProcessLockIntegration:
    """Integration tests simulating real backup scenarios."""

    def test_backup_lock_scenario(self, tmp_path):
        """Simulate the backup command locking scenario."""
        lock_file = tmp_path / "kopi-docka.lock"
        
        # First backup starts
        backup1_lock = ProcessLock(str(lock_file))
        assert backup1_lock.acquire() is True
        
        # Second backup tries to start (e.g., cron while manual is running)
        backup2_lock = ProcessLock(str(lock_file))
        acquired = backup2_lock.acquire()
        
        if not acquired:
            # This is the expected path - second backup should skip
            holder_pid = backup2_lock.get_holder_pid()
            assert holder_pid == os.getpid()  # Same process in test
        
        # First backup finishes
        backup1_lock.release()
        
        # Now a new backup can start
        backup3_lock = ProcessLock(str(lock_file))
        assert backup3_lock.acquire() is True
        backup3_lock.release()
