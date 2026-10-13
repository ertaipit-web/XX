"""Shared pytest configuration.

LLM is disabled by default in tests to keep them fast and hermetic. Tests that
need to exercise LLM behavior inject a MockLLMClient explicitly.
"""

import os

# Must be set before importing anything that builds an LLM client.
os.environ.setdefault("VACANCIES_DISABLE_LLM", "1")
