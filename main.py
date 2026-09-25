#!/usr/bin/env python3
"""Factory26 compliant model-driven ARC-Bench agent entry point."""

import os

from factory26_harness.qualifier import main


if __name__ == "__main__":
    # The submitted entry opts in; explicit runner settings retain precedence.
    # Library use stays opt-in. This permits verification only, never extra edits.
    os.environ.setdefault("FACTORY26_COMPLETION_TAIL", "1")
    raise SystemExit(main())
