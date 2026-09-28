from pathlib import Path
from PIL import Image,ImageDraw


def make_inputs(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    # Same 120px canvas and common 24mm scale; explicit partially overlapping silhouettes.
    image=Image.new('RGBA',(120,120),(255,255,255,0));d=ImageDraw.Draw(image)
    d.rectangle((15,15,100,100),fill='black');d.rectangle((38,38,77,77),fill=(255,255,255,0))
    image.save(folder/'image1_ring.png')
    image=Image.new('RGB',(120,120),'white');d=ImageDraw.Draw(image)
    d.polygon([(20,25),(40,25),(40,80),(105,80),(105,102),(20,102)],fill='black')
    image.save(folder/'image2_asymmetric_L.png')
    image=Image.new('RGB',(120,120),'white');d=ImageDraw.Draw(image)
    d.rectangle((10,50,110,70),fill='black');d.rectangle((85,12,108,32),fill='black')
    image.save(folder/'image10_bridge_island.png')
    (folder/'README.txt').write_text('Generated synthetic drawings. Natural order: ring, L, bridge + island. All share 120 x 120 canvas.\n',encoding='utf-8')
    return folder
