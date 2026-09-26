"""Run the trace API: `uv run api.py` (http://127.0.0.1:8000)."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("src.api:app", host="127.0.0.1", port=8000, reload=False)
