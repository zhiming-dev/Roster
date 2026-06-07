"""Backward-compatible entrypoint for legacy Conclave module references.

This module lets existing integrations keep using `python -m roster_compat`-style
imports internally while the public runtime package name is `roster`.
"""

from roster.__main__ import main


if __name__ == "__main__":
    main()