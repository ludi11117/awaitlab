"""Analyze an editor buffer from stdin; never open/import the target file."""
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent/'engine'))
from awaitlab import __version__
from awaitlab.code_audit import SuppressionError,audit_source,source_lines


def analyze(request):
    source=request['text'];name=request['filename'];lines=source_lines(source)
    try:
        findings,patched=audit_source(source,name)
        active=[item for item in findings if 'suppression_reason' not in item]
        for item in active:
            line=lines[item['line']-1].rstrip('\r\n')
            prefix=line.encode('utf-8')[:item['column']-1].decode('utf-8')
            item['character']=len(prefix.encode('utf-16-le'))//2
            item['endCharacter']=len(line.encode('utf-16-le'))//2
        return {'version':__version__,'findings':active,'patched':patched,'errors':[]}
    except (SyntaxError,SuppressionError,UnicodeError) as error:
        line=max(0,(getattr(error,'lineno',None) or 1)-1)
        return {'version':__version__,'findings':[],'patched':source,
            'errors':[{'line':line,'message':str(error)}]}


if __name__=='__main__':
    request=json.loads(sys.stdin.buffer.read().decode('utf-8'))
    sys.stdout.buffer.write((json.dumps(analyze(request),ensure_ascii=False)+'\n').encode('utf-8'))
