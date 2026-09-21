"""Package entrypoint for python -m companion."""

import sys
from companion.cli import main

if __name__ == "__main__":
    sys.exit(main())
