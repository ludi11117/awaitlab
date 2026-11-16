"""Bundle the existing stdlib auditor, without copying the experiment SDK."""
from pathlib import Path
import re
import shutil

folder=Path(__file__).resolve().parent;root=folder.parents[1]
engine=folder/'engine'/'awaitlab';engine.mkdir(parents=True,exist_ok=True)
version=re.search(r"__version__ = '([^']+)'",(root/'awaitlab/__init__.py').read_text(encoding='utf-8'))[1]
for name in ('code_audit.py','audit_output.py'):
    shutil.copyfile(root/'awaitlab'/name,engine/name)
(engine/'__init__.py').write_text(f"__version__ = {version!r}\n",encoding='utf-8',newline='\n')
shutil.copyfile(root/'examples/defensive_vscode_sample.py',folder/'engine'/'demo.py')
print(f'Bundled AwaitLab {version}: no runtime pip dependencies')
