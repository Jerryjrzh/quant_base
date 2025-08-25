# Archived Code Analysis Report

**Creation Date**: 2025-08-25

This document analyzes the functionality, logic, and configuration of the Python scripts located in the `backend/_archive/` directory. It compares the legacy approaches found in these files with the current, refactored system architecture to provide context for future development and maintenance.

## 1. Overview of Archived Files

The archived files primarily consist of two categories:

1.  **Legacy Screener Scripts (`screener*.py`)**: These are standalone scripts, each designed to run one or more specific trading strategies across the entire stock market. They represent an earlier, more fragmented approach to stock screening.
2.  **Redundant/Temporary Scripts**: Files like `human_logic_strategies.py` (whose logic was refactored into strategy classes) and `test_strategy_independence.py` (a one-off test script) fall into this category.

This analysis will focus on the legacy screener scripts, as they contain the most relevant logic for comparison.

## 2. Legacy Screener Architecture (`screener*.py`)

### Core Logic & Design

-   **Standalone Execution**: Each `screener*.py` file was designed to be executed directly from the command line (e.g., `python backend/screener_abyss.py`).
-   **Strategy-per-File**: Most scripts were hardcoded to run a single, specific strategy. The target strategy was often determined by a global constant within the script (e.g., `STRATEGY_TO_RUN = 'TRIPLE_CROSS'`). This made it cumbersome to run different strategies without modifying the code.
-   **Monolithic Structure**: The scripts typically contained all logic in one file: data loading, strategy application, backtesting, filtering, and report generation. This violated the Single Responsibility Principle and made the code difficult to maintain and test.
-   **Manual Multiprocessing**: The scripts implemented their own multiprocessing logic using Python's `multiprocessing.Pool` to scan all stock files.
-   **Hardcoded Configuration**: Critical parameters, such as file paths (`BASE_PATH`), strategy parameters, and filter thresholds, were often hardcoded directly within the scripts.

### Key Functional Blocks in Legacy Scripts

| Feature                 | Legacy Implementation (`screener*.py`)                                                                                             |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| **Strategy Selection**  | Hardcoded global variable (e.g., `STRATEGY_TO_RUN`). To change strategies, the code had to be edited.                               |
| **Strategy Logic**      | Implemented as simple functions within a `strategies.py` file (e.g., `strategies.apply_pre_cross(df)`). No object-oriented structure. |
| **Configuration**       | Spread across global constants, function default arguments, and hardcoded values within the logic itself. No central config file.    |
| **Data Loading**        | Direct calls to a `data_loader` module.                                                                                            |
| **Execution Flow**      | A `main()` function orchestrates the entire process: globbing files, setting up a process pool, calling a `worker` function for each stock, collecting results, and generating a JSON/text report. |
| **Filtering**           | Implemented as separate `check_*_filter` functions that were manually called within the main `worker` function. Filters were tightly coupled to the script. |
| **Output & Reporting**  | Generated JSON files (`signals_summary.json`) and detailed text reports (`scan_report_*.txt`) directly into a results directory.      |

---

## 3. Current System Architecture (Post-Refactoring)

The current system has been refactored into a more robust, flexible, and maintainable architecture centered around three key components: `StrategyManager`, `UniversalScreener`, and a unified JSON configuration.

### Core Logic & Design

-   **Modular and Decoupled**: Logic is separated into distinct modules with clear responsibilities (e.g., `strategy_manager.py` for strategy loading, `universal_screener.py` for the screening process, `config_manager.py` for configuration).
-   **Configuration-Driven**: The entire system is driven by `config/unified_strategy_config.json`. Strategies, their parameters, and global settings are all managed from this central location. Strategies can be enabled/disabled without touching the code.
-   **Object-Oriented Strategies**: Each trading strategy is encapsulated in its own class, inheriting from a `BaseStrategy`. This standardizes the strategy interface, making them plug-and-play.
-   **Service-Oriented (API-first)**: The primary entry point is now the Flask API (`app.py`), which exposes endpoints for the frontend to interact with the system. The `UniversalScreener` is used as a service by the API.
-   **Centralized Management**: The `StrategyManager` class is responsible for discovering, loading, and providing instances of all available strategy classes. This removes the need for manual script modifications to run different strategies.

### Feature Comparison: Legacy vs. Current

| Feature                 | Legacy (`screener*.py`)                                                              | **Current System (`UniversalScreener`, `StrategyManager`)**                                                                                             | **Key Improvement**                                                                                                                                                           |
| ----------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Strategy Selection**  | Hardcoded in script.                                                                 | **Dynamically selected** via API calls or configuration. `UniversalScreener` accepts a list of strategy IDs to run.                                    | **Flexibility & Decoupling**: No code changes needed to run any combination of strategies. Enables frontend control.                                                        |
| **Strategy Logic**      | Procedural functions.                                                                | **Object-Oriented Classes** (`BaseStrategy` subclasses). Each strategy is a self-contained object with its own name, version, config, and logic.         | **Maintainability & Scalability**: Easy to add, remove, or test strategies in isolation. Standardized interface.                                                          |
| **Configuration**       | Hardcoded constants.                                                                 | **Centralized JSON file** (`unified_strategy_config.json`) managed by `ConfigManager`.                                                                 | **Centralized Control**: All parameters are in one place, easily editable, and can be updated without restarting the application.                                             |
| **Execution Flow**      | Manual multiprocessing in a standalone script.                                       | The `UniversalScreener` class encapsulates the multiprocessing logic. It is invoked as a service, typically by the API layer (`app.py`).               | **Reusability & Abstraction**: The screening process is now a reusable service, abstracting away the complexity of multiprocessing from the API.                             |
| **Filtering**           | Tightly coupled filter functions.                                                    | Filters can be integrated within the `BaseStrategy` class itself or applied within the `UniversalScreener`, allowing for more modular filtering logic. | **Modularity**: Filters are more closely associated with the strategies they apply to, or can be designed as generic, reusable components.                                    |
| **Output & Reporting**  | Direct file I/O to JSON/TXT.                                                         | Returns structured `StrategyResult` objects. The API layer is responsible for formatting this data as a JSON response for the frontend.                  | **Separation of Concerns**: The screener's job is to find signals, not to format reports. This makes the screener more focused and the output more versatile for different consumers (e.g., API, other scripts). |

## 4. Conclusion & Path Forward

The archived `screener*.py` scripts represent a "Version 1.0" architecture that was effective for running specific, hardcoded tasks but lacked the flexibility and scalability required for a complex, interactive system.

The current architecture is a significant improvement, offering:
-   **Modularity**: Clear separation of concerns.
-   **Flexibility**: Configuration-driven design allows for easy changes.
-   **Scalability**: The object-oriented strategy pattern makes adding new strategies trivial.
-   **Maintainability**: Code is easier to understand, test, and debug.

By analyzing the logic within the archived scripts, we can identify valuable filters, backtesting logic, or strategy variations that may not have been fully migrated to the new system. This report serves as a guide for ensuring that no valuable intellectual property from the legacy code is lost during the ongoing evolution of the platform.
