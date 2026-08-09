from __future__ import annotations

import subprocess
import sys


def test_snapshot_result_events_and_outbox_main_import_in_fresh_process() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import data_pipeline.meeting_analysis.snapshot; "
                "import data_pipeline.meeting_analysis.result_events; "
                "import data_pipeline.outbox_publisher.__main__"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
