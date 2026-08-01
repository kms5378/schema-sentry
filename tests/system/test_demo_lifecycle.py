import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_demo_script_runs_complete_schema_drift_lifecycle() -> None:
    result = subprocess.run(
        ["bash", "scripts/demo.sh"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "baseline scan: completed" in result.stdout
    assert "breaking drift: detected" in result.stdout
    assert "affected DAG: daily_revenue" in result.stdout
    assert "pipeline validation: blocked" in result.stdout
    assert "email notification: sent" in result.stdout
    assert "restoration scan: resolved" in result.stdout
    assert "pipeline validation: safe" in result.stdout
