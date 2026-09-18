"""Platform-aware local installer. No browser download unless a later pull needs it."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import venv
from platform_support import backend
from install_git_helper import install


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replace-helper',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    selected=backend()
    environment=root/'.venv'
    if not environment.exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    python=environment/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if selected=='chromium':
        subprocess.run([str(python),'-m','pip','install','-r',str(root/'requirements-chromium.txt')],check=True)
    else:
        subprocess.run([str(python),str(root/'native/build.py')],check=True)
    # Future backend switching can install the Chromium dependency in this same venv.
    launcher=install(root,python=python,replace=args.replace_helper)
    print('Backend: '+selected+' (auto-detected unless BLACKBOARD_BACKEND is set)')
    print('Installed: '+str(launcher))
    print('No browser was downloaded during setup.')
    if os.name=='nt':
        print('PowerShell, current session: $env:Path = "$HOME\\.local\\bin;" + $env:Path')
        print('Also add this folder to your user PATH in Windows Environment Variables.')
    else:
        print('Add to your shell profile: export PATH="$HOME/.local/bin:$PATH"')


if __name__=='__main__':
    main()
