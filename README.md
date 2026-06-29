# Titan

Personal agentic AI system — modular monolith with Brain, Agents, Memory, Tools, State, and Missions.

## Prerequisites

- **Python 3.10+** (3.14 tested on Windows)
- An [OpenAI API key](https://platform.openai.com/api-keys)

## Setup

From the project root in PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Configure `.env`

Copy the example file and add your API key:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set `OPENAI_API_KEY`. Optional variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `TITAN_LOG_LEVEL` | `INFO` | Logging verbosity |
| `TITAN_DEBUG_BRAIN` | `false` | Verbose Brain pipeline logging |

See `.env.example` for the full template. Never commit `.env`.

## Run

From the project root (with the virtual environment activated):

```powershell
python main.py
```

Exit the session with `exit`, `quit`, `stop`, or `bye`.

Logs are written to `logs/titan.log`.

## Run tests

From the project root:

```powershell
python -m pytest tests/ -v
```

## PYTHONPATH

Titan imports assume the **project root** is on `PYTHONPATH`. Running `python main.py` or `python -m pytest tests/ -v` from the repo root satisfies this. If you import modules from another working directory, set:

```powershell
$env:PYTHONPATH = "C:\path\to\Titan"
```

Replace the path with your local clone location.
