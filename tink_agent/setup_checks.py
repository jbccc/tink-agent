"""Pure-logic checks/actions behind the 'Set up TINK' onboarding window.

Every effectful call takes an injectable *_fn so the whole module is testable
with no hardware, permissions, or AppKit. The AppKit window (onboarding.py)
delegates here.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from .audio import resolve_device, DeviceNotFound

_MIC_MEDIA_TYPE = "soun"  # AVMediaTypeAudio four-char code
_MIC_STATUS = {0: "undetermined", 1: "restricted", 2: "denied", 3: "authorized"}


def mic_status(query_fn=None) -> str:
    """Microphone authorization: authorized|denied|undetermined|restricted."""
    if query_fn is None:
        import Quartz
        query_fn = lambda: Quartz.AVCaptureDevice.authorizationStatusForMediaType_(  # noqa: E731
            _MIC_MEDIA_TYPE)
    return _MIC_STATUS.get(int(query_fn()), "undetermined")


def request_mic(callback=None, request_fn=None) -> None:
    """Trigger the OS microphone-permission prompt (no-op if already decided)."""
    if request_fn is None:
        import Quartz
        request_fn = Quartz.AVCaptureDevice.requestAccessForMediaType_completionHandler_
    request_fn(_MIC_MEDIA_TYPE, callback or (lambda granted: None))


def accessibility_trusted(query_fn=None) -> bool:
    """True if this process is trusted for Accessibility (keystroke synthesis)."""
    if query_fn is None:
        import ApplicationServices
        query_fn = ApplicationServices.AXIsProcessTrusted
    return bool(query_fn())


def request_accessibility(prompt_fn=None) -> None:
    """Surface the OS Accessibility prompt directing the user to System Settings."""
    if prompt_fn is None:
        import ApplicationServices as A

        def prompt_fn():
            A.AXIsProcessTrustedWithOptions({A.kAXTrustedCheckOptionPrompt: True})
    prompt_fn()


_SAMPLE_NAMES = ("1.wav", "2.wav", "3.wav", "4.wav")


def tingdisk_path(volumes="/Volumes", name="TINGDISK") -> str:
    return os.path.join(volumes, name)


def is_tingdisk_mounted(path=None, exists_fn=os.path.isdir) -> bool:
    return bool(exists_fn(path or tingdisk_path()))


def audio_present(config, resolve_fn=None) -> bool:
    resolve_fn = resolve_fn or resolve_device
    try:
        resolve_fn(config.device_name)
        return True
    except DeviceNotFound:
        return False


def device_config_sources(repo_root):
    """Repo-side files to copy onto TINK: config.json + samples/1..4.wav."""
    base = Path(repo_root) / "ting-config"
    return [base / "config.json"] + [base / "samples" / n for n in _SAMPLE_NAMES]


def _dest_for(src, repo_root, tingdisk):
    rel = Path(src).relative_to(Path(repo_root) / "ting-config")
    return Path(tingdisk) / rel


def copy_device_config(repo_root, tingdisk) -> None:
    """Copy config + samples onto TINK (creates samples/)."""
    (Path(tingdisk) / "samples").mkdir(parents=True, exist_ok=True)
    for src in device_config_sources(repo_root):
        shutil.copy2(str(src), str(_dest_for(src, repo_root, tingdisk)))


def files_match(repo_root, tingdisk) -> bool:
    """True if every source exists on TINK with a matching byte size."""
    for src in device_config_sources(repo_root):
        dst = _dest_for(src, repo_root, tingdisk)
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            return False
    return True
