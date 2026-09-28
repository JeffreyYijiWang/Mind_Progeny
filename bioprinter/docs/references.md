# Official sources consulted

Consulted on 2026-09-28 UTC; local machine date was the evening of 2026-09-27 EDT.
These document API/command semantics, not validation of this particular printer.

- [Duet RepRapFirmware HTTP requests](https://github.com/Duet3D/RepRapFirmware/wiki/HTTP-requests):
  standalone rr_connect, rr_model, rr_upload (CRC32), rr_download, rr_mkdir and rr_gcode.
- [Duet object model](https://github.com/Duet3D/RepRapFirmware/wiki/Object-Model-Documentation):
  boards/state/move/job fields. Explicitly marks lastFileCancelled/lastFileAborted as
  DSF/DWC-maintained and unavailable on standalone firmware. This limits queue automation.
- [Duet G-code dictionary](https://docs.duet3d.com/User_manual/Reference/Gcodes):
  reference for dialect review, thermal settings and cold extrusion. The current page
  had no extractable body through the research tool; actual machine version is unqueried.
- [Duet IDEX configuration](https://docs.duet3d.com/User_manual/Machine_configuration/Configuration_IDEX):
  demonstrates mixed G10 offset/temperature parameters and macro-induced actions;
  supports rejecting mixed forms instead of deleting every G10.
- [Inkscape manual](https://inkscape.org/doc/inkscape-man.html): requested but the research
  fetch returned HTTP 403. [Inkscape 1.3 release notes](https://wiki.inkscape.org/wiki/Release_notes/1.3)
  were accessible. No local Inkscape executable/action list could be inspected; no headless
  tracing claim is made.
- [PrusaSlicer source repository](https://github.com/prusa3d/PrusaSlicer) and
  [official SVG embossing tool](https://help.prusa3d.com/article/svg-embossing-tool_686167):
  GUI SVG support is distinct from the headless mesh/CLI path. The CLI adapter must pass
  actual installed help/profile checks before use; no local executable was available.
- [FFmpeg formats](https://ffmpeg.org/ffmpeg-formats.html): MOV output/container behavior.
  Actual local `-version`, `-encoders`, rawvideo input and ffprobe duration were exercised.

Dependency licenses are summarized in [licenses.md](licenses.md). Tested versions and
tool outputs are preserved in each run's manifest and `reports/doctor.json`.
