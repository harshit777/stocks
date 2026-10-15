#!/usr/bin/env python3
"""
Paper-trading report CLI.

  paper_report.py status    Print days completed; write done=true|false to
                            $GITHUB_OUTPUT (true once PAPER_MAX_DAYS reached).
  paper_report.py summary   Rebuild data/paper/SUMMARY.md and print it.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.paper_report import completed_days, update_summary  # noqa: E402


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
    max_days = int(os.getenv('PAPER_MAX_DAYS', '10'))

    if cmd == 'status':
        done = completed_days()
        finished = done >= max_days
        print(f"Paper trading: {done} of {max_days} days completed"
              f"{' — period finished, skipping session' if finished else ''}")
        out = os.getenv('GITHUB_OUTPUT')
        if out:
            with open(out, 'a') as f:
                f.write(f"done={'true' if finished else 'false'}\n")
                f.write(f"days_done={done}\n")
        return 0

    if cmd == 'summary':
        print(update_summary(max_days=max_days))
        return 0

    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main())
