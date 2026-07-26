import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.skin_catalog import public_skin_catalog, resolve_skin_resource, resolve_skins


RETARGET_SKINS = {
    "robot": ("X Bot.fbx", "mapping.json"),
    "aj": ("Aj (1).fbx", "mapping.json"),
    "ch09_nonpbr": ("Ch09_nonPBR (1).fbx", "mapping6.json"),
    "ch46_nonpbr": ("Ch46_nonPBR (1).fbx", "mapping.json"),
    "y_bot": ("Y Bot.fbx", "mapping.json"),
}


def load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_lodge_plans(lodge):
    cases = {
        "smpl_only": (["smpl"], False, True),
        "multi": (["smpl", "robot"], True, True),
    }
    cases.update(
        {
            f"{skin_id}_only": ([skin_id], True, False)
            for skin_id in RETARGET_SKINS
        }
    )
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
        if expected_retarget:
            retarget_skin_id = next(
                skin_id for skin_id in skin_ids if skin_id in RETARGET_SKINS
            )
            expected_fbx, expected_mapping = RETARGET_SKINS[retarget_skin_id]
            assert Path(options["target_fbx"]).name == expected_fbx
            assert Path(options["mapping_file"]).name == expected_mapping
        results[name] = {
            "retarget": options["enabled"],
            "smpl": options["render_smpl"],
            "skin_id": options["skin_id"],
        }
    return results


def test_catalog_resources():
    requested_ids = ["smpl", *RETARGET_SKINS]
    profiles = {
        str(profile["id"]): profile
        for profile in resolve_skins(REPO_ROOT, requested_ids)
    }
    assert list(profiles) == requested_ids

    public_ids = [
        str(profile["id"])
        for profile in public_skin_catalog(REPO_ROOT)["skins"]
    ]
    assert public_ids == requested_ids

    results = {}
    for skin_id, (expected_fbx, expected_mapping) in RETARGET_SKINS.items():
        profile = profiles[skin_id]
        target_fbx = Path(resolve_skin_resource(REPO_ROOT, profile, "target_fbx"))
        mapping_file = Path(
            resolve_skin_resource(REPO_ROOT, profile, "mapping_file")
        )
        assert target_fbx.is_file()
        assert mapping_file.is_file()
        assert target_fbx.name == expected_fbx
        assert mapping_file.name == expected_mapping
        results[skin_id] = {
            "target_fbx": target_fbx.name,
            "mapping_file": mapping_file.name,
        }
    return results


def test_intergen_outputs(intergen):
    original_generate = intergen.service.generate
    original_retarget = intergen._run_intergen_retarget_if_requested

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
        "multi": ["smpl", "robot"],
    }
    cases.update(
        {
            f"{skin_id}_only": [skin_id]
            for skin_id in RETARGET_SKINS
        }
    )
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
        has_retarget = any(skin_id in RETARGET_SKINS for skin_id in skin_ids)
        if has_retarget:
            assert task.output_retarget_path and Path(task.output_retarget_path).is_file()
        else:
            assert task.output_retarget_path is None
        results[name] = {
            "available_skin_ids": task.available_skin_ids,
            "smpl_video": bool(task.output_mp4_path),
            "retarget_video": bool(task.output_retarget_path),
        }
    intergen.service.generate = original_generate
    intergen._run_intergen_retarget_if_requested = original_retarget
    return results


def test_intergen_person_skin_manifest(intergen, task_root):
    task_id = "person-skin-pair"
    now = "2026-07-26T00:00:00Z"
    person_skin_ids = ["aj", "ch09_nonpbr"]
    intergen._tasks[task_id] = intergen.TaskInfo(
        task_id=task_id,
        status="running",
        created_at=now,
        updated_at=now,
        skin_id=person_skin_ids[0],
        requested_skin_ids=person_skin_ids,
        person_skin_ids=person_skin_ids,
    )

    output_path = task_root / task_id / "output" / f"{task_id}.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(b"preview")
    raw_paths = []
    for person_index in (1, 2):
        raw_path = task_root / task_id / "raw" / f"person{person_index}.npy"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(raw_path, np.zeros((12, 22, 3), dtype=np.float32))
        raw_paths.append(str(raw_path))

    fake_blender = task_root / "blender.exe"
    fake_blender.write_bytes(b"fake")
    original_export = intergen._export_intergen_bvh
    original_run = intergen._run_subprocess

    def fake_export(_task_id, current_root, _raw_path, person_idx=1):
        bvh_path = current_root / "retarget" / f"{task_id}_person{person_idx}.bvh"
        bvh_path.parent.mkdir(parents=True, exist_ok=True)
        bvh_path.write_text("HIERARCHY", encoding="utf-8")
        return bvh_path

    def fake_run(command, cwd, timeout_sec=None):
        del cwd, timeout_sec
        manifest_path = Path(command[-1])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        Path(manifest["output_mp4"]).write_bytes(b"dual-person-video")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    try:
        intergen._export_intergen_bvh = fake_export
        intergen._run_subprocess = fake_run
        req = intergen.GenerateMotionRequest(
            text="Two people dance.",
            person_a_skin_id=person_skin_ids[0],
            person_b_skin_id=person_skin_ids[1],
            blender_executable=str(fake_blender),
        )
        intergen._run_intergen_retarget_if_requested(
            task_id=task_id,
            task_root=task_root / task_id,
            output_path=output_path,
            raw_joints_files=raw_paths,
            req=req,
        )
    finally:
        intergen._export_intergen_bvh = original_export
        intergen._run_subprocess = original_run

    manifest_path = task_root / task_id / "retarget" / "retarget_manifest.json"
    assert manifest_path.is_file(), intergen._tasks[task_id].retarget_message
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["person_skin_ids"] == person_skin_ids
    assert [Path(path).name for path in manifest["target_fbx_files"]] == [
        "Aj (1).fbx",
        "Ch09_nonPBR (1).fbx",
    ]
    assert [Path(path).name for path in manifest["mapping_files"]] == [
        "mapping.json",
        "mapping6.json",
    ]
    assert intergen._tasks[task_id].retarget_status == "succeeded"

    try:
        intergen._resolve_person_skin_profiles(
            intergen.GenerateMotionRequest(
                text="Two people dance.",
                person_a_skin_id="smpl",
                person_b_skin_id="robot",
            )
        )
    except intergen.SkinCatalogError:
        pass
    else:
        raise AssertionError("SMPL must not be accepted as a Blender person skin")

    return {
        "person_skin_ids": manifest["person_skin_ids"],
        "target_fbx_files": [Path(path).name for path in manifest["target_fbx_files"]],
        "mapping_files": [Path(path).name for path in manifest["mapping_files"]],
        "retarget_status": intergen._tasks[task_id].retarget_status,
    }


def main():
    compile(
        (REPO_ROOT / "LODGE_api" / "blender_rokoko_retarget.py").read_text(encoding="utf-8"),
        "LODGE_api/blender_rokoko_retarget.py",
        "exec",
    )
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
            "catalog_resources": test_catalog_resources(),
            "lodge_execution_plan": test_lodge_plans(lodge),
            "intergen_mock_outputs": test_intergen_outputs(intergen),
            "intergen_person_skin_manifest": test_intergen_person_skin_manifest(
                intergen,
                Path(temp_dir),
            ),
        }
    assert results["contract_resolution"]["explicit_smpl_overrides_legacy_flag"] == ["smpl"]
    assert results["contract_resolution"]["legacy_retarget_requests_both"] == ["smpl", "robot"]
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
