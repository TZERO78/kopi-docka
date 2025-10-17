#!/usr/bin/env python3
"""
Complete workflow test for Kopi-Docka v2 CLI
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# Colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

def print_test(name):
    print(f"\n{BLUE}[TEST]{RESET} {name}")

def print_success(msg):
    print(f"{GREEN}✓{RESET} {msg}")

def print_error(msg):
    print(f"{RED}✗{RESET} {msg}")

def print_info(msg):
    print(f"{YELLOW}→{RESET} {msg}")

def run_cli(*args):
    """Run CLI command and return result"""
    cmd = ["python3", "kopi_docka/v2/test_cli.py"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result

def test_version():
    print_test("Version command")
    result = run_cli("version")
    if result.returncode == 0 and "Kopi-Docka" in result.stdout:
        print_success("Version command works")
        return True
    else:
        print_error(f"Version command failed: {result.stderr}")
        return False

def test_info():
    print_test("Info command")
    result = run_cli("info")
    if result.returncode == 0 and "Language" in result.stdout:
        print_success("Info command works")
        return True
    else:
        print_error(f"Info command failed: {result.stderr}")
        return False

def test_help():
    print_test("Help pages")
    
    tests = [
        (["--help"], "Main help"),
        (["setup", "--help"], "Setup help"),
        (["repo", "--help"], "Repo help"),
    ]
    
    for args, name in tests:
        result = run_cli(*args)
        if result.returncode == 0:
            print_success(f"{name} works")
        else:
            print_error(f"{name} failed")
            return False
    
    return True

def test_config_creation():
    print_test("Config creation (direct)")
    
    from kopi_docka.v2.config import save_backend_config, get_config_path
    
    # Create test config
    config = {
        "type": "filesystem",
        "repository_path": "/tmp/kopia-test",
        "credentials": {}
    }
    
    try:
        config_path = save_backend_config("local", config)
        print_success(f"Config saved to: {config_path}")
        
        # Check file exists
        if config_path.exists():
            print_success("Config file exists")
            
            # Check permissions
            stat = os.stat(config_path)
            mode = oct(stat.st_mode)[-3:]
            if mode == "600":
                print_success(f"Permissions correct: {mode}")
            else:
                print_error(f"Permissions wrong: {mode} (expected 600)")
                return False
            
            # Check content
            with open(config_path) as f:
                data = json.load(f)
            
            if data.get("backend_type") == "local":
                print_success("Config content correct")
            else:
                print_error("Config content wrong")
                return False
            
            return True
        else:
            print_error("Config file not created")
            return False
            
    except Exception as e:
        print_error(f"Config creation failed: {e}")
        return False

def test_repo_status_with_config():
    print_test("Repo status with config")
    
    result = run_cli("repo", "status")
    
    if result.returncode == 0:
        print_success("Repo status works")
        print_info("Output:")
        for line in result.stdout.split('\n')[:10]:
            if line.strip():
                print(f"  {line}")
        return True
    else:
        print_error(f"Repo status failed: {result.stderr}")
        return False

def test_error_handling():
    print_test("Error handling")
    
    # Delete config first
    from kopi_docka.v2.config import delete_config
    delete_config()
    print_info("Config deleted")
    
    # Test repo init without config
    result = run_cli("repo", "status")
    
    if result.returncode == 0 and "No backend configured" in result.stdout:
        print_success("Error handling works (no config)")
        return True
    else:
        print_error("Error handling failed")
        return False

def test_multi_language():
    print_test("Multi-language support")
    
    # Test German
    result = run_cli("--language", "de", "info")
    if result.returncode == 0:
        print_success("German language works")
    else:
        print_error("German language failed")
        return False
    
    # Test English
    result = run_cli("--language", "en", "info")
    if result.returncode == 0:
        print_success("English language works")
    else:
        print_error("English language failed")
        return False
    
    return True

def main():
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Kopi-Docka v2 Complete Workflow Test{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")
    
    tests = [
        ("Version", test_version),
        ("Info", test_info),
        ("Help Pages", test_help),
        ("Multi-Language", test_multi_language),
        ("Error Handling", test_error_handling),
        ("Config Creation", test_config_creation),
        ("Repo Status", test_repo_status_with_config),
    ]
    
    results = {}
    
    for name, test_func in tests:
        try:
            results[name] = test_func()
        except Exception as e:
            print_error(f"Test crashed: {e}")
            results[name] = False
    
    # Summary
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Test Summary{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        if result:
            print(f"{GREEN}✓{RESET} {name}")
        else:
            print(f"{RED}✗{RESET} {name}")
    
    print(f"\n{BLUE}Result: {passed}/{total} tests passed{RESET}")
    
    if passed == total:
        print(f"{GREEN}All tests passed! 🎉{RESET}\n")
        return 0
    else:
        print(f"{RED}Some tests failed{RESET}\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
