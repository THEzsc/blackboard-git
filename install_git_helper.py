"""Install a Git-for-Windows/POSIX launcher using the selected Python interpreter."""
import argparse
from pathlib import Path
import shlex
import subprocess
import sys


def install(root, bindir=None, python=None, replace=False, rewrite=True):
    root = Path(root).resolve()
    binary = Path(bindir or Path.home()/'.local/bin')/'git-remote-blackboard'
    binary.parent.mkdir(parents=True, exist_ok=True)
    interpreter = Path(python or sys.executable).absolute().as_posix()
    source = (root/'git-remote-blackboard').as_posix()
    launcher = '#!/bin/sh\n# Installed by blackboard-git\nexec ' + shlex.quote(interpreter) + ' -X utf8 ' + shlex.quote(source) + ' "$@"\n'
    if binary.exists() or binary.is_symlink():
        if binary.is_symlink() and binary.resolve() == root/'git-remote-blackboard':
            binary.unlink()
        elif binary.is_file() and binary.read_text(encoding='utf-8') == launcher:
            pass
        elif replace:
            binary.unlink()
        else:
            raise ValueError('A different helper exists at '+str(binary)+'. Use --replace-helper to replace it explicitly.')
    binary.write_text(launcher, encoding='utf-8', newline='\n')
    binary.chmod(0o755)
    if rewrite:
        key='url.blackboard::https://learn.intl.zju.edu.cn/.insteadOf'
        prefix='https://learn.intl.zju.edu.cn/'
        values=subprocess.run(['git','config','--global','--get-all',key],text=True,capture_output=True).stdout.splitlines()
        if prefix not in values:
            subprocess.run(['git','config','--global','--add',key,prefix],check=True)
    return binary


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replace-helper',action='store_true')
    args=parser.parse_args()
    print('Installed '+str(install(Path(__file__).parent,replace=args.replace_helper)))
    print('Add ~/.local/bin to PATH. Git URLs on https://learn.intl.zju.edu.cn/ use this helper.')
