#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys
from pathlib import Path


def main() -> None:
    # Ensure src/ is on the path so analyzer_web and analyzer_ui are importable
    src_dir = str(Path(__file__).resolve().parent / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "analyzer_web.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and available on "
            "your PYTHONPATH? Did you forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
