from __future__ import annotations

import sys

from . import __version__


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] in {"--version", "-V"}:
        print(f"tink-agent {__version__}")
        return

    from .menubar import main as menubar_main
    menubar_main()

if __name__ == "__main__":
    main()
