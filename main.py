"""Entry point for the Flashcard Quizzer CLI.

Usage:
    python main.py --help
    python main.py --mode sequential --file data/glossary.json
    python main.py -m adaptive -f data/python_basics.json
"""

import sys

from quizzer.cli import main

if __name__ == "__main__":
    sys.exit(main())
