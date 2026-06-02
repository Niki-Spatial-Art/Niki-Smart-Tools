#!/usr/bin/env python3
"""CLI wrapper for the public web scraper connector."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from connectors.public_web_scraper import main


if __name__ == "__main__":
    main()
