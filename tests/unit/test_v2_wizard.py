"""
Automated test for Kopi-Docka v2.1 Setup Wizard.

This test clicks through the entire wizard to catch errors automatically.
"""

import pytest
from textual.pilot import Pilot

from kopi_docka.v2.ui.app import KopiDockaApp


@pytest.mark.asyncio
async def test_wizard_complete_flow():
    """Test complete wizard flow through backend selection."""
    app = KopiDockaApp()
    
    async with app.run_test() as pilot:
        # Give UI time to render
        await pilot.pause()
        
        # Step 1: Welcome Screen - Verify elements
        screen = pilot.app.screen
        assert screen.query_one("#welcome-container")
        assert screen.query_one("#btn-next")
        
        # Step 2: Navigate to Backend Selection
        await pilot.click("#btn-next")
        await pilot.pause()
        
        # Step 3: Verify Backend Selection Screen
        screen = pilot.app.screen
        assert screen.query_one("#selection-container")
        assert screen.query_one("#backend-list")
        
        # Step 4: Select first backend (Filesystem)
        await pilot.click("OptionList")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        
        # Step 5: Test navigation back
        await pilot.press("escape")
        await pilot.pause()
        
        # Step 7: Verify we're back at welcome
        screen = pilot.app.screen
        assert screen.query_one("#welcome-container")


@pytest.mark.asyncio
async def test_wizard_welcome_screen():
    """Test Welcome Screen components."""
    app = KopiDockaApp()
    
    async with app.run_test() as pilot:
        await pilot.pause()
        
        # Verify Welcome Screen elements exist (use screen property)
        screen = pilot.app.screen
        assert screen.query_one("#welcome-container")
        assert screen.query_one("#title")
        assert screen.query_one("#btn-next")
        assert screen.query_one("#btn-quit")


@pytest.mark.asyncio
async def test_wizard_backend_selection():
    """Test Backend Selection Screen."""
    app = KopiDockaApp()
    
    async with app.run_test() as pilot:
        await pilot.pause()
        
        # Navigate to backend selection
        await pilot.click("#btn-next")
        await pilot.pause()
        
        # Verify Backend Selection elements
        screen = pilot.app.screen
        assert screen.query_one("#selection-container")
        assert screen.query_one("#backend-list")
        assert screen.query_one("#btn-back")
        assert screen.query_one("#btn-help")
        assert screen.query_one("#btn-next")


@pytest.mark.asyncio
async def test_wizard_navigation():
    """Test navigation between screens."""
    app = KopiDockaApp()
    
    async with app.run_test() as pilot:
        await pilot.pause()
        
        # Go to backend selection
        await pilot.click("#btn-next")
        await pilot.pause()
        
        # Go back to welcome
        await pilot.click("#btn-back")
        await pilot.pause()
        
        # Verify we're back at welcome screen
        screen = pilot.app.screen
        assert screen.query_one("#welcome-container")
        
        # Test Quit button
        await pilot.click("#btn-quit")
        await pilot.pause()


@pytest.mark.asyncio
async def test_wizard_keyboard_shortcuts():
    """Test keyboard shortcuts work."""
    app = KopiDockaApp()
    
    async with app.run_test() as pilot:
        await pilot.pause()
        
        # Test 'n' for Next
        await pilot.press("n")
        await pilot.pause()
        
        # Should be on backend selection now
        screen = pilot.app.screen
        assert screen.query_one("#selection-container")
        
        # Test 'h' for Help
        await pilot.press("h")
        await pilot.pause()
        
        # Test Escape for Back
        await pilot.press("escape")
        await pilot.pause()
        
        # Should be back at welcome
        screen = pilot.app.screen
        assert screen.query_one("#welcome-container")


if __name__ == "__main__":
    import asyncio
    
    print("Running wizard tests...")
    
    # Run all tests
    asyncio.run(test_wizard_welcome_screen())
    print("✓ Welcome Screen test passed")
    
    asyncio.run(test_wizard_backend_selection())
    print("✓ Backend Selection test passed")
    
    asyncio.run(test_wizard_navigation())
    print("✓ Navigation test passed")
    
    asyncio.run(test_wizard_keyboard_shortcuts())
    print("✓ Keyboard shortcuts test passed")
    
    asyncio.run(test_wizard_complete_flow())
    print("✓ Complete flow test passed")
    
    print("\n🎉 All wizard tests passed!")
