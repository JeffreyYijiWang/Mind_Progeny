from pathlib import Path
import json
from bioprinter.config import load_profile
from bioprinter.pipeline import compose,preflight,write_json
from bioprinter.video import create_video

root=Path(__file__).resolve().parents[1]
run=compose(root/'examples'/'inputs',load_profile(root/'profiles'/'synthetic.yaml'),
            output_root=root/'examples'/'run',progress=print)
movie=create_video(run,fps=2,size=(320,240),quadrants=True)
preflight(run,production=False)
write_json(root/'examples'/'latest.json',{'run':run.relative_to(root).as_posix(),'video':movie})
print(json.dumps({'run':str(run),'video':movie},indent=2))
