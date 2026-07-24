import importlib.util
import json
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.skin_catalog import resolve_skins


def load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_lodge_plans(lodge):
    cases = {
        "smpl_only": (["smpl"], False, True),
        "robot_only": (["robot"], True, False),
        "multi": (["smpl", "robot"], True, True),
    }
    results = {}
    for name, (skin_ids, expected_retarget, expected_smpl) in cases.items():
        req = lodge.InferFromAudioRequest(
            lodge_root=".",
            audio_path="input.wav",
            song_id=name,
            skin_ids=skin_ids,
        )
        options = lodge._retarget_options_from_req(req)
        assert options["enabled"] is expected_retarget
        assert options["render_smpl"] is expected_smpl
        results[name] = {
            "retarget": options["enabled"],
            "smpl": options["render_smpl"],
        }
    return results


def test_intergen_outputs(intergen):
    def fake_generate(_prompt, output_path, **_kwargs):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"temporary-smpl-preview")
        candidate_dir = output_path.parent / "candidates"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        (candidate_dir / "candidate.mp4").write_bytes(b"candidate")
        return {
            "message": "Mock motion completed",
            "generated_frames": 180,
            "fps": 30,
            "raw_joints_files": [],
        }

    def fake_retarget(task_id, task_root, output_path, raw_joints_files, req, motion_prompt=""):
        del output_path, raw_joints_files, motion_prompt
        profiles = intergen._resolve_request_skins(req)
        retarget_profile = next(
            (profile for profile in profiles if intergen.skin_requires_retarget(profile)),
            None,
        )
        if retarget_profile is None:
            intergen._update_task(
                task_id,
                retarget_status="skipped",
                retarget_message="Retarget disabled",
            )
            return
        output = task_root / "retarget" / f"{task_id}_retarget.mp4"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"robot-video")
        intergen._update_task(
            task_id,
            output_retarget_path=str(output.resolve()),
            retarget_status="succeeded",
            retarget_message="Mock retarget completed",
        )

    intergen.service.generate = fake_generate
    intergen._run_intergen_retarget_if_requested = fake_retarget

    results = {}
    cases = {
        "smpl_only": ["smpl"],
        "robot_only": ["robot"],
        "multi": ["smpl", "robot"],
    }
    for name, skin_ids in cases.items():
        task_id = name
        now = "2026-07-24T00:00:00Z"
        intergen._tasks[task_id] = intergen.TaskInfo(
            task_id=task_id,
            status="queued",
            created_at=now,
            updated_at=now,
            skin_id=skin_ids[0],
            requested_skin_ids=skin_ids,
        )
        req = intergen.GenerateMotionRequest(
            text="Two people dance.",
            skin_ids=skin_ids,
        )
        intergen._run_generate_task(task_id, req)
        task = intergen._tasks[task_id]
        assert task.status == "succeeded"
        assert task.available_skin_ids == skin_ids
        if "smpl" in skin_ids:
            assert task.output_mp4_path and Path(task.output_mp4_path).is_file()
        else:
            assert task.output_mp4_path is None
            assert not list((intergen.DEFAULT_TASK_ROOT / task_id / "output" / "candidates").glob("*.mp4"))
        if "robot" in skin_ids:
            assert task.output_retarget_path and Path(task.output_retarget_path).is_file()
        else:
            assert task.output_retarget_path is None
        results[name] = {
            "available_skin_ids": task.available_skin_ids,
            "smpl_video": bool(task.output_mp4_path),
            "robot_video": bool(task.output_retarget_path),
        }
    return results


def main():
    lodge = load_module("lodge_api_skin_test", "LODGE_api/lodge_async_api.py")
    intergen = load_module("intergen_api_skin_test", "InterGen_api/intergen_async_api.py")
    with tempfile.TemporaryDirectory(prefix="human_action_skin_test_") as temp_dir:
        intergen.DEFAULT_TASK_ROOT = Path(temp_dir)
        results = {
            "contract_resolution": {
                "explicit_smpl_overrides_legacy_flag": [
                    profile["id"]
                    for profile in resolve_skins(
                        REPO_ROOT,
                        ["smpl"],
                        legacy_retarget_enabled=True,
                    )
                ],
                "legacy_retarget_requests_both": [
                    profile["id"]
                    for profile in resolve_skins(
                        REPO_ROOT,
                        None,
                        legacy_retarget_enabled=True,
                    )
                ],
            },
            "lodge_execution_plan": test_lodge_plans(lodge),
            "intergen_mock_outputs": test_intergen_outputs(intergen),
        }
    assert results["contract_resolution"]["explicit_smpl_overrides_legacy_flag"] == ["smpl"]
    assert results["contract_resolution"]["legacy_retarget_requests_both"] == ["smpl", "robot"]
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
