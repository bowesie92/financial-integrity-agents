"""Run one GL Sentinel review. Same as: python scripts/run_review.py --agent gl ...
See scripts/run_review.py for the options."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_review import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["--agent", "gl", *sys.argv[1:]]))
