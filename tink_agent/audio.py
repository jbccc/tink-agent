from __future__ import annotations
import sys
import time
import numpy as np


class DeviceNotFound(Exception):
    pass


def _default_on_status(status: str) -> None:
    # Goes to stderr -> the LaunchAgent run log (~/Library/Logs/TinkAgent.log),
    # so input overflow / device drops that truncate audio become visible.
    print(f"[audio] stream status: {status}", file=sys.stderr, flush=True)


def resolve_device(name: str, query_fn=None) -> int:
    if query_fn is None:
        import sounddevice as sd
        query_fn = sd.query_devices
    devices = query_fn()
    for idx, dev in enumerate(devices):
        if name.lower() in dev["name"].lower() and dev.get("max_input_channels", 0) > 0:
            return idx
    raise DeviceNotFound(f"No input device matching {name!r}")


def reinitialize() -> None:
    """Force PortAudio to re-enumerate devices.

    PortAudio caches the device list at initialization, so a hot-plugged or
    unplugged device is not reflected by query_devices() until it is
    re-initialized. The caller MUST stop any open stream first — terminating
    PortAudio under a live stream is undefined."""
    import sounddevice as sd
    sd._terminate()
    sd._initialize()


NOT_CONNECTED_SUFFIX = " (not connected)"


def input_device_names(query_fn=None) -> list[str]:
    """Names of available input devices, deduped (order-preserving) and sorted
    case-insensitively. query_fn injectable for tests."""
    if query_fn is None:
        import sounddevice as sd
        query_fn = sd.query_devices
    seen = []
    for dev in query_fn():
        name = dev["name"]
        if dev.get("max_input_channels", 0) > 0 and name not in seen:
            seen.append(name)
    return sorted(seen, key=str.lower)


def device_menu_items(saved_name: str, connected_names: list[str]) -> tuple[list[str], int]:
    """(dropdown titles, index to select) for the audio-source popup. A saved
    device that isn't currently connected is appended as a '(not connected)'
    placeholder and selected, so the choice survives unplug/replug.
    Presence is decided by the same case-insensitive substring rule
    resolve_device uses, so the UI status matches what capture will actually
    resolve."""
    items = list(connected_names)
    if saved_name:
        for i, name in enumerate(items):
            if saved_name.lower() in name.lower():
                return items, i
        items.append(f"{saved_name}{NOT_CONNECTED_SUFFIX}")
        return items, len(items) - 1
    return items, -1


def device_name_from_title(title: str) -> str | None:
    """Real device name for a chosen popup title, or None if it's the
    '(not connected)' placeholder (meaning: no change)."""
    if title.endswith(NOT_CONNECTED_SUFFIX):
        return None
    return title


class AudioCapture:
    def __init__(self, device_name, sample_rate, block_size, on_block,
                 stream_factory=None, resolve_fn=None, on_status=None,
                 capture_rate=0, capture_channels=1, input_channel=0):
        self.device_name = device_name
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.on_block = on_block
        self._resolve = resolve_fn or resolve_device
        self._stream_factory = stream_factory
        self._on_status = on_status or _default_on_status
        self._stream = None
        # Native-rate capture path: open the device at capture_rate with
        # capture_channels, take input_channel, decimate to sample_rate.
        # capture_rate 0 = the simple mono sample_rate path.
        self._capture_rate = int(capture_rate) or self.sample_rate
        self._capture_channels = max(1, int(capture_channels))
        self._input_channel = int(input_channel)
        self._decim = max(1, round(self._capture_rate / self.sample_rate))

    def _make_stream(self, device_index):
        if self._stream_factory is not None:
            factory = self._stream_factory
        else:
            import sounddevice as sd
            factory = sd.InputStream
        # Open block_size at the CAPTURE rate so that after decimation we emit
        # ~block_size samples at sample_rate to the detector/VAD.
        return factory(device=device_index, channels=self._capture_channels,
                       samplerate=self._capture_rate,
                       blocksize=self.block_size * self._decim,
                       dtype="int16", callback=self._callback)

    def _callback(self, indata, frames, time_info, status):
        # Heartbeat: stamp every delivered block. When the USB adapter drops,
        # PortAudio often does NOT flip is_running or fire a status callback — the
        # stream just goes silent forever. A stale heartbeat is the ONLY reliable,
        # notification-independent signal that the device vanished, so the menubar
        # can rebind. Cheap monotonic read; safe from the audio thread.
        self.last_block_at = time.monotonic()
        if status:
            # input overflow / device error — report but still forward the block
            try:
                self._on_status(str(status))
            except Exception:  # noqa: BLE001 — logging must never break capture
                pass
        data = np.asarray(indata, dtype=np.int16)
        if data.ndim == 2 and data.shape[1] > 1:
            ch = min(self._input_channel, data.shape[1] - 1)
            mono = data[:, ch]
        else:
            mono = data.reshape(-1)
        if self._decim > 1:
            mono = mono[::self._decim]
        block = np.ascontiguousarray(mono, dtype=np.int16)
        self.on_block(block)

    def start(self):
        # The USB adapter sleeps and drops off the bus; on wake, PortAudio
        # RENUMBERS its (cached) device list. A stale index can silently point at
        # the built-in MacBook mic — so we must (1) re-enumerate to clear the
        # cache, (2) resolve by name, and (3) HARD-VERIFY the bound device's real
        # name matches what we asked for. Never fall through to the wrong mic:
        # capturing room noise off the built-in mic is worse than not capturing.
        try:
            reinitialize()  # clear PortAudio's cached device list (sleep/wake churn)
        except Exception:  # noqa: BLE001 — a failed re-init must not block start
            pass
        idx = self._resolve(self.device_name)
        bound = None
        try:
            import sounddevice as sd
            bound = sd.query_devices(idx)["name"]
        except Exception:  # noqa: BLE001
            pass
        # Guard: the resolved index must actually BE the device we want. If the
        # adapter is asleep/absent, resolve_device already raises DeviceNotFound;
        # this catches the subtler case where churn made the index point elsewhere.
        if bound is not None and self.device_name.lower() not in bound.lower():
            raise DeviceNotFound(
                f"idx {idx} is {bound!r}, not {self.device_name!r} "
                f"(refusing to capture the wrong mic)")
        print(f"[audio] bound input device idx={idx} name={bound!r} "
              f"(wanted {self.device_name!r})", file=sys.stderr, flush=True)
        # Seed the heartbeat so a just-opened stream isn't flagged stale before
        # its first block arrives.
        self.last_block_at = time.monotonic()
        self._stream = self._make_stream(idx)
        self._stream.start()

    def blocks_stale_for(self) -> float:
        """Seconds since the last block was delivered (0 if never started). A
        large value on a supposedly-running stream means the device dropped
        silently — PortAudio didn't tell us, the blocks just stopped."""
        last = getattr(self, "last_block_at", 0.0)
        return 0.0 if not last else max(0.0, time.monotonic() - last)

    def stop(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    @property
    def is_running(self) -> bool:
        return self._stream is not None
