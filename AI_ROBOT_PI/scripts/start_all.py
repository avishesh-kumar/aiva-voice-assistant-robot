#!/usr/bin/env python3
"""
Master launcher script for Raspberry Pi robot.
Starts and monitors all subsystems with auto-restart.
"""

import subprocess
import time
import signal
import sys
import os
import threading
from typing import List, Dict, Optional

# Configuration
RECONNECT_RETRY_DELAY = 2.0  # seconds between restart attempts
PROCESS_MONITOR_INTERVAL = 1.0  # seconds between health checks

# Subsystem definitions
SUBSYSTEMS = [
    {
        "name": "PI",
        "cmd": [sys.executable, "scripts/start_pi.py"],
        "cwd": os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "process": None,
        "thread": None,
        "output_buffer": [],
        "pgid": None  # Process group ID for clean termination
    },
    {
        "name": "AUDIO",
        "cmd": [sys.executable, "scripts/start_audio.py"],
        "cwd": os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "process": None,
        "thread": None,
        "output_buffer": [],
        "pgid": None
    },
    {
        "name": "CAMERA",
        "cmd": [sys.executable, "scripts/start_camera.py"],
        "cwd": os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "process": None,
        "thread": None,
        "output_buffer": [],
        "pgid": None
    }
]

class SubsystemMonitor:
    """Monitors and manages subsystem processes."""
    
    def __init__(self):
        self.running = True
        self.processes: List[Dict] = SUBSYSTEMS.copy()
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, sig, frame):
        """Handle termination signals."""
        print(f"\n[START_ALL] Signal {sig} received. Shutting down all subsystems...")
        self.running = False
        self._stop_all_processes()
    
    def _read_output(self, subsystem: Dict):
        """Read output from a subsystem process and print it with a prefix."""
        process = subsystem["process"]
        name = subsystem["name"]
        
        try:
            while self.running and process.poll() is None:
                line = process.stdout.readline()
                if line:
                    # Clean up the line and add prefix
                    line = line.rstrip('\n')
                    print(f"[{name}] {line}")
                    subsystem["output_buffer"].append(line)
                    
                    # Keep buffer size manageable
                    if len(subsystem["output_buffer"]) > 100:
                        subsystem["output_buffer"].pop(0)
        except:
            pass
    
    def _start_subsystem(self, subsystem: Dict):
        """Start a single subsystem process."""
        name = subsystem["name"]
        
        try:
            print(f"[START_ALL] Starting {name} subsystem...")
            
            # Start the process with its own process group
            process = subprocess.Popen(
                subsystem["cmd"],
                cwd=subsystem["cwd"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                start_new_session=True  # Creates new process group
            )
            
            subsystem["process"] = process
            
            # Store process group ID for clean termination
            if process.pid:
                subsystem["pgid"] = os.getpgid(process.pid)
            else:
                subsystem["pgid"] = None
            
            # Start output reading thread
            thread = threading.Thread(
                target=self._read_output,
                args=(subsystem,),
                daemon=True
            )
            subsystem["thread"] = thread
            thread.start()
            
            print(f"[START_ALL] {name} subsystem started (PID: {process.pid}, PGID: {subsystem['pgid']})")
            return True
            
        except Exception as e:
            print(f"[START_ALL] Failed to start {name} subsystem: {e}")
            subsystem["process"] = None
            subsystem["thread"] = None
            subsystem["pgid"] = None
            return False
    
    def _stop_subsystem(self, subsystem: Dict, force: bool = False):
        """Stop a single subsystem process using process group termination."""
        name = subsystem["name"]
        process = subsystem["process"]
        pgid = subsystem["pgid"]
        
        if process is None:
            return
            
        try:
            print(f"[START_ALL] Stopping {name} subsystem (PGID: {pgid})...")
            
            if pgid is not None:
                # Kill the entire process group
                try:
                    os.killpg(pgid, signal.SIGTERM)
                    print(f"[START_ALL] Sent SIGTERM to process group {pgid}")
                except ProcessLookupError:
                    print(f"[START_ALL] Process group {pgid} not found")
                except PermissionError:
                    print(f"[START_ALL] Permission denied killing process group {pgid}")
            
            # Wait for process to terminate
            try:
                process.wait(timeout=3 if force else 2)
                print(f"[START_ALL] {name} subsystem stopped gracefully")
            except subprocess.TimeoutExpired:
                if force and pgid is not None:
                    # Force kill the process group
                    try:
                        os.killpg(pgid, signal.SIGKILL)
                        print(f"[START_ALL] Sent SIGKILL to process group {pgid}")
                        process.wait()
                    except (ProcessLookupError, PermissionError):
                        pass
            
            subsystem["process"] = None
            subsystem["pgid"] = None
            
            # Wait for output thread to finish
            if subsystem["thread"] is not None:
                subsystem["thread"].join(timeout=1)
                subsystem["thread"] = None
                
            return True
            
        except Exception as e:
            print(f"[START_ALL] Error stopping {name} subsystem: {e}")
            return False
    
    def _stop_all_processes(self):
        """Stop all running subsystem processes."""
        print("\n[START_ALL] Stopping all subsystems...")
        
        # First pass: graceful termination of all process groups
        for subsystem in self.processes:
            if subsystem["process"] is not None:
                self._stop_subsystem(subsystem, force=False)
        
        # Second pass: force kill any remaining process groups
        time.sleep(1)
        for subsystem in self.processes:
            if subsystem["process"] is not None:
                self._stop_subsystem(subsystem, force=True)
        
        print("[START_ALL] All subsystems stopped")
    
    def _check_and_restart_subsystems(self):
        """Check all subsystems and restart any that have stopped."""
        for subsystem in self.processes:
            process = subsystem["process"]
            name = subsystem["name"]
            
            if process is None:
                # Process not running, try to start it
                print(f"[START_ALL] {name} subsystem is not running, attempting to start...")
                if not self._start_subsystem(subsystem):
                    print(f"[START_ALL] Failed to start {name}, will retry in {RECONNECT_RETRY_DELAY} seconds")
            else:
                # Check if process is still alive
                return_code = process.poll()
                if return_code is not None:
                    # Process has exited
                    print(f"[START_ALL] {name} subsystem exited with code {return_code}")
                    subsystem["process"] = None
                    subsystem["pgid"] = None
                    
                    # Clean up thread
                    if subsystem["thread"] is not None:
                        subsystem["thread"].join(timeout=1)
                        subsystem["thread"] = None
    
    def run(self):
        """Main monitoring loop."""
        print("=" * 60)
        print("STARTING ALL ROBOT SUBSYSTEMS")
        print("=" * 60)
        print(f"[START_ALL] Python executable: {sys.executable}")
        print(f"[START_ALL] Working directory: {os.getcwd()}")
        print(f"[START_ALL] Reconnect delay: {RECONNECT_RETRY_DELAY} seconds")
        print("=" * 60 + "\n")
        
        # Initial startup of all subsystems
        print("[START_ALL] Starting all subsystems...")
        for subsystem in self.processes:
            self._start_subsystem(subsystem)
            time.sleep(0.5)  # Small delay between starts
        
        print("\n[START_ALL] All subsystems started. Monitoring...")
        print("[START_ALL] Press Ctrl+C to stop all subsystems\n")
        
        # Main monitoring loop
        while self.running:
            try:
                # Check and restart subsystems
                self._check_and_restart_subsystems()
                
                # Wait before next check
                time.sleep(PROCESS_MONITOR_INTERVAL)
                
            except KeyboardInterrupt:
                print("\n[START_ALL] Interrupted by user")
                self.running = False
                break
            except Exception as e:
                print(f"[START_ALL] Monitoring error: {e}")
                time.sleep(PROCESS_MONITOR_INTERVAL)
        
        # Clean shutdown
        self._stop_all_processes()
        print("[START_ALL] Master launcher stopped")

def main():
    """Main entry point."""
    monitor = SubsystemMonitor()
    monitor.run()

if __name__ == "__main__":
    main()
