from pathlib import Path
import plistlib
import platform
import shutil
import subprocess
root=Path(__file__).resolve().parent.parent
app=root/'native/Blackboard Git.app'
mac=app/'Contents/MacOS'; mac.mkdir(parents=True,exist_ok=True)
resources=app/'Contents/Resources'; resources.mkdir(parents=True,exist_ok=True)
shutil.copy2(root/'login-provider.js',resources/'login-provider.js')
(app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'local.blackboard.git','CFBundleName':'Blackboard Git','CFBundleExecutable':'BlackboardFetcher','CFBundlePackageType':'APPL','NSHighResolutionCapable':True,'CFBundleVersion':'1','LSMinimumSystemVersion':'12.0'}))
subprocess.run(['xcrun','swiftc',str(root/'native/NativeFetcher.swift'),'-target',platform.machine()+'-apple-macosx12.0','-o',str(mac/'BlackboardFetcher'),'-framework','Cocoa','-framework','WebKit'],check=True)
print(app)
