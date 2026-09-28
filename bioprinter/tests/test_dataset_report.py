import importlib.util
from pathlib import Path
from PIL import Image
import pytest

spec=importlib.util.spec_from_file_location('dataset_report',Path(__file__).resolve().parents[1]/'scripts'/'test_image_dataset.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)


@pytest.mark.parametrize('pixels,expected',[
    ((1600,800),(93.6,46.8)),((800,1600),(59.5,119)),((1200,1200),(93.6,93.6))])
def test_quadrant_fit_preserves_aspect_and_respects_both_axes(tmp_path,pixels,expected):
    path=tmp_path/'input.png';Image.new('RGB',pixels,'white').save(path)
    settings={'max_working_pixels':800,'sizing':'fit-quadrant','usable_size_mm':[93.6,119]}
    result=runner.image_fit(path,settings)
    assert result['canvas_mm']==pytest.approx(expected,abs=1e-7)
    assert result['canvas_mm'][0]/result['canvas_mm'][1]==pytest.approx(pixels[0]/pixels[1])
    assert max(result['working_pixels'])==800
    assert Image.open(path).size==pixels


def test_report_uses_run_dimensions_and_only_existing_links(tmp_path):
    (tmp_path/'01').mkdir();(tmp_path/'01'/'result.json').write_text('{}')
    result={'index':1,'folder':'01','sha256':'fixture','input':'a & b.png','status':'failed','stage':'mesh',
            'size':{'canvas_mm':[59.5,119]},'error':'touching <boundary>','trace_passed':True}
    meta={'sizing':'fit-quadrant','quadrant_size_mm':[101.6,127],'usable_size_mm':[93.6,119],
          'margin_mm':4,'expected':1}
    data=runner.report(tmp_path,[result],meta);text=(tmp_path/'report.html').read_text(encoding='utf-8')
    assert data['completed']==1 and data['passed']==0
    assert '101.6 × 127' in text and '93.6 × 119' in text and '59.50 × 119.00 mm' in text
    assert 'a &amp; b.png' in text and 'touching &lt;boundary&gt;' in text
    assert 'href="01/result.json"' in text and 'href="01/raw.gcode"' not in text


def test_tracer_curve_overshoot_is_fitted_without_clipping():
    from bioprinter.geometry import Design
    from shapely.geometry import box
    d=Design(box(-46.824,-37.53,46.806,37.53),(-46.8,-37.53,46.8,37.53),[[1,0,0],[0,1,0],[0,0,1]])
    area=d.geometry.area;before_ratio=(46.824+46.806)/(37.53*2)
    scale=runner.fit_trace_extent(d,[93.6,119])
    x0,y0,x1,y1=d.geometry.bounds
    assert 0<scale<1 and x1-x0<93.6 and y1-y0<119
    assert d.geometry.area==pytest.approx(area*scale**2)
    assert (x1-x0)/(y1-y0)==pytest.approx(before_ratio)
