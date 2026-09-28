"""Optional widgets. Constructing the panel never starts a batch or contacts hardware."""
import json
from pathlib import Path
from threading import Event,Thread
import ipywidgets as w
from IPython.display import display
from .ingestion import discover
from .pipeline import compose


def batch_panel(folder,profile,output_root):
    folder=w.Text(value=str(folder),description='Folder',layout=w.Layout(width='90%'))
    order=w.Select(options=[a.path.name for a in discover(folder.value)],rows=6,description='Order')
    width=w.FloatText(value=24,description='Width mm')
    anchor=w.Dropdown(options=['bottom_left','center','top_left','top_right','bottom_right'],description='Anchor')
    registration=w.Dropdown(options=['shared_canvas','per_design_bbox'],description='Register')
    mode=w.Dropdown(options=['overlap_aware','planar_stack'],description='Stack')
    per_image=w.Textarea(value='{}',description='Per image',layout=w.Layout(width='90%'))
    refresh=w.Button(description='Read folder');up=w.Button(description='Move up');down=w.Button(description='Move down')
    start=w.Button(description='Run offline batch',button_style='primary');cancel=w.Button(description='Cancel batch')
    output=w.Output();stop=Event();state={'running':False,'run':None}
    def reorder(delta):
        if state['running'] or order.index is None:return
        values=list(order.options);i=order.index;j=max(0,min(len(values)-1,i+delta))
        values[i],values[j]=values[j],values[i];order.options=values;order.index=j
    up.on_click(lambda _:reorder(-1));down.on_click(lambda _:reorder(1))
    def reload(_):
        if state['running']:return
        try:order.options=[a.path.name for a in discover(folder.value)]
        except Exception as exc:output.append_stdout(str(exc)+'\n')
    refresh.on_click(reload);cancel.on_click(lambda _:stop.set())
    def run(_):
        if state['running']:return
        try:
            options=dict(width_mm=width.value,anchor=anchor.value,registration=registration.value,
                         stack_mode=mode.value,order=list(order.options),per_image=json.loads(per_image.value))
        except Exception as exc:output.append_stdout(str(exc)+'\n');return
        source=folder.value;state['running']=True;start.disabled=True;stop.clear();output.clear_output()
        def worker():
            try:
                result=compose(source,profile,output_root=output_root,cancelled=stop.is_set,
                    progress=lambda text:output.append_stdout(text+'\n'),**options)
                state['run']=result;output.append_stdout('Created '+str(result)+'\n')
            except Exception as exc:output.append_stdout('Stopped: '+str(exc)+'\n')
            finally:state['running']=False;start.disabled=False
        Thread(target=worker,daemon=True).start()
    start.on_click(run)
    panel=w.VBox([folder,refresh,order,w.HBox([up,down]),w.HBox([width,anchor,registration,mode]),per_image,w.HBox([start,cancel]),output])
    display(panel)
    return state
