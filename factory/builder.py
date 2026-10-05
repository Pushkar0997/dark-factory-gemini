"""Backward-compatible entry point: `factory-builder` == `factory-seat --role implementer`."""

from factory.seat import main as _seat_main


def main() -> None:
    _seat_main(default_role="implementer")


if __name__ == "__main__":
    main()
