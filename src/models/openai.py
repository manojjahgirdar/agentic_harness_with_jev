from langchain.chat_models import init_chat_model

import dotenv

from src.config import FAST_MODEL, REASONING_MODEL, SUMMARY_MODEL, TITLE_MODEL

dotenv.load_dotenv()

GPT5_5_FAST = init_chat_model(FAST_MODEL)
"""Low-latency model for straightforward support questions."""

GPT6_LUNA = init_chat_model(REASONING_MODEL)
"""Reasoning model for policy calls, disputes, and multi-step resolution."""

SUMMARIZER = init_chat_model(SUMMARY_MODEL)
"""Model used to compact long threads; deliberately the cheap one."""

TITLER = init_chat_model(TITLE_MODEL)
"""Names a thread by the customer's intent, for the dashboard. See `src/titles.py`."""
