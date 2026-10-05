"""Backward-compatible entry point: `factory-planner` == `factory-seat --role coordinator`."""

from factory.seat import main as _seat_main


def main() -> None:
    _seat_main(default_role="coordinator")


if __name__ == "__main__":
    main()
