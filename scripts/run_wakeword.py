#!/usr/bin/env python3
"""
Wake Word Listener Entry Point
===============================
Listens for "Hey Jarvis" and routes voice commands through the agent system.

Prerequisites:
  - Web server running (adk-web.service)
  - Mic HAT configured in ALSA
  - pip install openwakeword pyaudio webrtcvad

Usage:
  python scripts/run_wakeword.py
  python scripts/run_wakeword.py --api-url http://localhost:8000
  python scripts/run_wakeword.py --wake-word hey_jarvis --threshold 0.4
"""

import sys
import os
import asyncio
import argparse
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from config.google_runtime import env_flag


def _env_int(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def main():
    parser = argparse.ArgumentParser(description="Wake Word Listener")
    parser.add_argument(
        "--api-url", default=os.getenv("WAKEWORD_API_URL") or os.getenv("WAKEWORD_API_BASE_URL") or "http://localhost:8000",
        help="Web server URL (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--wake-word", default=os.getenv("WAKEWORD_MODEL", "hey_jarvis"),
        help="Wake word model name (default: hey_jarvis)"
    )
    parser.add_argument(
        "--threshold", type=float,
        default=float(os.getenv("WAKEWORD_THRESHOLD", "0.4")),
        help="Detection confidence threshold (default: 0.4)"
    )
    parser.add_argument(
        "--mic-device", type=int, default=_env_int("WAKEWORD_INPUT_DEVICE"),
        help="ALSA mic device index (default: system default)"
    )
    parser.add_argument(
        "--speaker-device", type=int, default=_env_int("WAKEWORD_OUTPUT_DEVICE"),
        help="ALSA speaker device index (default: system default)"
    )
    parser.add_argument(
        "--no-listening-cue", action="store_true",
        help="Disable local audio cue after wake word detection"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging"
    )
    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    from monitoring.logging_config import setup_logging

    setup_logging(
        level="DEBUG" if args.verbose else "INFO",
        use_cloud_logging=env_flag("USE_CLOUD_LOGGING", bool(os.getenv("GOOGLE_CLOUD_PROJECT"))),
        project_id=os.getenv("GOOGLE_CLOUD_PROJECT"),
    )

    # API token from env (if web server requires auth)
    api_token = os.getenv("API_TOKEN")

    from interfaces.wakeword_interface import WakeWordInterface

    interface = WakeWordInterface(
        api_url=args.api_url,
        wake_word=args.wake_word,
        threshold=args.threshold,
        mic_device=args.mic_device,
        speaker_device=args.speaker_device,
        api_token=api_token,
        user_id=os.getenv("WAKEWORD_USER_ID", "rpi-voice").strip() or "rpi-voice",
        listening_cue=not args.no_listening_cue and os.getenv("WAKEWORD_LISTENING_CUE", "true").lower() in ("1", "true", "yes", "on"),
    )

    print(f"Starting wake word listener...")
    print(f"  API: {args.api_url}")
    print(f"  Wake word: {args.wake_word} (threshold: {args.threshold})")
    print(f"  Listening cue: {'ON' if interface.listening_cue else 'OFF'}")
    print(f"  Say '{args.wake_word.replace('_', ' ')}' to activate")
    print()

    try:
        asyncio.run(interface.start())
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
