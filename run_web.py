"""
Web Dashboard Runner for Google Workspace ADK Multi-Agent System

Usage:
    python run_web.py                    # Start on localhost:8000
    python run_web.py --port 9000        # Custom port
    python run_web.py --host 0.0.0.0     # Bind to all interfaces (for Docker/Cloud Run)
"""

import os
import sys
import logging
import argparse

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()

# Set interface context so HITL logic knows not to use blocking terminal input
os.environ.setdefault('HITL_INTERFACE', 'web')


def main():
    parser = argparse.ArgumentParser(description="Google Workspace ADK Web Dashboard")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to (default: 8000)")
    args = parser.parse_args()

    print("=" * 60)
    print("  Google Workspace ADK - Web Dashboard")
    print(f"  Starting at http://{args.host}:{args.port}")
    print("=" * 60)
    print()

    # Import here to avoid circular imports
    from interfaces.web_interface import WebInterface
    from web.app import create_app

    # Create interface (system initialization happens in FastAPI lifespan
    # because APScheduler.start() needs a running event loop)
    interface = WebInterface()

    # Create FastAPI app with lifespan-based init
    app = create_app(interface)

    # Run with uvicorn (starts the event loop, triggers lifespan startup)
    import uvicorn
    print(f"Dashboard: http://{args.host}:{args.port}")
    print(f"API Docs:  http://{args.host}:{args.port}/docs")
    print()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nShutdown complete")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
