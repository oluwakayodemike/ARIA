import os

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


SPLUNK_HOST = os.getenv("SPLUNK_HOST", "localhost")
SPLUNK_PORT = int(os.getenv("SPLUNK_PORT", 8089))
SPLUNK_USERNAME = os.getenv("SPLUNK_USERNAME", "admin")
SPLUNK_PASSWORD = os.getenv("SPLUNK_PASSWORD", "")
SPLUNK_SCHEME = "https"

# MCP + Splunk AI Assistant configuration
SPLUNK_MCP_URL = os.getenv("SPLUNK_MCP_URL", "https://localhost:8089/services/mcp")
SPLUNK_MCP_TOKEN = os.getenv("SPLUNK_MCP_TOKEN", "")
SPLUNK_MCP_VERIFY_SSL = _env_bool("SPLUNK_MCP_VERIFY_SSL", True)
SPLUNK_MCP_TIMEOUT_SEC = _env_int("SPLUNK_MCP_TIMEOUT_SEC", 30)
SPLUNK_AI_PRIMARY = _env_bool("SPLUNK_AI_PRIMARY", True)

# Tool names are configurable to survive deployment-specific tool naming.
SPLUNK_MCP_TOOL_GENERATE = os.getenv("SPLUNK_MCP_TOOL_GENERATE", "saia_generate_spl")
SPLUNK_MCP_TOOL_OPTIMIZE = os.getenv("SPLUNK_MCP_TOOL_OPTIMIZE", "saia_optimize_spl")
SPLUNK_MCP_TOOL_EXPLAIN = os.getenv("SPLUNK_MCP_TOOL_EXPLAIN", "saia_explain_spl")

# Demo mode
ARIA_DEMO_MODE = _env_bool("ARIA_DEMO_MODE", False)
ARIA_DEMO_FIXTURE_PATH = os.getenv("ARIA_DEMO_FIXTURE_PATH", "scripts/demo_state.json")
ARIA_DEMO_SIMULATE_RUN_SEC = _env_int("ARIA_DEMO_SIMULATE_RUN_SEC", 12)
