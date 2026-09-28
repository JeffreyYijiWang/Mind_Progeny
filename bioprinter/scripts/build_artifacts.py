"""Maintainer generator for shipped profiles, schemas, samples and notebook source."""
from pathlib import Path
import json
import subprocess
import sys
import yaml
import nbformat as nb
from bioprinter.config import Profile,demo_profile
from bioprinter.examples import make_inputs

ROOT=Path(__file__).resolve().parents[1]
for name in ['profiles','schemas','notebooks','locks','validation']:(ROOT/name).mkdir(exist_ok=True)
(ROOT/'config.example.yaml').write_text('# Real Duet 2: unresolved values deliberately remain null. See docs/machine-profile.md.\n'+yaml.safe_dump(Profile().model_dump(),sort_keys=False),encoding='utf-8')
(ROOT/'profiles'/'synthetic.yaml').write_text('# INVENTED simulation values. Never authorizes printer upload/start.\n'+yaml.safe_dump(demo_profile().model_dump(),sort_keys=False),encoding='utf-8')
(ROOT/'schemas'/'machine-profile.schema.json').write_text(json.dumps(Profile.model_json_schema(),indent=2),encoding='utf-8')
make_inputs(ROOT/'examples'/'inputs')
(ROOT/'examples'/'order.json').write_text(json.dumps({'order':['image1_ring.png','image2_asymmetric_L.png','image10_bridge_island.png'],
    'sequences':{'Q1':['image1_ring.png','image2_asymmetric_L.png','image10_bridge_island.png'],
                 'Q2':['image2_asymmetric_L.png'],'Q3':[],'Q4':['image10_bridge_island.png']},
    'per_image':{'image1_ring.png':{'threshold':128,'simplify_mm':0.05}}},indent=2),encoding='utf-8')
event_required=['event_id','asset_id','source_path','source_sha256','svg_path','quadrant','sequence_index','nominal_layer_index','job_id',
    'start_s','end_s','duration_s','deposition_start_s','deposition_end_s','byte_start','byte_end','line_start','line_end','display_action','timing_status']
event_props={key:{'type':'string'} for key in event_required}
for key in ['start_s','end_s','duration_s','deposition_start_s','deposition_end_s']:event_props[key]={'type':'number','minimum':0}
for key in ['sequence_index','nominal_layer_index','byte_start','byte_end','line_start','line_end']:event_props[key]={'type':'integer','minimum':0}
event_props['quadrant']={'enum':['Q1','Q2','Q3','Q4']};event_props['display_action']={'enum':['show','hold','blank']}
schema={'$schema':'https://json-schema.org/draft/2020-12/schema','title':'Bioprinter display timeline v1','type':'object',
    'required':['schema_version','gcode_sha256','origin','timing','events'],
    'properties':{'schema_version':{'const':'1.0'},'gcode_sha256':{'type':'string','pattern':'^[a-f0-9]{64}$'},
        'events':{'type':'array','minItems':1,'items':{'type':'object','required':event_required,'properties':event_props}},
        'timing':{'type':'object','required':['total_s','model','status'],'properties':{'total_s':{'type':'number','exclusiveMinimum':0}}}}}
(ROOT/'schemas'/'display-timeline.schema.json').write_text(json.dumps(schema,indent=2),encoding='utf-8')
cells=[]
def md(text):cells.append(nb.v4.new_markdown_cell(text))
def code(text):cells.append(nb.v4.new_code_cell(text))
md('# Image → SVG → syringe pipeline\n\nThis notebook runs entirely offline with the **synthetic simulation profile**. Run All creates a new audited run; it never contacts, homes or starts a printer. All implementation lives in `src/bioprinter`. The demo intentionally exposes uneven support, so preview success is not production approval.\n\nUse the bioprinter `.venv` Python kernel. Install dependencies using `scripts/bootstrap.ps1` or `scripts/bootstrap.sh`.')
code('''from pathlib import Path
import os, json
ROOT = Path.cwd().resolve()
if ROOT.name == 'notebooks': ROOT = ROOT.parent
assert (ROOT / 'pyproject.toml').exists(), 'Start Jupyter from the bioprinter folder'
if os.environ.get('BIOPRINTER_OFFLINE_TEST') == '1':
    import httpx
    def no_network(*args, **kwargs): raise AssertionError('Notebook must remain offline')
    httpx.Client.request = no_network
from IPython.display import display, Image, HTML
from bioprinter.config import load_profile
from bioprinter.external import doctor
PROFILE = load_profile(ROOT / 'profiles/synthetic.yaml')
capabilities = doctor(PROFILE)
display({'Python': capabilities['python'], 'profile': PROFILE.name,
         'external': {k: v.get('version', 'not found') for k,v in capabilities['external'].items()},
         'production_allowed': not PROFILE.missing(True)})''')
md('## Folder, order and per-image settings\n\nNatural filename order is deterministic. Set `ORDER` to a list of filenames to override it; repeated entries repeat designs. `SEQUENCES` can set different lists for Q1–Q4, including empty lists. All input originals are copied and hashed. Multi-page/animated inputs must be split first.')
code('''from bioprinter.ingestion import discover
INPUT_FOLDER = ROOT / 'examples/inputs'
ORDER = None
SEQUENCES = None  # e.g. {'Q1': ['image1_ring.png'], 'Q2': [], 'Q3': [], 'Q4': []}
PER_IMAGE = {'image1_ring.png': {'threshold': 128, 'simplify_mm': 0.05}}
assets = discover(INPUT_FOLDER, order=ORDER)
display([a.metadata() for a in assets])''')
md('## Vectorization comparison\n\nThe custom backend extracts real filled polygons with holes. Inkscape is an explicit manual round-trip if no fixture-verified headless tracer is available: Path → Trace Bitmap, remove raster, save Plain SVG. Selecting `inkscape` never silently chooses Python. Existing SVG strokes become filled geometry; raster centerlines are unsupported.')
code('''from bioprinter.vectorization import vectorize
from bioprinter.geometry import register, anchor_point
designs = [vectorize(a.path, width_mm=24) for a in assets]
display([{'name': a.path.name, 'backend': d.metadata['backend'], 'area_mm2': round(d.geometry.area, 3),
          'bounds_mm': d.geometry.bounds} for a,d in zip(assets,designs)])
display(Image(filename=str(assets[0].path)))''')
md('## Dimensions, anchors and registration\n\n23 gauge and 12.7 mm needle length are the two individually confirmed specifications from the supplied brief. Bore, outer diameter, barrel and bead width are separate. Physical width is mandatory for raster input. Shared canvas is the default: preserve offsets and use a common scale across the stack. Bottom-left is design-local (0,0); the machine origin stays at plate center.')
code('''WIDTH_MM = 24.0
ANCHOR = 'bottom_left'
REGISTRATION = 'shared_canvas'
display({name: anchor_point(designs[0].geometry.bounds, name)
         for name in ['bottom_left','bottom_right','top_left','top_right','center']})
display(register(designs[0], ANCHOR, REGISTRATION).metadata)''')
md('## Slice and calibration settings\n\nThe demo explicitly selects direct polygon paths. PrusaSlicer uses a watertight mm-convention STL and records its probed CLI/config; it was not installed during development. Real 0.5 mm layers may be incompatible with the measured bore. Do not falsify a nozzle dimension to bypass that rejection. Top/bottom solid layers can override sparse infill.\n\nFinal E is calibrated relative syringe units. Filament E is converted to volume first, then divided by measured mm³/E; G92 does not refill capacity. No uncalibrated priming/retraction is reused.')
code('''BACKEND = 'direct'
PERIMETERS = 1
INFILL_DENSITY = 0.15
STACK_MODE = 'overlap_aware'
SCHEDULE = 'round_robin'
display({'layer_mm': PROFILE.deposition_height_mm, 'bead_width_mm': PROFILE.bead_width_mm,
         'mm3_per_E_unit': PROFILE.mm3_per_e_unit, 'capacity_mm3': PROFILE.capacity_mm3,
         'warning': 'These values are synthetic, not measurements'})''')
md('## Compose the stack and all four quadrants\n\nQ1 top-right → Q2 bottom-right → Q3 bottom-left → Q4 top-left. Each design is applied to the height field in execution order. Sparse gaps and holes stay empty. At changes in support, lift/relocate instead of extruding through a vertical jump. Keyboard interrupt cancels between/within Python work; an incomplete run is never uploadable.')
code('''from bioprinter.pipeline import compose, preflight
RUN = compose(INPUT_FOLDER, PROFILE, output_root=ROOT/'runs', width_mm=WIDTH_MM,
              order=ORDER, sequences=SEQUENCES, per_image=PER_IMAGE,
              anchor=ANCHOR, registration=REGISTRATION, backend=BACKEND,
              perimeters=PERIMETERS, infill_density=INFILL_DENSITY,
              stack_mode=STACK_MODE, schedule_mode=SCHEDULE, progress=print)
print('Run:', RUN)
resolved, manifest = preflight(RUN, production=False)
display({'segments': len(manifest['events']), 'volume_mm3': manifest['used_mm3'],
         'production_blocking_diagnostics': manifest['diagnostics']})''')
md('## G-code cleanup report\n\nModal parsing resolves XYZ/E modes, units and resets. Pure thermal/fan commands (including off commands) are removed. Unknown motions, arcs, macros, tool changes and mixed/nonthermal G10 forms reject. Every final file is serialized and reparsed against an allowlist. There is one coherent combined prologue and no homing at continuation boundaries.')
code('''cleanup = json.loads(next((RUN/'reports').glob('*.cleanup.json')).read_text())
display(cleanup)
print((RUN/'combined/combined.gcode').read_text()[:600])''')
md('## Quadrant and 3D motion preview\n\nThe image shows deposited paths and conservative surface heights. Open the self-contained Plotly HTML for rotation/zoom and travel visibility. These are geometric approximations; spreading, curing, pressure and liquid stability remain experimental.')
code('''display(Image(filename=str(RUN/'previews/plate.png')))
print('Interactive 3D:', RUN/'previews/motion3d.html')
display(HTML('<a href="../' + (RUN/'previews/motion3d.html').relative_to(ROOT).as_posix() + '" target="_blank">Open interactive 3D preview</a>'))''')
md('## Timeline, exact bytes and display player\n\nTiming comes from final filtered G-code with axis and E limits, acceleration and zero junction speed. This is an estimate; transfer/firmware/pressure delays remain unknown. Display intervals cover the whole modeled motion schedule and hold the last image. Byte positions do not establish completed physical movement. Live observations are saved separately; pause holds the active image.')
code('''timeline = json.loads((RUN/'timing/display_timeline.json').read_text())
display(timeline['timing'])
display([{k: e[k] for k in ['event_id','quadrant','start_s','end_s','byte_start','byte_end']} for e in timeline['events']])
print('Offline display player:', RUN/'previews/display_player.html')''')
md('## Optional MOV\n\nEnable only if desired. FFmpeg is optional and has no effect on geometry/planning. Cumulative frame rounding avoids drift, the final frame receives its full interval, and ffprobe checks the output duration. A planned movie cannot follow arbitrary physical pauses.')
code('''MAKE_VIDEO = False
if MAKE_VIDEO:
    from bioprinter.video import create_video
    display(create_video(RUN, fps=2, size=(320,240)))
else:
    print('MOV skipped. Set MAKE_VIDEO=True to render this run.')''')
md('## Optional explicit batch widgets\n\nReading this cell only creates controls. Click **Run offline batch** to create another timestamped run. Move up/down edits order, per-image JSON accepts threshold/size/registration settings, and **Cancel batch** requests cancellation at the next stage/segment boundary. Reruns preserve previous outputs.')
code('''from bioprinter.notebook_ui import batch_panel
batch_state = batch_panel(INPUT_FOLDER, PROFILE, ROOT/'runs')''')
md('## Printer controls — separate explicit invocation\n\nRun All does not execute printer code. First fill `config.example.yaml`, mark measured fields, review the actual firmware/cold-extrusion/tool setup, and produce a clean `--production` run. Upload and start are separate. The synthetic run above is rejected by both.\n\nFrom a terminal in this folder (these are documentation, not executable notebook cells):\n\n```text\npython -m bioprinter duet --url http://hans.local status\npython -m bioprinter duet --url http://hans.local upload REAL_RUN --jobs\npython -m bioprinter duet --url http://hans.local run-queue REAL_RUN --start --watch\npython -m bioprinter duet --url http://hans.local run-queue REAL_RUN --confirm-completed job-0001\n```\n\nStandalone RRF cannot reliably prove cancellation vs successful completion from idle alone; the host queue waits for an operator to confirm physical completion before a successor can start. Confirm pose, deposited material and remaining syringe capacity. Never use a checkpoint as automatic physical resume. Pause/resume/cancel can invoke installed machine macros and require `--reviewed-macros`. Host control is not a physical emergency stop. See `docs/duet.md`.')
notebook=nb.v4.new_notebook(cells=cells,metadata={'kernelspec':{'display_name':'Python 3 (bioprinter .venv)','language':'python','name':'python3'},'language_info':{'name':'python','version':sys.version.split()[0]}})
nb.write(notebook,ROOT/'notebooks/image_to_syringe_pipeline.ipynb')
freeze=subprocess.check_output([sys.executable,'-m','pip','freeze','--all'],text=True)
freeze='\n'.join(line for line in freeze.splitlines() if not line.startswith(('-e ', '# Editable','bioprinter-pipeline')))+'\n'
(ROOT/'locks'/'windows-py311.txt').write_text('# Tested Windows Python 3.11 full environment. Install this then pip install --no-deps -e .\n'+freeze,encoding='utf-8')
print('Generated profiles, schemas, sample drawings, notebook and tested environment lock')
