# Deal Watcher

Deal Watcher is an **educational prototype** for monitoring product prices on **Amazon.sa** and sending Telegram alerts when a configured condition is met. It combines a Playwright-based scraper, a persistent SQLite store, a background worker, a command-line interface, and Model Context Protocol (MCP) tools with explicit human approval before tracking begins.

> [!IMPORTANT]
> This project supports Amazon.sa only. It does not buy products, add items to a cart, request Amazon credentials, or bypass CAPTCHA and other site protections.

## Project Overview

Deal Watcher lets a user preview an Amazon.sa product, review its current price and alert settings, explicitly approve the tracking plan, and then monitor the product at a configurable interval. Price observations and tracking state are stored locally so monitoring can resume after a restart.

## Problem

Product prices can change frequently, and repeatedly checking product pages is inconvenient. Deal Watcher automates periodic checks while keeping the user in control of sensitive actions such as starting, pausing, or resuming monitoring.

## Key Features

- Amazon.sa URL validation and ASIN extraction.
- Product title and price extraction with Playwright and Chromium.
- Target-price alerts and optional alerts for any price decrease.
- Telegram notifications containing the old price, new price, decrease, reason, and product URL.
- SQLite persistence for products, price history, pending approvals, errors, and scheduling state.
- A long-running worker with retry scheduling and a Windows single-instance lock.
- Two-step, human-approved product registration.
- CLI commands for local operation.
- MCP tools for agent integrations.
- Windows Scheduled Task helpers for starting the worker at user logon.

## Architecture

<img width="611" height="645" alt="deal watcher agent workflow" src="https://github.com/user-attachments/assets/843baabe-987e-4321-be66-e0a0b207e90f" />


The main modules are deliberately separated by responsibility:

- `src/amazon_scraper.py`: marketplace validation, ASIN extraction, price parsing, Playwright navigation, and CAPTCHA detection.
- `src/database.py`: SQLite schema and persistence operations.
- `src/tracker_worker.py`: scheduling, checks, alert evaluation, retries, logging, and single-instance locking.
- `src/telegram_notify.py`: Telegram Bot API delivery.
- `src/cli.py`: local command-line interface.
- `src/mcp_server.py`: MCP tools for agent-driven workflows.
- `src/config.py`: relative project paths and environment-based settings.

## Workflow

1. A user supplies an Amazon.sa product URL and optional target price.
2. The application validates the marketplace and uses Playwright to extract the product title and current price.
3. A preview is returned with an approval token. The product is **not yet tracked**.
4. The user reviews the product, current price, target price, and any-drop setting.
5. Tracking starts only after explicit confirmation using the approval token.
6. The worker checks due products, evaluates alert conditions, records the result, and schedules the next check.
7. When an alert condition is satisfied, a message is sent through the Telegram Bot API.

If Amazon displays a CAPTCHA or verification page, Deal Watcher stops that extraction attempt, records the failure, and retries later. It does not attempt a bypass.

## Technology Stack

- Python 3.11+
- Playwright with Chromium
- SQLite with WAL journaling
- Model Context Protocol (`mcp` / FastMCP)
- Telegram Bot API
- PowerShell and Windows Task Scheduler helpers
- `pytest`-style tests

## Project Structure

```text
deal-watcher/
├── .env.example
├── .gitignore
├── README.md
├── README_AR.md
├── requirements.txt
├── requirements-dev.txt
├── setup.ps1
├── install-autostart.ps1
├── uninstall-autostart.ps1
├── run-worker.cmd
├── hermes/
│   └── skills/
│       └── amazon-price-tracker/
│           └── SKILL.md
├── src/
│   ├── __init__.py
│   ├── amazon_scraper.py
│   ├── cli.py
│   ├── config.py
│   ├── database.py
│   ├── mcp_server.py
│   ├── telegram_notify.py
│   └── tracker_worker.py
└── tests/
    └── test_price_parser.py
```

Runtime-only content such as `.env`, `.venv/`, `data/tracker.db`, SQLite sidecar files, logs, caches, credentials, and local Hermes profiles is excluded from Git.

## Installation

### Windows setup script

Requirements:

- Windows 10 or later
- Python 3.11 or later available as `python` or `py`
- PowerShell

From the project directory:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
```

The script creates `.venv`, installs Python dependencies, installs Playwright Chromium, initializes the SQLite database, and creates `.env` from `.env.example` when needed.

### Manual setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m src.cli init
```

## Telegram Configuration

1. Create a bot through Telegram's official **BotFather**.
2. Obtain the destination chat ID using a method appropriate for your own bot and chat.
3. Copy `.env.example` to `.env`.
4. Set the following values locally:

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
CHECK_INTERVAL_HOURS=6
```

Do not commit `.env`, paste credentials into documentation, or share the bot token. Deal Watcher does not need an Amazon username, password, payment details, or cookies.

Additional settings:

| Variable | Default | Purpose |
|---|---:|---|
| `CHECK_INTERVAL_HOURS` | `6` | Hours between successful checks |
| `WORKER_POLL_SECONDS` | `60` | Delay while waiting for due products |
| `FAILURE_RETRY_MINUTES` | `60` | Delay after a failed Amazon check |
| `PLAYWRIGHT_HEADLESS` | `true` | Run Chromium without a visible window |

## Usage

### Preview a product

A preview extracts product data and creates a short-lived approval token; it does not start tracking:

```powershell
.\.venv\Scripts\python.exe -m src.cli preview "https://www.amazon.sa/dp/PRODUCT_ASIN" --target 250
```

Use `--no-any-drop` if alerts should only be based on the target price.

### Confirm tracking

After reviewing the preview and explicitly approving it:

```powershell
.\.venv\Scripts\python.exe -m src.cli confirm APPROVAL_TOKEN
```

Approval tokens expire after 15 minutes and are single-use.

### Manage products

```powershell
.\.venv\Scripts\python.exe -m src.cli list
.\.venv\Scripts\python.exe -m src.cli pause PRODUCT_ID
.\.venv\Scripts\python.exe -m src.cli resume PRODUCT_ID
.\.venv\Scripts\python.exe -m src.cli check-now PRODUCT_ID
.\.venv\Scripts\python.exe -m src.cli delete PRODUCT_ID
```

Pause, resume, delete, and configuration changes should be performed only after clear user approval in an agent-driven workflow.

### Run the worker

```powershell
.\run-worker.cmd
```

Stop it with `Ctrl+C`.

### Start at Windows logon

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install-autostart.ps1
```

Remove the scheduled task with:

```powershell
.\uninstall-autostart.ps1
```

## MCP Tools

Run the MCP server with:

```powershell
.\.venv\Scripts\python.exe -m src.mcp_server
```

Available tools:

| Tool | Purpose |
|---|---|
| `preview_amazon_tracking` | Scrape an Amazon.sa URL and return a proposed tracking plan plus approval token |
| `confirm_amazon_tracking` | Persist the previously previewed product after explicit approval |
| `list_tracked_products` | List stored products and their current state |
| `pause_tracked_product` | Pause checks for a product after approval |
| `resume_tracked_product` | Resume checks for a product after approval |
| `check_product_now` | Mark a product as due for the worker's next cycle |

## Human-in-the-Loop

Starting monitoring is a two-step action:

1. `preview_amazon_tracking` performs a read-only product preview and creates a pending action.
2. `confirm_amazon_tracking` consumes the approval token and stores the product only after the user clearly approves the displayed plan.

Agent integrations should also require explicit approval before pausing, resuming, deleting, changing a target price, or changing the check interval. Previously approved periodic checks and alerts do not need approval on every cycle.

## Data Persistence

The application stores local state in `data/tracker.db` using SQLite. The database contains tracked products, price history, pending approval actions, last errors, and next-check timestamps. WAL mode may also create `tracker.db-wal` and `tracker.db-shm` while the database is active.

The database and its sidecar files are intentionally excluded from Git. Back up local runtime data separately if needed.

A powered-off computer cannot perform checks or send alerts. When the worker starts again, it loads persisted state and immediately processes products whose scheduled check time has passed. For continuous monitoring, run the worker on an always-on machine or a hosted environment.

## Testing

Install the development dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Run the tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Check all Python files for syntax errors:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests
```

The current tests cover English and Arabic price parsing and ASIN extraction. Broader scraper, database, worker, and notification tests are recommended before production use.

## Security

- Secrets are loaded from a local `.env` file that is excluded from Git.
- `.env.example` contains no credential values.
- SQLite data, logs, caches, OAuth artifacts, private keys, and local Hermes profiles are excluded from Git.
- Public project files use relative paths rather than user-specific absolute paths.
- Amazon credentials and payment information are neither requested nor required.
- CAPTCHA and verification pages are detected but never bypassed.
- The project never purchases products or adds items to a shopping cart.
- Review staged files and run a secret scanner before every public release.
- If a credential is ever committed, revoke or rotate it immediately; deleting it from the latest commit is not sufficient.

## Limitations

- This is an educational prototype, not a production service or an official Amazon integration.
- Only `amazon.sa` and `www.amazon.sa` are accepted.
- Extraction depends on Amazon's page structure and may break when the site changes.
- CAPTCHA, verification challenges, unavailable products, and network failures can delay checks.
- Local execution means no checks occur while the computer is powered off or the worker is stopped.
- Telegram delivery depends on valid local credentials and network availability.
- The test suite is currently small.
- No purchase or cart functionality is provided.

## Future Improvements

- Add unit tests for scheduling, database transitions, and alert de-duplication.
- Add mocked integration tests for Telegram and Playwright extraction paths.
- Add structured migrations for future database schema changes.
- Add configurable per-product intervals and richer notification policies.
- Add observability, health checks, and safer log rotation.
- Add container and hosted deployment options for continuous operation.
- Add CI checks for tests, syntax, formatting, and secret scanning.
- Add support for additional marketplaces only after marketplace-specific validation and testing.
