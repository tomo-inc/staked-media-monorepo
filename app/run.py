from __future__ import annotations

import argparse
from typing import Sequence

from pydantic import ValidationError
import uvicorn

from app.config import clear_config_cache, load_config_file, set_runtime_config_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Staked Media backend from a JSON config file.")
    parser.add_argument(
        "-c",
        "--config",
        required=True,
        help="Path to the JSON config file.",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable code reload on top of the JSON server config.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    clear_config_cache()
    try:
        loaded_config = load_config_file(args.config)
    except (FileNotFoundError, ValidationError, ValueError, RuntimeError) as exc:
        raise SystemExit(f"Failed to load config file {args.config}: {exc}") from exc

    set_runtime_config_path(loaded_config.config_path)
    uvicorn.run(
        app="app.main:create_app_from_runtime_config",
        factory=True,
        host=loaded_config.server.host,
        port=loaded_config.server.port,
        reload=bool(loaded_config.server.reload or args.reload),
    )


if __name__ == "__main__":
    main()
