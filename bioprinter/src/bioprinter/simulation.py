from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np
import plotly.graph_objects as go

COLORS={'Q1':'#e45756','Q2':'#f2a541','Q3':'#28a99e','Q4':'#5b75cf'}


def previews(run,motions,field,timeline):
    run=Path(run);by_event={e['event_id']:e for e in timeline['events']}
    fig,axes=plt.subplots(1,2,figsize=(12,9),layout='constrained')
    segments=[];colors=[]
    for m in motions:
        if m.e_delta:
            segments.append([m.start[:2],m.end[:2]])
            colors.append(COLORS[by_event[m.event]['quadrant']])
    axes[0].add_collection(LineCollection(segments,colors=colors,linewidths=.7))
    for ax in axes:
        ax.set(xlim=(field.p.x_min,field.p.x_max),ylim=(field.p.y_min,field.p.y_max),xlabel='X (mm)',ylabel='Y (mm)')
        ax.set_aspect('equal');ax.axhline(0,color='#aaa',lw=.7);ax.axvline(0,color='#aaa',lw=.7)
    axes[0].set_title('Deposited toolpaths / centered machine frame')
    im=axes[1].imshow(field.z,extent=(field.p.x_min,field.p.x_max,field.p.y_min,field.p.y_max),origin='lower',cmap='viridis',aspect='equal')
    axes[1].set_title('Conservative geometric height field')
    fig.colorbar(im,ax=axes[1],label='Surface Z (mm)',shrink=.7)
    fig.suptitle('SYNTHETIC PREVIEW — not liquid stability validation' if field.p.synthetic else 'Geometric preview — inspect support diagnostics')
    fig.savefig(run/'previews'/'plate.png',dpi=130);plt.close(fig)
    plot=go.Figure()
    quadrant_colors=[];design_colors=[];layer_colors=[]
    palette=['#3465a4','#de7c28','#7b4fa1','#28a99e','#d95062']
    asset_ids=list(dict.fromkeys(e['asset_id'] for e in timeline['events']))
    for event in timeline['events']:
        q=event['quadrant'];color=COLORS[q]
        xyz=[[],[],[]]
        for m in motions:
            if m.e_delta and m.event==event['event_id']:
                for k in range(3):xyz[k].extend([m.start[k],m.end[k],None])
        plot.add_trace(go.Scatter3d(x=xyz[0],y=xyz[1],z=xyz[2],mode='lines',name=f"{q} / layer {event['nominal_layer_index']+1} / {event['asset_id'][:6]}",line=dict(color=color,width=4)))
        quadrant_colors.append(color)
        design_colors.append(palette[asset_ids.index(event['asset_id'])%len(palette)])
        layer_colors.append(palette[event['nominal_layer_index']%len(palette)])
    xyz=[[],[],[]]
    for m in motions:
        if not m.e_delta:
            for k in range(3):xyz[k].extend([m.start[k],m.end[k],None])
    plot.add_trace(go.Scatter3d(x=xyz[0],y=xyz[1],z=xyz[2],mode='lines',name='Non-depositing travel',visible='legendonly',line=dict(color='#999',width=2)))
    plot.update_layout(title='Motion preview — geometric approximation; toggle travel in legend',scene=dict(xaxis_title='X mm',yaxis_title='Y mm',zaxis_title='Tip Z mm',aspectmode='data'),
        updatemenus=[dict(type='dropdown',x=0,y=1.1,buttons=[dict(label=label,method='restyle',args=[{'line.color':colors+['#999']}])
            for label,colors in [('Color: quadrant',quadrant_colors),('Color: design',design_colors),('Color: layer',layer_colors)]])])
    plot.write_html(run/'previews'/'motion3d.html',include_plotlyjs=True,auto_open=False)


def collision_preview(run,planner,error):
    point=error.location or planner.position
    fig=go.Figure()
    xyz=[[],[],[]]
    for m in planner.plan.motions:
        for k in range(3):xyz[k].extend([m.start[k],m.end[k],None])
    fig.add_trace(go.Scatter3d(x=xyz[0],y=xyz[1],z=xyz[2],mode='lines',name='Partial plan',line=dict(color='#777')))
    fig.add_trace(go.Scatter3d(x=[point[0]],y=[point[1]],z=[point[2]],mode='markers',name='Rejected collision location',marker=dict(color='red',size=8)))
    fig.update_layout(title='REJECTED: '+str(error),scene=dict(xaxis_title='X mm',yaxis_title='Y mm',zaxis_title='Tip Z mm',aspectmode='data'))
    fig.write_html(Path(run)/'previews'/'collision.html',include_plotlyjs=True,auto_open=False)
