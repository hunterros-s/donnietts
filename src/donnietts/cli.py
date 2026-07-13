import argparse

import uvicorn


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="donnietts")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="run the controller HTTP service")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    database = subparsers.add_parser("db", help="manage the controller database")
    database_subparsers = database.add_subparsers(dest="database_command", required=True)
    database_subparsers.add_parser("upgrade", help="apply all database migrations")
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
    elif args.command == "db" and args.database_command == "upgrade":
        from donnietts.migration_runner import upgrade_database
        from donnietts.settings import ControllerSettings

        settings = ControllerSettings.from_environment()
        upgrade_database(settings)
        print(f"Database upgraded: {settings.database_path}")


if __name__ == "__main__":
    main()
