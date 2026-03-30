#!/usr/bin/env python3
# scripts/start_camera.py

import sys
import os
import time
import signal

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.network_config import MAC_HOST, AUDIO_PORT

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from camera.camera_stream import CameraStreamer, load_network_config

# Reconnection settings with exponential backoff
MIN_RECONNECT_DELAY = 2.0  # seconds
MAX_RECONNECT_DELAY = 10.0  # seconds
STABLE_RUN_TIME = 10.0  # seconds to consider run stable

def main():
    print("=" * 60)
    print("[CAMERA] Starting Camera Streaming System")
    print("=" * 60)
    
    # Setup signal handler for graceful shutdown
    def signal_handler(sig, frame):
        print(f"\n[CAMERA] Signal {sig} received. Shutting down...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Exponential backoff state
    current_delay = MIN_RECONNECT_DELAY
    reconnect_attempts = 0
    
    while True:
        streamer = None
        start_time = None
        
        try:
            # Load configuration (reload each time in case config changed)
            host, port = load_network_config()
            
            if reconnect_attempts == 0:
                print(f"[CAMERA] Initial connection to {host}:{port}")
            else:
                print(f"[CAMERA] Reconnection attempt {reconnect_attempts}, delay: {current_delay:.1f}s")
            
            # Create a fresh streamer instance
            streamer = CameraStreamer(
                host=host,
                port=port,
                fps=15,
                jpeg_quality=70,
                width=640,
                height=480
            )
            
            # Start streaming
            streamer.start()
            start_time = time.monotonic()
            
            # Monitor the streamer
            print("[CAMERA] Camera stream active")
            
            # Keep monitoring the streamer while it's running
            while True:
                time.sleep(1)
                
                # Check if streamer thread is still alive
                if not hasattr(streamer, 'stream_thread') or not streamer.stream_thread.is_alive():
                    run_duration = time.monotonic() - start_time
                    print(f"[CAMERA] Camera stream stopped after {run_duration:.1f}s")
                    
                    # Reset backoff if we had a stable run
                    if run_duration >= STABLE_RUN_TIME:
                        print(f"[CAMERA] Stable run ({run_duration:.1f}s), resetting backoff")
                        current_delay = MIN_RECONNECT_DELAY
                    break
                
                # Optional: Add additional health checks here
                
        except KeyboardInterrupt:
            print("\n[CAMERA] Interrupted by user")
            if streamer is not None:
                streamer.stop()
            break
            
        except Exception as e:
            print(f"[CAMERA] Unexpected error: {e}")
            reconnect_attempts += 1
            
        finally:
            # Ensure streamer is stopped safely
            if streamer is not None:
                try:
                    streamer.stop()
                except Exception as e:
                    print(f"[CAMERA] Error during stop: {e}")
            
            # If we're here due to error or stream stopped, apply backoff
            if streamer is not None:
                # Apply exponential backoff
                current_delay = min(current_delay * 2, MAX_RECONNECT_DELAY)
                print(f"[CAMERA] Waiting {current_delay:.1f}s before reconnection...")
                time.sleep(current_delay)
            else:
                # If streamer was never created, use current delay
                print(f"[CAMERA] Waiting {current_delay:.1f}s before retry...")
                time.sleep(current_delay)
    
    print("[CAMERA] Camera streaming terminated")

if __name__ == "__main__":
    main()
