"""Demo runner: three fictional incidents end to end.

Run it with:

    python run_demo.py

It submits a checkout-latency incident (approved), a payments 5xx
incident (rejected — nothing executes), and a documentation question
(answered with citations). Then it prints the audit trail and verifies
the hash chain. All data is fictional; nothing here touches a real
system.
"""

import sys

from ai_ops_copilot.cli import _cmd_demo


class _Args:
    mcp_mode = "direct"


if __name__ == "__main__":
    sys.exit(_cmd_demo(_Args()))
