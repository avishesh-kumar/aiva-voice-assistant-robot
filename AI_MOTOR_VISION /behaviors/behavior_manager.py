# behaviors/behavior_manager.py

import threading
import time
from typing import Optional
from utils.logger import setup_logger

logger = setup_logger("BEHAVIOR", log_file="system.log")


class BehaviorManager:
    """
    Runs exactly ONE autonomous behavior at a time.
    Behaviors must be cooperative and check stop_event frequently.
    """

    def __init__(self):
        self._active_behavior_name: Optional[str] = None
        self._behavior_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    # -------------------------------------------------
    # Public API
    # -------------------------------------------------

    def start_behavior(self, name: str, target_fn, *args, **kwargs) -> bool:
        """
        Start a behavior loop in a background thread.

        Args:
            name: Behavior name (e.g., 'FOLLOW_PERSON')
            target_fn: Function implementing the behavior loop
            *args, **kwargs: Passed to target_fn

        Returns:
            True if behavior started, False if another is already running
        """
        with self._lock:
            if self._behavior_thread and self._behavior_thread.is_alive():
                logger.warning(
                    f"Behavior '{self._active_behavior_name}' already running. "
                    f"Cannot start '{name}'."
                )
                return False

            # Clear any previous stop signal
            self._stop_event.clear()
            self._active_behavior_name = name

            # Wrap the behavior so we always clean up
            def _run():
                logger.info(f"Behavior started: {name}")
                try:
                    target_fn(self._stop_event, *args, **kwargs)
                except Exception:
                    logger.exception(f"Behavior '{name}' crashed")
                finally:
                    logger.info(f"Behavior stopped: {name}")
                    with self._lock:
                        self._active_behavior_name = None
                        self._behavior_thread = None
                        self._stop_event.clear()

            self._behavior_thread = threading.Thread(
                target=_run,
                daemon=True,
            )
            self._behavior_thread.start()
            return True

    def stop_behavior(self):
        """
        Request the currently running behavior to stop.
        """
        with self._lock:
            if not self._behavior_thread:
                return

            logger.info(f"Stopping behavior: {self._active_behavior_name}")
            self._stop_event.set()

    def is_running(self) -> bool:
        """
        Check if a behavior is currently running.
        """
        return (
            self._behavior_thread is not None
            and self._behavior_thread.is_alive()
        )

    def current_behavior(self) -> Optional[str]:
        """
        Return the name of the active behavior, if any.
        """
        return self._active_behavior_name

