from pathlib import Path
import os
import sys
import nbformat
from nbclient import NotebookClient
from jupyter_client.kernelspec import KernelSpecManager

root=Path(__file__).resolve().parents[1]
os.environ['BIOPRINTER_OFFLINE_TEST']='1'
os.environ['JUPYTER_PLATFORM_DIRS']='1'
# Explicit kernel command: the invoking environment, not a user's unrelated default.
from jupyter_client import KernelManager
class LocalKernel(KernelManager):
    def format_kernel_cmd(self,extra_arguments=None):
        return [sys.executable,'-m','ipykernel_launcher','-f',self.connection_file,*(extra_arguments or [])]
path=root/'notebooks/image_to_syringe_pipeline.ipynb'
book=nbformat.read(path,as_version=4)
client=NotebookClient(book,timeout=300,resources={'metadata':{'path':str(root)}},kernel_manager_class=LocalKernel)
client.execute()
nbformat.write(book,path)
print(f'Fresh kernel executed {sum(c.cell_type=="code" for c in book.cells)} cells with external HTTP disabled; saved {path}')
