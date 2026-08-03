import argparse
import asyncio

import uvicorn


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="donnietts")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="run the controller HTTP service")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    worker = subparsers.add_parser("worker", help="run the announcement scheduler")
    worker.add_argument(
        "--poll-seconds",
        type=float,
        default=30.0,
        help="seconds between scheduling passes (default: 30)",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "serve":
        uvicorn.run(
            "donnietts.app:app",
            host=args.host,
            port=args.port,
            workers=1,
        )
    elif args.command == "worker":
        from donnietts.settings import ControllerSettings
        from donnietts.worker import run_worker

        settings = ControllerSettings.from_environment()
        asyncio.run(run_worker(settings, poll_interval_seconds=args.poll_seconds))


if __name__ == "__main__":
    main()
