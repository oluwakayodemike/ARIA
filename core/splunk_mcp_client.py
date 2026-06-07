import json
from typing import Any

import httpx

from config import (
    SPLUNK_MCP_TIMEOUT_SEC,
    SPLUNK_MCP_TOKEN,
    SPLUNK_MCP_URL,
    SPLUNK_MCP_VERIFY_SSL,
)


class SplunkMCPClient:
    """
    Lightweight JSON-RPC client for Splunk MCP Server over HTTP.
    Uses encrypted MCP bearer token authentication.
    """

    def __init__(
        self,
        base_url: str = SPLUNK_MCP_URL,
        token: str = SPLUNK_MCP_TOKEN,
        verify_ssl: bool = SPLUNK_MCP_VERIFY_SSL,
        timeout_sec: int = SPLUNK_MCP_TIMEOUT_SEC,
    ):
        self.base_url = (base_url or "").strip()
        self.token = (token or "").strip()
        self.verify_ssl = bool(verify_ssl)
        self.timeout_sec = timeout_sec

        self._request_id = 1
        self._initialized = False
        self._tools_cache: list[dict[str, Any]] | None = None

    def is_configured(self) -> bool:
        return bool(self.base_url and self.token)

    def initialize(self) -> bool:
        if not self.is_configured():
            return False
        self._rpc("initialize", {"client": "aria", "version": "1.0"})
        self._initialized = True
        return True

    def list_tools(self, force: bool = False) -> list[dict[str, Any]]:
        if self._tools_cache is not None and not force:
            return self._tools_cache

        self._ensure_initialized()

        try:
            result = self._rpc("tools/list", {})
        except RuntimeError:
            result = self._rpc("tools/list", None)

        tools = result.get("tools") if isinstance(result, dict) else None
        if not isinstance(tools, list):
            tools = []

        parsed: list[dict[str, Any]] = []
        for tool in tools:
            if isinstance(tool, dict):
                parsed.append(tool)

        self._tools_cache = parsed
        return parsed

    def find_tool(self, *preferred_names: str) -> str | None:
        tools = self.list_tools()
        available = {
            str(t.get("name", "")).strip(): t
            for t in tools
            if isinstance(t, dict) and str(t.get("name", "")).strip()
        }

        for name in preferred_names:
            normalized = (name or "").strip()
            if normalized and normalized in available:
                return normalized

        # fallback: allow suffix match when namespaced or legacy names differ.
        lower_map = {k.lower(): k for k in available.keys()}
        for name in preferred_names:
            n = (name or "").strip().lower()
            if not n:
                continue

            if n in lower_map:
                return lower_map[n]

            for candidate in available.keys():
                c = candidate.lower()
                if c.endswith(n):
                    return candidate
                if n.startswith("saia_") and c.endswith(n.replace("saia_", "")):
                    return candidate
                if n.startswith("splunk_") and c.endswith(n.replace("splunk_", "")):
                    return candidate

        return None

    def call_tool(
        self, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> dict:
        if not tool_name:
            raise ValueError("tool_name is required")

        self._ensure_initialized()
        result = self._rpc(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments or {},
            },
        )

        if not isinstance(result, dict):
            return {"raw": result}

        if bool(result.get("isError")):
            raise RuntimeError(
                f"MCP tool '{tool_name}' returned isError=true: {self.extract_text(result)}"
            )

        error = result.get("error")
        if isinstance(error, str) and error.strip():
            raise RuntimeError(f"MCP tool '{tool_name}' error: {error.strip()}")
        if isinstance(error, dict):
            raise RuntimeError(f"MCP tool '{tool_name}' error: {json.dumps(error)}")

        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            sc_error = structured.get("error")
            if isinstance(sc_error, str) and sc_error.strip():
                raise RuntimeError(f"MCP tool '{tool_name}' error: {sc_error.strip()}")
            if isinstance(sc_error, dict):
                raise RuntimeError(
                    f"MCP tool '{tool_name}' error: {json.dumps(sc_error)}"
                )

        return result

    def extract_text(self, tool_result: dict[str, Any]) -> str:
        if not isinstance(tool_result, dict):
            return str(tool_result)

        content = tool_result.get("content")
        texts: list[str] = []

        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text" and item.get("text"):
                    texts.append(str(item.get("text")))

        if texts:
            return "\n".join(texts).strip()

        structured = tool_result.get("structuredContent")
        if isinstance(structured, str):
            return structured.strip()
        if isinstance(structured, dict):
            for key in (
                "spl",
                "query",
                "search",
                "optimized_spl",
                "explanation",
                "answer",
                "text",
            ):
                value = structured.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            return json.dumps(structured)

        if "result" in tool_result and isinstance(tool_result["result"], str):
            return tool_result["result"].strip()

        return json.dumps(tool_result)

    def healthcheck(self) -> tuple[bool, str]:
        if not self.is_configured():
            return False, "Splunk MCP is not configured. Missing URL or token."
        try:
            self.initialize()
            tools = self.list_tools(force=True)
            return True, f"Connected. {len(tools)} tools available."
        except Exception as e:
            return False, str(e)

    def _ensure_initialized(self):
        if self._initialized:
            return
        if not self.initialize():
            raise RuntimeError("Splunk MCP is not configured. Missing URL or token.")

    def _rpc(self, method: str, params: dict | None) -> dict:
        if not self.is_configured():
            raise RuntimeError("Splunk MCP is not configured. Missing URL or token.")

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
        }
        self._request_id += 1

        if params is not None:
            payload["params"] = params

        try:
            with httpx.Client(
                verify=self.verify_ssl,
                timeout=self.timeout_sec,
            ) as client:
                response = client.post(self.base_url, headers=headers, json=payload)
        except Exception as e:
            raise RuntimeError(f"MCP request failed for '{method}': {e}") from e

        if response.status_code >= 400:
            text = response.text[:400]
            raise RuntimeError(
                f"MCP HTTP {response.status_code} for '{method}': {text}"
            )

        try:
            data = response.json()
        except Exception as e:
            raise RuntimeError(f"MCP returned non-JSON for '{method}': {e}") from e

        if not isinstance(data, dict):
            raise RuntimeError(f"MCP response for '{method}' is not an object: {data}")

        if "error" in data and data["error"] is not None:
            err = data["error"]
            if isinstance(err, dict):
                message = err.get("message") or str(err)
            else:
                message = str(err)
            raise RuntimeError(f"MCP error for '{method}': {message}")

        return data.get("result", {})
