import json
import os
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
ATTACK_DATA_PATH = os.path.join(DATA_DIR, "attack.json")
ATTACK_DATA_URL = "https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json"

class MitreLoader:
    """
    Loads and parses the official MITRE ATT&CK STIX dataset.
    Provides clean technique objects for attack simulation, retrieval, and analysis.
    """

    def __init__(self, path: str = ATTACK_DATA_PATH):
        self.path = path
        self._techniques = None

    def _ensure_data_exists(self):
        """Downloads the MITRE dataset if it is missing."""
        if os.path.exists(self.path):
            return

        print("🌐 MITRE dataset not found locally. Downloading from official repository...")
        os.makedirs(DATA_DIR, exist_ok=True)

        try:
            self._download_with_progress(ATTACK_DATA_URL, self.path)
            print("Download complete!")
        except Exception as e:
            raise RuntimeError(f"Failed to download MITRE dataset: {e}")

    def _download_with_progress(self, url: str, destination_path: str):
        import urllib.request
        with urllib.request.urlopen(url, timeout=30) as response:
            total_size = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            bar_width  = 30
            chunk_size = 8192

            with open(destination_path, "wb") as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    if total_size > 0:
                        pct    = min(100, int(downloaded * 100 / total_size))
                        filled = int(bar_width * pct / 100)
                        bar    = "#" * filled + "-" * (bar_width - filled)
                        print(f"\r[MitreLoader] Downloading [{bar}] {pct:3d}%",
                            end="", flush=True)
        print()

    def load(self) -> list:
        """Load and parse all ATT&CK techniques. Cached in memory after first call."""
        if self._techniques is not None:
            return self._techniques

        self._ensure_data_exists()
        print("Parsing MITRE ATT&CK dataset...")

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                bundle = json.load(f)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"MITRE dataset at {self.path} is not valid JSON: {e}") from e

        techniques = []
        for obj in bundle.get("objects", []):
            # only process top-level techniques.
            if obj.get("type") != "attack-pattern":
                continue
            if obj.get("x_mitre_deprecated", False):
                continue
            if obj.get("x_mitre_is_subtechnique", False):
                continue

            tid = self._extract_technique_id(obj)
            name = obj.get("name", "")

            if not tid or not name:
                continue

            techniques.append({
                "technique_id": tid,
                "name": name,
                "description": obj.get("description", "").strip()[:1500],
                "tactics": self._extract_tactics(obj),
                "platforms": obj.get("x_mitre_platforms", []),
                "detection": self._extract_detection(obj),
                "url": f"https://attack.mitre.org/techniques/{tid}/",
            })

        self._techniques = sorted(techniques, key=lambda x: x["technique_id"])
        print(f"   [MitreLoader] Loaded {len(self._techniques)} techniques across {len(self.get_all_tactics())} tactics.")

        return self._techniques

    def get_by_id(self, technique_id: str) -> dict | None:
        techniques = self.load()
        return next((t for t in techniques if t["technique_id"] == technique_id), None)

    def get_by_tactic(self, tactic: str) -> list:
        """Return every technique associated with a specific ATT&CK tactic."""
        normalized_tactic = tactic.strip().lower()
        return [
            technique
            for technique in self.load()
            if normalized_tactic in {entry.lower() for entry in technique["tactics"]}
        ]

    def get_all_tactics(self) -> list:
        tactics = set()
        for t in self.load():
            tactics.update(t["tactics"])
        return sorted(tactics)

    def get_priority_techniques(self, limit: int = 20) -> list:
        """Returns the highest-priority techniques for ARIA's demo."""
        priority_ids = [
            "T1566", "T1078", "T1190", "T1059", "T1053", 
            "T1547", "T1055", "T1003", "T1110", "T1087", 
            "T1082", "T1021", "T1570", "T1005", "T1048", 
            "T1041", "T1486", "T1490", "T1071", "T1027"
        ]
        techniques = self.load()
        by_id = {t["technique_id"]: t for t in techniques}
        return [by_id[tid] for tid in priority_ids if tid in by_id][:limit]

    def _extract_technique_id(self, obj: dict) -> str | None:
        for ref in obj.get("external_references", []):
            if ref.get("source_name") == "mitre-attack":
                return ref.get("external_id")
        return None

    def _extract_tactics(self, obj: dict) -> list:
        return [
            phase["phase_name"]
            for phase in obj.get("kill_chain_phases", [])
            if phase.get("kill_chain_name") == "mitre-attack"
        ]

    def _extract_detection(self, obj: dict) -> str:
        detection = obj.get("x_mitre_detection", "") or ""
        return detection.strip()[:1000]