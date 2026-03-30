#!/usr/bin/env python3
# scripts/start_camera_receiver.py

import sys
import os
import time
import signal

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vision.camera_receiver import CameraReceiver

def main():
    print("=" * 60)
    print("Starting Mac Camera Receiver")
    print("=" * 60)
    
    # Create receiver instance
    receiver = CameraReceiver(
        host="0.0.0.0",
        port=8891,
        window_name="Robot Camera"
    )
    
    # Setup signal handler for graceful shutdown
    def signal_handler(sig, frame):
        print("\nShutdown signal received...")
        receiver.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Start receiver
        receiver.start()
        
        # Keep main thread alive
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        receiver.stop()
        print("Camera receiver terminated")

if __name__ == "__main__":
    main()
