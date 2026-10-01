# Paste this entire file into a new Colab cell, then run it.
# Repairs/retries only the isolated package installation; no model is loaded.
from pathlib import Path
import platform
import shutil
import subprocess
import sys

WORK = Path('/content/NeoHuman_ADA256_code')
assert Path('/content').is_dir(), 'Run this cell in your hosted Google Colab runtime.'
assert (3, 10) <= sys.version_info[:2] <= (3, 13), 'The pinned packages support Python 3.10–3.13.'
WORK.mkdir(parents=True, exist_ok=True)
ENV = WORK / '.venv'
PYTHON = ENV / 'bin/python'
INSTALL_LOG = WORK / 'installation.log'


def install_command(argv):
    """Expose pip stderr in the notebook AND retain it in a local log."""
    tail = []
    with INSTALL_LOG.open('a', encoding='utf-8') as log:
        heading = '\nRUN: ' + ' '.join(map(str, argv)) + '\n'
        print(heading, flush=True)
        log.write(heading)
        with subprocess.Popen(list(map(str, argv)), stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, bufsize=1) as process:
            for line in process.stdout:
                print(line, end='', flush=True)
                log.write(line)
                log.flush()
                tail.append(line.rstrip())
                tail = tail[-30:]
            result = process.wait()
    if result:
        raise RuntimeError(f'Installation command failed (exit {result}). '
                           f'Full output: {INSTALL_LOG}\nLast output:\n' + '\n'.join(tail))


print('Notebook Python:', sys.version)
print('Platform:', platform.platform(), '| machine:', platform.machine())
print(f'Free runtime disk: {shutil.disk_usage(WORK).free / 1024**3:.1f} GiB')
if not PYTHON.exists():
    install_command([sys.executable, '-m', 'venv', ENV])
install_command([PYTHON, '-c', 'import sys; print("Isolated Python:", sys.version)'])
install_command([PYTHON, '-m', 'ensurepip', '--upgrade'])
install_command([PYTHON, '-m', 'pip', 'install', '--upgrade', '--no-cache-dir',
                 '--index-url', 'https://pypi.org/simple', 'pip'])
install_command([PYTHON, '-m', 'pip', 'install', '--no-cache-dir', '--progress-bar', 'off',
                 '--timeout', '120', '--retries', '3',
                 '--index-url', 'https://download.pytorch.org/whl/cu128', 'torch==2.7.1'])
install_command([PYTHON, '-m', 'pip', 'install', '--no-cache-dir', '--progress-bar', 'off',
                 '--index-url', 'https://pypi.org/simple',
                 'numpy==2.2.6', 'Pillow==11.2.1', 'scipy==1.15.3', 'click==8.2.1',
                 'requests==2.32.4', 'tqdm==4.67.1', 'psutil==7.0.0', 'ninja==1.11.1.4'])
install_command([PYTHON, '-m', 'pip', 'check'])
print('Package installation complete. Rerun notebook step 3 to fetch source/weights, then continue to step 4.')
