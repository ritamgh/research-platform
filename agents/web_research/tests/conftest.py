"""Test configuration for web_research agent tests."""
import os
import pytest

# Provide fake credentials so CrewAI/OpenAI don't raise at import/init time
os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake-key")
os.environ.setdefault("TAVILY_API_KEY", "tvly-test-fake-key")
os.environ.setdefault("WEB_SEARCH_MCP_URL", "http://localhost:9001")
