#!/usr/bin/env python3
"""PreToolUse gate: never drop a RoboLab eval request whose run has no composed_config.yaml on HF.

User directive 2026-08-28. The eval service materializes a checkpoint as
``<checkpoint.url>/composed_config.yaml`` + ``iter_*/<ckpt_kind>``; the trainer's HF backup
ships only ``config.yaml`` (the launcher writes composed_config.yaml into the LOCAL run dir at
submit), so the first eval of a cluster-trained run burned in 1 s whenever nobody uploaded the
file by hand (screen4 0826, screen19 / screen20 0828). The launcher now publishes it at submit
(cam_uva.infra.launcher.publish_composed_config); this hook is the backstop for runs submitted
before that, or whose publish failed.

Matches Bash commands that upload an eval request into a drop-box
(``storage_upload ... uri=<box>/requests/pending/<rid>.json`` via harness_call.py, key=value or
'{json}' form). For each: read the request JSON (local_path / name), take checkpoint.url
(adapter-only requests have none -> pass), and check ``<url>/composed_config.yaml`` with
``hf buckets ls``. Missing -> try to upload the local run dir's copy
(``$IMAGINAIRE_OUTPUT_ROOT/<url tail after checkpoints/imaginaire4-output/>/composed_config.yaml``);
success -> allow with a note; otherwise DENY with the exact fix. Anything unparseable passes
through untouched (the gate must never block unrelated commands).
"""
import json
import os
import re
import shlex
import subprocess
import sys

HF_MARK = "checkpoints/imaginaire4-output/"
OUTPUT_ROOT = os.environ.get("IMAGINAIRE_OUTPUT_ROOT") or os.path.expanduser("~/video-gen/repositories/imaginaire4-output")
EXCHANGE_DIRS = [os.path.expanduser("~/.cam_uva_mcp_harness/exchange"), "/tmp/cam_uva_mcp_harness/exchange"]
PENDING_RE = re.compile(r"requests/pending/[^\s'\"]+\.json")


def _decide(decision: str, reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                             "permissionDecisionReason": reason}}))


def _hf_ls(uri: str) -> bool | None:
    """True/False = file present/absent; None = could not tell (hf CLI missing / timeout / error)."""
    try:
        p = subprocess.run(["hf", "buckets", "ls", uri], capture_output=True, text=True, timeout=90)
    except Exception:
        return None
    if p.returncode != 0:
        return None if "not found" not in (p.stdout + p.stderr).lower() else False
    return "composed_config.yaml" in p.stdout


def _hf_cp(src: str, dst: str) -> bool:
    try:
        return subprocess.run(["hf", "buckets", "cp", src, dst], capture_output=True, text=True, timeout=120).returncode == 0
    except Exception:
        return False


def _request_uploads(command: str) -> list[dict]:
    """Every storage_upload invocation in the command that targets requests/pending/, as {uri, local_path, name}."""
    out = []
    for line in re.split(r"(?:\n|;|&&|\|\|)", command):
        if "storage_upload" not in line or "requests/pending/" not in line:
            continue
        spec: dict = {}
        m = re.search(r"'(\{.*\})'", line) or re.search(r'"(\{.*\})"', line)
        if m:
            try:
                spec = json.loads(m.group(1))
            except Exception:
                spec = {}
        if not spec:
            try:
                toks = shlex.split(line)
            except ValueError:
                toks = line.split()
            for t in toks:
                if "=" in t:
                    k, v = t.split("=", 1)
                    if k in ("uri", "local_path", "name"):
                        spec[k] = v
        if spec.get("uri") and "requests/pending/" in spec["uri"]:
            out.append(spec)
    return out


def _load_request(spec: dict) -> dict | None:
    path = spec.get("local_path")
    if not path and spec.get("name"):
        for d in EXCHANGE_DIRS:
            cand = os.path.join(d, spec["name"])
            if os.path.exists(cand):
                path = cand
                break
    if not path:
        return None
    path = os.path.expandvars(os.path.expanduser(path))
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def main() -> None:
    try:
        d = json.load(sys.stdin)
    except Exception:
        return
    if (d.get("tool_name") or "") != "Bash":
        return
    command = (d.get("tool_input") or {}).get("command") or ""
    uploads = _request_uploads(command)
    if not uploads:
        return
    notes = []
    for spec in uploads:
        req = _load_request(spec)
        if not req:
            continue  # unreadable request: the service will validate it; not this gate's job
        url = str(((req.get("checkpoint") or {}).get("url")) or "").rstrip("/")
        if not url:
            continue  # adapter-only request (pretrained cosmos3 ...): no run dir to check
        target = f"{url}/composed_config.yaml"
        present = _hf_ls(target)
        if present is True:
            continue
        if present is None:
            _decide("ask", f"composed_config gate: could not verify {target} (hf CLI error/timeout). "
                           "Check it by hand (`hf buckets ls <run root>`) before approving this drop.")
            return
        local = None
        if HF_MARK in url:
            local = os.path.join(OUTPUT_ROOT, url.split(HF_MARK, 1)[1], "composed_config.yaml")
        if local and os.path.isfile(local) and _hf_cp(local, target) and _hf_ls(target):
            notes.append(f"uploaded {local} -> {target}")
            continue
        _decide("deny", f"composed_config gate (directive 2026-08-28): {target} is MISSING on HF and no local copy "
                        f"could be uploaded ({local or 'no local run dir derivable'}). The eval service would burn this "
                        f"request in 1 s. Fix: `hf buckets cp <run dir>/composed_config.yaml {target}` (or download "
                        f"the run's config.yaml from its cluster output dir and upload it under that name), then re-drop.")
        return
    if notes:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow",
                                                 "permissionDecisionReason": "composed_config gate auto-fix: " + "; ".join(notes)}}))


main()
