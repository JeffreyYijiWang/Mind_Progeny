# Explicit standalone Duet 2 operations

No development/demo/test/notebook Run All contacted `hans.local`. Tests use an httpx
MockTransport. The standalone RRF 3.x HTTP adapter is implemented but has not been
hardware-validated. It rejects DSF-emulated or missing object-model APIs rather than
assuming a native queue or SBC endpoint.

On the same LAN, explicitly request status:

```powershell
$env:DUET_PASSWORD = 'your local password'
.\.venv\Scripts\python.exe -m bioprinter duet --url http://hans.local status
```

Use `http://192.168.x.x:PORT` or a base URL if mDNS fails. Obtain the address from the
printer/router; the application does not scan the LAN or change Wi-Fi. A profile URL
documents the intended machine, while CLI `--url` explicitly chooses the connection.
Never put credentials into a URL, manifest or notebook output. HTTP on a local network
does not encrypt the password; use an appropriately protected local network/HTTPS proxy.

Status performs session authentication and read-only object-model queries, reports
firmware, selected tool, job identity, XYZ homing/position, file offset and polling latency.
It sends no G-code and does not adjust the printer clock. Read-only queries have bounded
retries; uploads and start/control commands are not automatically retried after ambiguity.

## Upload and start separately

Generate a fresh production run with a measured profile and no blocking diagnostics:

```text
python -m bioprinter export pictures --profile measured.yaml --width-mm 24 --production
python -m bioprinter duet --url http://hans.local upload REAL_RUN
```

The last command uploads the combined file without starting it. For ordered continuation
jobs use `upload REAL_RUN --jobs`. Only `/gcodes/bioprinter/<run-id>/` is writable through
this client. CRC32 is sent with the upload, and full remote bytes are downloaded and
compared. Different existing files are not overwritten. Firmware, macros and homing
files are never upload targets. Upload receipts are separate from immutable manifests.
The manual fallback is Duet Web Control: upload only a reviewed production G-code job.
Inspect machine state and explicitly start it there.

```text
python -m bioprinter duet --url http://hans.local run-queue REAL_RUN --start --watch
```

This preflights hashes/profile, validates firmware/tool, verifies the upload receipt and
remote bytes, and checks homed axes and expected starting pose. `--start` is mandatory
to send M32. A durable start intent is written before that one-time command. Reopening
a queue with ambiguous intent never sends the start again.

## Completion and recovery

Standalone RRF does **not** expose the DSF/DWC-maintained `lastFileCancelled` and
`lastFileAborted` fields. File position is buffered progress, not executed motion;
idle and `lastFileName` alone are not proof of success. Therefore the current adapter
stops at `awaiting_confirmation` after observing the correct running identity and
subsequent idle state. It never automatically advances on that evidence.

After inspecting the physical result, remaining material and final pose, explicitly
confirm successful completion of the exact current job:

```text
python -m bioprinter duet --url http://hans.local run-queue REAL_RUN --confirm-completed job-0001
python -m bioprinter duet --url http://hans.local run-queue REAL_RUN --start --watch
```

Confirmation also requires matching last-job identity and end pose. A cancellation,
fault, disconnect, unobserved short job, mismatched identity or lost start reply remains
unresolved until operator reconciliation. There is no automatic restart or rewind.
If material/pose/predecessor are uncertain, retain the queue and replan after physical
recovery. Never home through an existing stack or reset Z to a bare substrate. A stale
queue lock after process failure also requires checking no other runner is active.

## Pause, resume, cancel and live display

The explicit `pause`, `resume` and `cancel` subcommands use M25, M24 and M0 and require
`--reviewed-macros`, because the installed machine may invoke pause/resume/stop macros.
Review those locally for syringe motion and thermal/fan effects first. The client records
before/after status; firmware feedback can lag. Host control is not a physical emergency stop.

`duet display REAL_RUN --samples 20 --poll-seconds 2` records approximate active-image
observations into `timing/observed.json`. It holds the image on pause/disconnection and
reports measured request latency; processed-byte buffering adds unknown execution error.
It does not overwrite the planned timeline or pretend uploaded bytes are finished motion.
The self-contained HTML player is an offline time-based rehearsal. There is no live
browser-to-printer bridge or executed-segment marker implementation in this version.

Cold extrusion is firmware-dependent. Consult the actual firmware's M302 documentation
and machine/tool configuration; this software never sends M302 or changes config.g.
