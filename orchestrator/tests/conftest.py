"""Shared test fixtures for orchestrator tests."""
import os

# Prevent real API calls at import time
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-fake-key")
os.environ.setdefault("WEB_RESEARCH_AGENT_URL", "http://localhost:8001")
os.environ.setdefault("RAG_AGENT_URL", "http://localhost:8002")
os.environ.setdefault("SUMMARISER_AGENT_URL", "http://localhost:8003")
