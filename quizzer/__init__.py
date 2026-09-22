"""Flashcard Quizzer: a terminal flashcard trainer.

Modules:
    models:       Flashcard value object and answer normalisation.
    data_loader:  Load and validate flashcard decks from JSON.
    quiz_engine:  Quiz modes (Strategy), mode factory (Factory), engine.
    stats:        Per-answer results and session statistics.
    progress:     Cross-session per-card history used by adaptive mode.
    exporters:    Export session results to JSON or CSV (Strategy + Factory).
    ui:           Console rendering and input (colors, tables).
    session:      The interactive quiz loop.
    cli:          Argument parsing and application wiring.
"""

__version__ = "1.0.0"
