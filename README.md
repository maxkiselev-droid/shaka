# Headless World-Model growth (no UI)

## What you get
- `wm_runner.py` — runs without a browser; grows `wm_state.json` over time.
- `seeds.txt` — editable seed prompts list.

## How to run
From your `backend/` folder (same place as `world_model.py` and your `.env`):

```bash
source venv/bin/activate
python wm_runner.py --steps 30 --self-prompts --seed-file seeds.txt
```

Outputs:
- `wm_state.json` — latest world model snapshot
- `wm_log.jsonl` — append-only run log

## Notes
- Uses `OPENAI_API_KEY` from environment or `.env` in the current directory.
- Does not touch `app.py` or the web UI.
