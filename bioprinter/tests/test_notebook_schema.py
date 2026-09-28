from pathlib import Path
import json
import os
import subprocess
import sys
import nbformat
import jsonschema
import pytest

ROOT=Path(__file__).resolve().parents[1]


def test_timeline_schema(demo_run):
    schema=json.loads((ROOT/'schemas'/'display-timeline.schema.json').read_text())
    timeline=json.loads((demo_run/'timing'/'display_timeline.json').read_text())
    jsonschema.validate(timeline,schema)


@pytest.mark.notebook
def test_fresh_kernel_notebook_offline():
    env={**os.environ,'BIOPRINTER_OFFLINE_TEST':'1'}
    result=subprocess.run([sys.executable,str(ROOT/'scripts'/'execute_notebook.py')],cwd=ROOT,env=env,
                          capture_output=True,text=True,timeout=180)
    assert result.returncode==0,result.stdout+'\n'+result.stderr
    book=nbformat.read(ROOT/'notebooks'/'image_to_syringe_pipeline.ipynb',as_version=4)
    cells=[c for c in book.cells if c.cell_type=='code']
    assert len(cells)==11 and all(c.execution_count is not None for c in cells)
    assert not [o for c in cells for o in c.outputs if o.output_type=='error']
