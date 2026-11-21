"""Test setup: make the exec-ashlar and system-redstone scripts importable."""
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "exec-ashlar" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills" / "system-redstone" / "scripts"))
