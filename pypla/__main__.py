"""Allow `sudo python3 -m pypla ...`."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
