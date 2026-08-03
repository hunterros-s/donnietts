import argparse
import asyncio

import httpx
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

    say = subparsers.add_parser("say", help="render and speak an announcement template")
    say.add_argument(
        "template",
        nargs="*",
        help="template text; defaults to the daily briefing template",
    )

    subparsers.add_parser("schedule", help="show the current schedule")

    runs = subparsers.add_parser("runs", help="show recent announcement runs")
    runs.add_argument(
        "--limit",
        type=int,
        default=20,
        help="maximum runs to show (default: 20)",
    )

    run = subparsers.add_parser(
        "run",
        help="run the controller API and announcement worker together",
    )
    run.add_argument("--host", default="127.0.0.1")
    run.add_argument("--port", type=int, default=8000)
    run.add_argument(
        "--poll-seconds",
        type=float,
        default=30.0,
        help="seconds between scheduling passes (default: 30)",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    from donnietts.runner import configure_logging

    configure_logging()
    if args.command == "serve":
        uvicorn.run(
            "donnietts.app:app",
            host=args.host,
            port=args.port,
            workers=1,
            log_config=None,
        )
    elif args.command == "worker":
        from donnietts.settings import ControllerSettings
        from donnietts.worker import run_worker

        settings = ControllerSettings.from_environment()
        asyncio.run(run_worker(settings, poll_interval_seconds=args.poll_seconds))
    elif args.command == "run":
        from donnietts.runner import run_controller
        from donnietts.settings import ControllerSettings

        settings = ControllerSettings.from_environment()
        asyncio.run(
            run_controller(
                settings,
                host=args.host,
                port=args.port,
                poll_interval_seconds=args.poll_seconds,
            )
        )
    elif args.command == "say":
        from donnietts.rendering import DEFAULT_TEMPLATE
        from donnietts.say import say as say_once
        from donnietts.settings import ControllerSettings

        settings = ControllerSettings.from_environment()
        template = " ".join(args.template) or DEFAULT_TEMPLATE
        try:
            rendered = asyncio.run(say_once(settings, template))
        except httpx.TimeoutException:
            raise SystemExit(
                f"Speech service at {settings.speech.base_url} timed out after "
                f"{settings.speech.generation_timeout_seconds:g}s. It may still be "
                "loading the model; check its status with /health/ready."
            )
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 503:
                raise SystemExit(
                    "Speech service is not ready (HTTP 503) — it is probably still "
                    "loading the model. Retry in a moment."
                ) from error
            raise SystemExit(
                f"Speech service returned HTTP {error.response.status_code} "
                f"for {error.request.url}."
            ) from error
        except httpx.RequestError as error:
            raise SystemExit(
                f"Could not reach the speech service at {settings.speech.base_url} "
                f"({type(error).__name__}). Is it running? Start it with "
                "'uv run qwen-speech serve' from services/qwen-speech."
            ) from error
        except Exception as error:
            raise SystemExit(f"Speech failed: {error}") from error
        print(rendered)
    elif args.command == "schedule":
        from donnietts.reporting import schedule_text
        from donnietts.settings import ControllerSettings

        settings = ControllerSettings.from_environment()
        print(asyncio.run(schedule_text(settings)))
    elif args.command == "runs":
        from donnietts.reporting import runs_text
        from donnietts.settings import ControllerSettings

        settings = ControllerSettings.from_environment()
        print(asyncio.run(runs_text(settings, limit=args.limit)))


if __name__ == "__main__":
    main()
