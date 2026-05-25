import splunklib.client as client
import splunklib.results as results
from config import SPLUNK_HOST, SPLUNK_PORT, SPLUNK_USERNAME, SPLUNK_PASSWORD, SPLUNK_SCHEME


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
                scheme=SPLUNK_SCHEME
            )
            print(f"connected to Splunk - version {self.service.info['version']}")
            return True
        except Exception as e:
            print(f"splunk connection failed: {e}")
            return False

    def get_all_saved_searches(self):
        """
        Blue Agent's primary data source for generating new rules is existing saved searches from Splunk.
        so this method retrieves all saved searches and their metadata for the Blue Agent to analyze and learn from.
        """
        if not self.service:
            raise Exception("not connected to Splunk. call connect() first.")

        searches = []
        for search in self.service.saved_searches:
            content = search.content
            searches.append({
                "name": search.name,
                "query": content.get("search", ""),
                "tags": content.get("tags", ""),
                "description": content.get("description", ""),
                "annotations": content.get("action.correlationsearch.annotations", ""),
                "mitre_technique": content.get("action.risk.param._risk_object", ""),
                "disabled": content.get("disabled", "0"),
            })
        return searches

    def validate_spl(self, spl_query):
        """validate SPL using the native Splunk SDK parser."""
        import splunklib.client as splunk_client

        def normalize(q):
            q = q.strip()
            generating_commands = (
                "search ", "tstats ", "inputlookup ",
                "makeresults", "rest ", "|"
            )
            if any(q.startswith(cmd) for cmd in generating_commands):
                return q
            return f"search {q}"

        normalized = normalize(spl_query)

        try:
            self.service.parse(normalized, parse_only=True)
            return {"valid": True, "error": None, "normalized": normalized}

        except splunk_client.HTTPError as e:
            # invalid queries return a 400 with error details in the body
            return {"valid": False, "error": str(e), "normalized": normalized}

        except Exception as e:
            # anthing else = genuine connection or config problem
            return {"valid": False, "error": f"Unexpected error: {str(e)}", "normalized": normalized}

    def create_saved_search(self, name, query, description="", tags=""):
        """
        stage an approved rule into Splunk as a saved search.
        called ONLY after human approval in the UI.
        """
        try:
            self.service.saved_searches.create(
                name,
                query,
                description=description,
                tags=tags,
                is_scheduled=False,  # human can enable scheduling post-review
            )
            print(f"rule staged: {name}")
            return True
        except Exception as e:
            print(f"failed to stage rule: {e}")
            return False

    def run_search(self, spl_query, max_results=100):
        """run a one-shot search and return results."""
        job = self.service.jobs.oneshot(spl_query, count=max_results)
        reader = results.JSONResultsReader(job)
        return [r for r in reader if isinstance(r, dict)]