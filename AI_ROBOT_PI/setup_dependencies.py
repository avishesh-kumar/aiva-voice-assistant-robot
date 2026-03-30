#!/usr/bin/env python3
"""
Setup script for installing required dependencies on Raspberry Pi.
Run this before using the robot modules.
"""
import sys
import subprocess
import os

def run_command(cmd, description):
    """Run a shell command and print status."""
    print(f"\n{'='*60}")
    print(f"Installing: {description}")
    print(f"Command: {cmd}")
    print('='*60)
    
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"? {description} installed successfully")
            return True
        else:
            print(f"? Failed to install {description}")
            print(f"Error: {result.stderr}")
            return False
    except Exception as e:
        print(f"? Error: {e}")
        return False

def main():
    print("Raspberry Pi Robot - Dependency Installer")
    print("="*60)
    
    # Check if we're on Raspberry Pi
    try:
        with open('/proc/cpuinfo', 'r') as f:
            if 'Raspberry Pi' not in f.read():
                print("Warning: This doesn't appear to be a Raspberry Pi")
                print("Some dependencies may not be installable.")
    except:
        print("Warning: Could not detect Raspberry Pi")
    
    # Install required packages
    dependencies = [
        # GPIO libraries
        ("sudo apt-get update && sudo apt-get install -y python3-gpiozero python3-rpi.gpio", "GPIO libraries"),
        
        # Python packages
        ("pip3 install --upgrade pip", "Pip upgrade"),
        
        # Optional: For more accurate timing
        ("pip3 install python-periphery", "Periphery library"),
    ]
    
    success_count = 0
    for cmd, desc in dependencies:
        if run_command(cmd, desc):
            success_count += 1
    
    print(f"\n{'='*60}")
    print(f"Installation complete: {success_count}/{len(dependencies)} packages installed")
    
    # Create symbolic links for imports
    print("\nSetting up project structure...")
    project_root = os.path.dirname(os.path.abspath(__file__))
    
    # Add project root to Python path
    with open(os.path.expanduser('~/.bashrc'), 'a') as f:
        f.write(f'\n# Raspberry Pi Robot Project\n')
        f.write(f'export PYTHONPATH="{project_root}:$PYTHONPATH"\n')
    
    print("? Added project to PYTHONPATH")
    print("\nPlease restart your terminal or run: source ~/.bashrc")
    
    # Test imports
    print("\nTesting imports...")
    test_imports = [
        "import sys",
        "import time",
        "try:\n    from gpiozero import DigitalOutputDevice\n    print('? gpiozero available')\nexcept:\n    print('? gpiozero not available')",
        "try:\n    import RPi.GPIO as GPIO\n    print('? RPi.GPIO available')\nexcept:\n    print('? RPi.GPIO not available')",
    ]
    
    for import_stmt in test_imports:
        try:
            exec(import_stmt)
        except:
            pass

if __name__ == "__main__":
    main()