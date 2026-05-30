import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv() 

from core.state import ARIAState, TechniqueState
from core.splunk_client import SplunkClient
from agents.gap_agent import GapAgent

def run_visual_test():
    print("\n" + "=" * 55)
    print("ARIA GAP AGENT TEST")
    print("=" * 55)


    state = ARIAState()
    
    technique = TechniqueState(
        technique_id="T1059.001",
        technique_name="PowerShell",
        tactics=["Execution"],
        verdict="GAP"
    )

    # mock red flags for this technique
    technique.attack_profile = {
        "technique_id": "T1059.001",
        "technique_name": "PowerShell",
        "tactics": ["Execution"],
        "severity": "high",
        "keywords": ["powershell", "encodedcommand", "hidden", "bypass", "nopm"],
        "log_hints": ["endpoint", "process", "sysmon"],
        "description": "Adversaries may abuse PowerShell commands and scripts for execution. PowerShell is a powerful interactive command-line interface and scripting environment included in the Windows operating system.",
        "detection_hint": "Monitor for powershell.exe launching with encoded, hidden, or bypass execution policy flags."
    }

    state.techniques[technique.technique_id] = technique
    
    print("Connecting to Splunk and Gemini...")
    splunk = SplunkClient()

    splunk.connect()

    gap_agent = GapAgent(splunk_client=splunk, model_name="gemini-2.5-flash")

    print("Generating SPL... (~2 seconds)\n")
    gap_agent.run(state, limit=1)

    print("\n" + "=" * 55)
    print("FINAL AI OUTPUT")
    print("=" * 55)
    
    if technique.generated_rule:
        print(f"Technique  : {technique.technique_id} — {technique.technique_name}")
        print(f"Confidence : {technique.rule_confidence * 100}%")
        print(f"Explanation: {technique.rule_explanation}\n")
        print("-" * 55)
        print("SPL QUERY:")
        print("-" * 55)
        print(f"{technique.generated_rule}")
        print("-" * 55)
    else:
        print("AI failed to generate a valid rule.")
        
    print("=" * 55)

if __name__ == "__main__":
    run_visual_test()