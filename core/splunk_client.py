import splunklib.client as client

from config import (
    SPLUNK_HOST,
    SPLUNK_PASSWORD,
    SPLUNK_PORT,
    SPLUNK_SCHEME,
    SPLUNK_USERNAME,
)


class SplunkClient:
    def __init__(self):
        self.service = None

    def connect(self):
        """establish connection to Splunk."""
        try:
            self.service = client.connect(
                host=SPLUNK_HOST,
                port=SPLUNK_PORT,
                username=SPLUNK_USERNAME,
                password=SPLUNK_PASSWORD,
                scheme=SPLUNK_SCHEME,
            )
            print(f"connected to Splunk - version {self.service.info['version']}")
            return True
        except Exception as e:
            print(f"splunk connection failed: {e}")
            self.service = None
            return False

    def ensure_connected(self) -> bool:
        """Ensure we have a live Splunk session, reconnecting if needed."""
        if self.service:
            return True
        return self.connect()

    @staticmethod
    def _is_session_error(error: Exception | str | None) -> bool:
        if not error:
            return False
        text = str(error).lower()
        indicators = [
            "session is not logged in",
            "not logged in",
            "unauthorized",
            "authentication",
            "forbidden",
        ]
        return any(token in text for token in indicators)

    def is_session_error_message(self, message: str | None) -> bool:
        """Public helper for callers (e.g., agents) to classify auth/session errors."""
        return self._is_session_error(message)

    def get_all_saved_searches(self):
        """
        Blue Agent's primary data source for generating new rules is existing saved searches from Splunk.
        so this method retrieves all saved searches and their metadata for the Blue Agent to analyze and learn from.
        """
        if not self.ensure_connected():
            raise Exception("not connected to Splunk. call connect() first.")

        searches = []
        try:
            for search in self.service.saved_searches:
                content = search.content
                searches.append(
                    {
                        "name": search.name,
                        "query": content.get("search", ""),
                        "tags": content.get("tags", ""),
                        "description": content.get("description", ""),
                        "annotations": content.get(
                            "action.correlationsearch.annotations", ""
                        ),
                        "mitre_technique": content.get(
                            "action.risk.param._risk_object", ""
                        ),
                        "disabled": content.get("disabled", "0"),
                    }
                )
            return searches
        except Exception as e:
            if self._is_session_error(e) and self.connect():
                searches = []
                for search in self.service.saved_searches:
                    content = search.content
                    searches.append(
                        {
                            "name": search.name,
                            "query": content.get("search", ""),
                            "tags": content.get("tags", ""),
                            "description": content.get("description", ""),
                            "annotations": content.get(
                                "action.correlationsearch.annotations", ""
                            ),
                            "mitre_technique": content.get(
                                "action.risk.param._risk_object", ""
                            ),
                            "disabled": content.get("disabled", "0"),
                        }
                    )
                return searches
            raise

    def validate_spl(self, spl_query):
        """validate SPL using the native Splunk SDK parser."""
        import splunklib.client as splunk_client

        def normalize(q):
            q = q.strip()
            generating_commands = (
                "search ",
                "tstats ",
                "inputlookup ",
                "makeresults",
                "rest ",
                "|",
            )
            if any(q.startswith(cmd) for cmd in generating_commands):
                return q
            return f"search {q}"

        normalized = normalize(spl_query)

        if not self.ensure_connected():
            return {
                "valid": False,
                "error": "Not connected to Splunk. call connect() first.",
                "normalized": normalized,
            }

        try:
            self.service.parse(normalized, parse_only=True)
            return {"valid": True, "error": None, "normalized": normalized}

        except splunk_client.HTTPError as e:
            # invalid queries return a 400 with error details in the body
            if self._is_session_error(e) and self.connect():
                try:
                    self.service.parse(normalized, parse_only=True)
                    return {"valid": True, "error": None, "normalized": normalized}
                except splunk_client.HTTPError as retry_err:
                    return {
                        "valid": False,
                        "error": str(retry_err),
                        "normalized": normalized,
                    }
                except Exception as retry_err:
                    return {
                        "valid": False,
                        "error": f"Unexpected error: {str(retry_err)}",
                        "normalized": normalized,
                    }
            return {"valid": False, "error": str(e), "normalized": normalized}

        except Exception as e:
            # anything else = genuine connection or config problem
            if self._is_session_error(e) and self.connect():
                try:
                    self.service.parse(normalized, parse_only=True)
                    return {"valid": True, "error": None, "normalized": normalized}
                except splunk_client.HTTPError as retry_err:
                    return {
                        "valid": False,
                        "error": str(retry_err),
                        "normalized": normalized,
                    }
                except Exception as retry_err:
                    return {
                        "valid": False,
                        "error": f"Unexpected error: {str(retry_err)}",
                        "normalized": normalized,
                    }

            return {
                "valid": False,
                "error": f"Unexpected error: {str(e)}",
                "normalized": normalized,
            }

    def create_saved_search(self, name, query, description=""):
        """
        stage an approved rule into Splunk as a saved search.
        called ONLY after human approval in the UI.
        """
        if not self.ensure_connected():
            print("failed to stage rule: not connected to Splunk")
            return False

        def _create_once() -> bool:
            kwargs: dict[str, object] = {
                "is_scheduled": False,  # human can enable scheduling post-review
            }
            if description:
                kwargs["description"] = description

            self.service.saved_searches.create(
                name,
                query,
                **kwargs,
            )
            print(f"rule staged: {name}")
            return True

        try:
            return _create_once()
        except Exception as e:
            if self._is_session_error(e) and self.connect():
                try:
                    return _create_once()
                except Exception as retry_err:
                    print(f"failed to stage rule: {retry_err}")
                    return False

            print(f"failed to stage rule: {e}")
            return False

    def run_search(self, spl_query, max_results=100):
        """run a one-shot search and return results."""
        import json

        if not self.ensure_connected():
            print("[-] run_search failed: not connected to Splunk")
            return []

        def _run_once():
            response = self.service.jobs.oneshot(
                spl_query, count=max_results, output_mode="json"
            )
            data = json.loads(response.read().decode("utf-8"))
            return data.get("results", [])

        # we must explicitly request JSON, otherwise Splunk defaults to XML [and the SDK doesn't parse it right]
        try:
            return _run_once()
        except Exception as e:
            if self._is_session_error(e) and self.connect():
                try:
                    return _run_once()
                except Exception as retry_err:
                    print(f"[-] run_search failed: {retry_err}")
                    return []

            print(f"[-] run_search failed: {e}")
            return []
