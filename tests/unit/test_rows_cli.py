import json
import subprocess
import sys


def test_build_model_cli_orders_steps_and_preserves_input(tmp_path):
    data = {
        "project_name": "Demo",
        "TEST": [{"TS_TEST_ID": "1", "TS_NAME": "Login"}],
        "COMPONENT": [{"CO_ID": "10", "CO_NAME": "LoginComponent"}],
        "COMPONENT_STEP": [
            {
                "CS_STEP_ID": "2",
                "CS_COMPONENT_ID": "10",
                "CS_STEP_ORDER": "2",
                "CS_STEP_NAME": "Second",
            },
            {
                "CS_STEP_ID": "1",
                "CS_COMPONENT_ID": "10",
                "CS_STEP_ORDER": "1",
                "CS_STEP_NAME": "First",
            },
        ],
        "BPTEST_TO_COMPONENTS": [
            {
                "BC_ID": "1",
                "BC_BPT_ID": "1",
                "BC_CO_ID": "10",
                "BC_ORDER": "1",
            }
        ],
    }

    source = tmp_path / "rows.json"
    target = tmp_path / "model.json"
    source.write_text(json.dumps(data), encoding="utf-8")

    command = [
        sys.executable, "-m", "uft2uipath", "build-model",
        str(source), "--out", str(target),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

    model = json.loads(target.read_text(encoding="utf-8"))
    steps = model["project"]["tests"][0]["components"][0]["steps"]
    assert [step["name"] for step in steps] == ["First", "Second"]
    assert model["source_tables"]["COMPONENT_STEP"] == data["COMPONENT_STEP"]

    original = target.read_bytes()
    assert subprocess.run(command, capture_output=True).returncode != 0
    assert target.read_bytes() == original


def test_build_model_rejects_missing_tables(tmp_path):
    source = tmp_path / "rows.json"
    target = tmp_path / "model.json"
    source.write_text('{"project_name": "Demo"}', encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable, "-m", "uft2uipath", "build-model",
            str(source), "--out", str(target),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "TEST must be a list" in result.stderr
    assert not target.exists()
