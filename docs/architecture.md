# Architecture

## Module dependencies

Arrows point from a module to what it depends on. Nothing below `cli` imports the
UI, so the engine, loader, stats and progress modules are all testable without a
terminal.

```mermaid
flowchart TD
    main[main.py] --> cli[quizzer/cli.py]
    cli --> loader[data_loader.py]
    cli --> engine[quiz_engine.py]
    cli --> session[session.py]
    cli --> progress[progress.py]
    cli --> exporters[exporters.py]
    cli --> ui[ui.py]
    session --> engine
    session --> ui
    loader --> models[models.py]
    loader --> fh[utils/file_handler.py]
    engine --> models
    engine --> stats[stats.py]
    progress --> fh
    progress --> stats
    exporters --> stats
    ui --> stats
    ui --> progress
```

## Strategy and Factory: quiz modes

```mermaid
classDiagram
    class QuizMode {
        <<abstract>>
        +name: str
        +description: str
        +next_card() Flashcard | None*
        +remaining: int*
        +record_result(card, correct) None
    }
    class SequentialMode
    class RandomMode
    class AdaptiveMode {
        -_queue: deque
        -_attempts: dict
        +record_result(card, correct) None
    }
    class ModeConfig {
        +seed: int | None
        +history: Mapping[str, int]
        +max_attempts: int
        +requeue_gap: int
    }
    class QuizModeFactory {
        -_registry: dict
        +register(mode_class)$
        +create(name, cards, config)$ QuizMode
        +available_modes()$ list
    }
    class QuizEngine {
        +stats: SessionStats
        +next_card() Flashcard | None
        +answer(response) AnswerResult
    }
    QuizMode <|-- SequentialMode
    QuizMode <|-- RandomMode
    QuizMode <|-- AdaptiveMode
    QuizMode --> ModeConfig
    QuizModeFactory ..> QuizMode : creates
    QuizEngine o-- QuizMode : strategy
```

`QuizEngine` (the Strategy context) only calls `next_card`, `remaining` and
`record_result`. It never checks which mode it has. The CLI never instantiates a mode
directly: it passes the `--mode` string to `QuizModeFactory.create`, and argparse's
`choices` come from `QuizModeFactory.available_modes()`, so registering a new mode
also makes it appear in `--help` automatically.

## Adaptive mode algorithm

```mermaid
flowchart TD
    start([Session starts]) --> hist[Load per-card miss counts from progress file]
    hist --> order[Shuffle deck with seed, then stable-sort by past misses, descending]
    order --> q[(Queue)]
    q --> ask{Queue empty?}
    ask -- yes --> done([Session complete])
    ask -- no --> pop[Pop next card and ask it]
    pop --> check{Correct?}
    check -- yes --> ask
    check -- no --> cap{Asked max_attempts times?}
    cap -- yes --> ask
    cap -- no --> requeue["Re-insert at position n x requeue_gap<br/>(n = times missed so far)"]
    requeue --> ask
    done --> save[Fold results into progress file for next time]
```

The growing gap (`n x requeue_gap`) was introduced after manual testing showed that a
fixed gap let three missed cards cycle between each other and starve the rest of the
deck. See entry 2 in `ai_edit_log.md`.

## Session flow and error handling

```mermaid
sequenceDiagram
    actor User
    participant CLI as cli.main
    participant Loader as data_loader
    participant Store as ProgressStore
    participant Engine as QuizEngine
    participant UI as ConsoleUI
    User->>CLI: python main.py -m adaptive -f deck.json
    CLI->>Loader: load_flashcards(path)
    alt missing / malformed / invalid deck
        Loader-->>CLI: FlashcardLoadError(friendly message)
        CLI->>UI: error(message)
        CLI-->>User: exit code 1, no traceback
    end
    CLI->>Store: load() (corrupt file only warns)
    CLI->>Engine: QuizModeFactory.create(mode, cards, config)
    loop until done, "exit", Ctrl+C or EOF
        Engine-->>UI: next card
        UI->>User: front of card
        User->>UI: answer
        UI->>Engine: answer(text)
        Engine-->>UI: AnswerResult (green / red feedback)
    end
    CLI->>UI: show_summary(stats)
    CLI->>Store: update + atomic save
```

Every expected failure is converted to a domain exception carrying a user-facing
message (`FileReadError`, `FlashcardLoadError`, `ExportError`). As a last resort,
`cli.main` catches anything unexpected and prints a one-line message instead of a
traceback, unless `--debug` is passed.
