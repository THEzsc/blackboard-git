"""Install this local helper and route only this Blackboard host's Git URLs to it."""
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parent
binary=Path.home()/'.local/bin/git-remote-blackboard'
binary.parent.mkdir(parents=True,exist_ok=True)
if binary.exists() or binary.is_symlink():
    if binary.resolve()!=root/'git-remote-blackboard':raise SystemExit('Another helper already exists at '+str(binary))
else:binary.symlink_to(root/'git-remote-blackboard')
key='url.blackboard::https://learn.intl.zju.edu.cn/.insteadOf'
prefix='https://learn.intl.zju.edu.cn/'
values=subprocess.run(['git','config','--global','--get-all',key],text=True,capture_output=True).stdout.splitlines()
if prefix not in values:subprocess.run(['git','config','--global','--add',key,prefix],check=True)
print('Installed '+str(binary))
print('Git URLs on '+prefix+' now use the Blackboard helper. Other hosts are unchanged.')
