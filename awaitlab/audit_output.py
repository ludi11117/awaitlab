"""Publish one complete audit artifact without truncating the previous one."""
import os
from pathlib import Path
import tempfile


def write_text_atomic(path,text):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    descriptor,temporary=tempfile.mkstemp(dir=path.parent,prefix='.'+path.name+'.',suffix='.tmp')
    try:
        with os.fdopen(descriptor,'w',encoding='utf-8',newline='\n') as stream:stream.write(text)
        os.replace(temporary,path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return path
