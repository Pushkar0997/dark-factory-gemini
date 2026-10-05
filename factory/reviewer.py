"""Backward-compatible entry point: `factory-reviewer` == `factory-seat --role reviewer`."""

from factory.seat import main as _seat_main


def main() -> None:
    _seat_main(default_role="reviewer")


if __name__ == "__main__":
    main()
