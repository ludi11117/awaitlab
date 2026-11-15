"""Small, local Python audit: path facts first, review-only heuristics second."""
import ast
import difflib
from fnmatch import fnmatchcase
import io
import json
import os
from pathlib import Path
import re
import tokenize
from . import __version__


SKIP_DIRS={'.git','.venv','venv','__pycache__','node_modules','build','dist','.mypy_cache','.pytest_cache'}
RULES={'ALD001','ALD002'}
SOURCE_LINE=re.compile(r'[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+$')


def source_lines(source):
    """Physical Python lines; Unicode separators and form feeds remain content."""
    return SOURCE_LINE.findall(source)


class SuppressionError(ValueError):
    """A source-level ignore directive is invalid, so the scan is incomplete."""


def read_suppressions(comments):
    result={}
    for line,comment in comments.items():
        if not re.match(r'#\s*awaitlab:',comment):continue
        match=re.fullmatch(r'#\s*awaitlab:\s*ignore\[([A-Z0-9, ]+)\]\s*--\s*(\S.*)',comment)
        if not match:raise SuppressionError(f'第 {line} 行忽略说明无效；使用 # awaitlab: ignore[ALD002] -- 原因')
        rules={rule.strip() for rule in match[1].split(',')}
        if not rules<=RULES:raise SuppressionError(f'第 {line} 行含未知规则：{", ".join(sorted(rules-RULES))}')
        result[line]=(rules,match[2])
    return result


def identity_test(node):
    if not (isinstance(node,ast.Compare) and len(node.ops)==1 and isinstance(node.ops[0],(ast.Is,ast.IsNot))):return
    left,right=node.left,node.comparators[0]
    if isinstance(left,ast.Constant):left,right=right,left
    if (isinstance(left,ast.Name) and isinstance(right,ast.Constant) and
            (right.value is None or type(right.value) is bool)):
        return (left.id,repr(right.value)),isinstance(node.ops[0],ast.Is)


def merge_paths(paths):
    paths=[path for path in paths if path is not None]
    if not paths:return None
    result=dict(paths[0])
    for path in paths[1:]:
        result={key:(truth,origins|path[key][1]) for key,(truth,origins) in result.items()
                if key in path and path[key][0]==truth}
    return result


def supported_condition(node,locals_):
    test=identity_test(node)
    if test:return test[0][0] in locals_
    if isinstance(node,ast.UnaryOp) and isinstance(node.op,ast.Not):return supported_condition(node.operand,locals_)
    return isinstance(node,ast.BoolOp) and all(supported_condition(value,locals_) for value in node.values)


def split_condition(node,facts):
    """Return facts on true/false short-circuit paths; None means unreachable."""
    test=identity_test(node)
    if test:
        key,wants_identity=test
        if key in facts:
            return (dict(facts),None) if facts[key][0]==wants_identity else (None,dict(facts))
        def branch(identity):
            result={**facts,key:(identity,frozenset({node.lineno}))}
            if identity:
                for other in ('None','True','False'):
                    if other!=key[1]:result[(key[0],other)]=(False,frozenset({node.lineno}))
            return result
        positive,negative=branch(True),branch(False)
        return (positive,negative) if wants_identity else (negative,positive)
    if isinstance(node,ast.UnaryOp):
        positive,negative=split_condition(node.operand,facts)
        return negative,positive
    current=dict(facts);exits=[]
    for value in node.values:
        if current is None:break
        positive,negative=split_condition(value,current)
        continuing,finished=(positive,negative) if isinstance(node.op,ast.And) else (negative,positive)
        exits.append(finished);current=continuing
    return (current,merge_paths(exits)) if isinstance(node.op,ast.And) else (merge_paths(exits),current)


def local_names(function):
    """Names owned by this function; never infer facts about globals/free names."""
    names={arg.arg for arg in function.args.posonlyargs+function.args.args+function.args.kwonlyargs}
    for arg in (function.args.vararg,function.args.kwarg):
        if arg:names.add(arg.arg)
    excluded=set()
    def visit(node):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.Lambda,
                            ast.ListComp,ast.SetComp,ast.DictComp,ast.GeneratorExp)):return
        if isinstance(node,ast.Name) and isinstance(node.ctx,ast.Store):names.add(node.id)
        if isinstance(node,(ast.Global,ast.Nonlocal)):excluded.update(node.names)
        for child in ast.iter_child_nodes(node):visit(child)
    for statement in function.body:visit(statement)
    return names-excluded


def scope_docstrings(tree):
    result=[]
    def visit(node):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            result.append((type(node).__name__,node.name,ast.get_docstring(node,clean=False)))
        for child in ast.iter_child_nodes(node):visit(child)
    visit(tree)
    return result


def has_scope_declarations(statements):
    return any(isinstance(child,(ast.Yield,ast.YieldFrom,ast.Global,ast.Nonlocal,
        ast.Import,ast.ImportFrom,ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.ExceptHandler,ast.Match)) or
        isinstance(child,ast.Name) and isinstance(child.ctx,(ast.Store,ast.Del))
        for statement in statements for child in ast.walk(statement))


def apply_edits(lines,edits):
    patched=lines[:]
    for start,end,replacement,_ in reversed(edits):patched[start:end]=replacement
    return ''.join(patched)


def patch_error(source,filename,docstrings):
    try:
        tree=ast.parse(source,filename=filename)
        compile(tree,filename,'exec')
    except SyntaxError:
        return '该处修改不能通过语法检查（可能留下空代码块），需人工调整。'
    if scope_docstrings(tree)!=docstrings:
        return '修改会改变函数或类的文档字符串，需人工调整。'


class FlowAudit:
    def __init__(self,source,filename):
        self.source=source;self.lines=source_lines(source);self.filename=filename;self.findings=[];self.edits=[]
        self.encoded_lines=[line.encode('utf-8') for line in self.lines]
        tokens=list(tokenize.generate_tokens(io.StringIO(source,newline=None).readline))
        self.comments={token.start[0]:token.string for token in tokens if token.type==tokenize.COMMENT}
        self.suppressions=read_suppressions(self.comments)
        self.else_headers=[token.start for token in tokens if token.type==tokenize.NAME and token.string=='else']

    def segment(self,node):
        start=node.lineno-1;end=node.end_lineno-1
        if start==end:return self.encoded_lines[start][node.col_offset:node.end_col_offset].decode('utf-8')
        return (self.encoded_lines[start][node.col_offset:].decode('utf-8')+
            ''.join(self.lines[start+1:end])+self.encoded_lines[end][:node.end_col_offset].decode('utf-8'))

    def finding(self,node,rule,confidence,message,evidence,suggestion):
        item={'path':self.filename,'line':node.lineno,'column':node.col_offset+1,
              'rule':rule,'confidence':confidence,'message':message,'evidence':evidence,
              'suggestion':suggestion,'code':self.segment(node),'patch_available':False}
        self.findings.append(item)
        if node.lineno in self.suppressions:
            rules,reason=self.suppressions[node.lineno]
            if rule in rules:item['suppression_reason']=reason
        return item

    def block(self,statements,facts,locals_,parameters):
        facts=dict(facts)
        for node in statements:
            if isinstance(node,ast.If):
                if supported_condition(node.test,locals_):
                    positive,negative=split_condition(node.test,facts)
                    names={child.id for child in ast.walk(node.test) if isinstance(child,ast.Name)}
                    bound=parameters|{name for name,_ in facts}
                    if (positive is None or negative is None) and names<=bound:
                        truth=negative is None
                        tested_keys={test[0] for child in ast.walk(node.test) if (test:=identity_test(child))}
                        related=[{'name':name,'singleton':singleton,'identity':identity,'lines':sorted(origins)}
                            for (name,singleton),(identity,origins) in sorted(facts.items()) if (name,singleton) in tested_keys]
                        details='；'.join(f'第 {"/".join(map(str,row["lines"]))} 行：{row["name"]} is {"" if row["identity"] else "not "}{row["singleton"]}' for row in related)
                        item=self.finding(node,'ALD001','path_proven',
                            f'{self.segment(node.test)} 在当前路径恒为 {truth}',
                            (details+'。' if details else '条件自身的单例身份比较与短路路径确定结果。')+'赋值、调用、await等语句会清除已有路径事实。',
                            '移除重复条件，保留实际可达分支。')
                        item['related_conditions']=related
                        self.propose(node,truth,item)
                        selected=node.body if truth else node.orelse
                        facts=self.block(selected,positive if truth else negative,locals_,parameters)
                        if facts is None:return None
                        continue
                    left=self.block(node.body,positive,locals_,parameters) if positive is not None else None
                    right=self.block(node.orelse,negative,locals_,parameters) if negative is not None else None
                    facts=merge_paths((left,right))
                    if facts is None:return None
                    continue
                # Unknown conditions may execute user code. Discard incoming facts.
                self.block(node.body,{},locals_,parameters);self.block(node.orelse,{},locals_,parameters)
                facts={}
            elif isinstance(node,(ast.Return,ast.Raise)):
                return None
            elif not isinstance(node,ast.Pass):
                # Assignment, call, await, loops and context managers are barriers.
                facts={}
                if isinstance(node,(ast.For,ast.AsyncFor,ast.While,ast.With,ast.AsyncWith,ast.Try)):
                    self.block(node.body,{},locals_,parameters)
                    if hasattr(node,'orelse'):self.block(node.orelse,{},locals_,parameters)
                    if isinstance(node,ast.Try):
                        for handler in node.handlers:self.block(handler.body,{},locals_,parameters)
                        self.block(node.finalbody,{},locals_,parameters)
        return facts

    def propose(self,node,truth,item):
        if 'suppression_reason' in item:return
        lines=self.lines
        start=node.lineno-1;end=node.end_lineno
        header=lines[start];header_indent=header[:len(header)-len(header.lstrip())]
        if (node.body[0].lineno==node.lineno or not header.lstrip().startswith('if ') or
                not header.split('#',1)[0].rstrip().endswith(':')):
            item['patch_note']='elif、多行条件或行内语句仅报告，不生成补丁。';return
        if '\t' in header_indent:
            item['patch_note']='含制表符缩进，不生成补丁。';return
        if any(character!=' ' for character in header_indent):
            item['patch_note']='含非空格缩进，不生成补丁。';return
        # AST ranges exclude trailing comments; include only comments still indented in this branch.
        cursor=end
        while cursor<len(lines):
            line=lines[cursor]
            if not line.strip():cursor+=1;continue
            indent=line[:len(line)-len(line.lstrip())]
            if cursor+1 in self.comments and line.lstrip().startswith('#') and len(indent)>len(header_indent):
                cursor+=1;end=cursor;continue
            break
        else_line=None
        if node.orelse:
            else_line=next((line-1 for line,column in self.else_headers
                if node.body[-1].end_lineno<line<=node.orelse[0].lineno and column==node.col_offset),None)
            if else_line is None or node.orelse[0].lineno==else_line+1:
                item['patch_note']='elif链或行内else仅报告，不生成补丁。';return
        kept=node.body if truth else node.orelse
        discarded=node.orelse if truth else node.body
        if has_scope_declarations(discarded):
            item['patch_note']='死分支含绑定或生成器声明，删除可能改变函数作用域/类型。';return
        if truth:
            dead_start=else_line+1 if else_line is not None else end
            dead_end=end
        else:
            dead_start=start+1
            dead_end=else_line if else_line is not None else end
        if any(line+1 in self.comments for line in range(dead_start,dead_end)) or (
                truth and else_line is not None and else_line+1 in self.comments):
            item['patch_note']='不可达分支含注释，保留原文以便人工处理。';return
        replacement=[]
        for line in (start,else_line):
            if line is not None and line+1 in self.comments:
                replacement.append(header_indent+self.comments[line+1]+'\n')
        if kept:
            if any(isinstance(child,(ast.Constant,ast.JoinedStr)) and child.end_lineno>child.lineno
                    for statement in kept for child in ast.walk(statement)):
                item['patch_note']='分支含多行字符串，避免改变字符串内容。';return
            first=lines[kept[0].lineno-1]
            body_indent=first[:len(first)-len(first.lstrip())]
            if '\t' in body_indent:
                item['patch_note']='含制表符缩进，不生成补丁。';return
            if any(character!=' ' for character in body_indent):
                item['patch_note']='含非空格缩进，不生成补丁。';return
            kept_start,kept_end=(start+1,else_line if else_line is not None else end) if truth else (else_line+1,end)
            replacement.extend(header_indent+line[len(body_indent):] if line.startswith(body_indent) else line
                for line in lines[kept_start:kept_end])
        item['code']=''.join(lines[start:end]).rstrip('\r\n')
        self.edits.append((start,end,replacement,item))


def audit_source(source,filename='<string>'):
    tree=ast.parse(source,filename=filename)
    compile(tree,filename,'exec')
    audit=FlowAudit(source,filename)
    for node in ast.walk(tree):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            parameters={arg.arg for arg in node.args.posonlyargs+node.args.args+node.args.kwonlyargs}
            for arg in (node.args.vararg,node.args.kwarg):
                if arg:parameters.add(arg.arg)
            audit.block(node.body,{},local_names(node),parameters)
        elif isinstance(node,ast.ExceptHandler):
            types=node.type.elts if isinstance(node.type,ast.Tuple) else [node.type]
            broad=node.type is None or any(isinstance(t,ast.Name) and t.id in ('Exception','BaseException') for t in types)
            swallowed=len(node.body)==1 and (isinstance(node.body[0],ast.Pass) or
                isinstance(node.body[0],ast.Return) and (node.body[0].value is None or isinstance(node.body[0].value,ast.Constant)))
            if broad and swallowed:
                audit.finding(node,'ALD002','needs_review','宽泛异常被静默忽略或转成固定结果',
                    audit.segment(node),
                    '核实是否为业务合同；可考虑捕获具体异常或向上传播。不会自动删除异常处理。')
    ordered=sorted(audit.edits,key=lambda e:(e[0],-e[1]))
    if not ordered:return sorted(audit.findings,key=lambda f:(f['line'],f['column'],f['rule'])),source
    lines=audit.lines;docstrings=scope_docstrings(tree)
    batch=[];covered=[]
    for edit in ordered:
        if batch and edit[0]<batch[-1][1]:covered.append(edit)
        else:batch.append(edit)
    combined=apply_edits(lines,batch)
    if patch_error(combined,filename,docstrings) is None:
        for edit in batch:edit[3]['patch_available']=True
        for edit in covered:edit[3]['patch_note']='与外层修改重叠，先复核外层补丁。'
        return sorted(audit.findings,key=lambda f:(f['line'],f['column'],f['rule'])),combined
    # Batch rejected: keep per-edit checks so an invalid edit cannot block other fixes.
    accepted=[]
    for edit in ordered:
        if accepted and edit[0]<accepted[-1][1]:
            edit[3]['patch_note']='与外层修改重叠，先复核外层补丁。';continue
        candidate=apply_edits(lines,accepted+[edit])
        reason=patch_error(candidate,filename,docstrings)
        if reason:
            edit[3]['patch_note']=reason;continue
        edit[3]['patch_available']=True;accepted.append(edit)
    result=apply_edits(lines,accepted)
    return sorted(audit.findings,key=lambda f:(f['line'],f['column'],f['rule'])),result


def audit_path(target,*,exclude=()):
    target=Path(target).resolve()
    if not target.exists():raise ValueError(f'路径不存在：{target}')
    if target.is_file() and target.suffix!='.py':raise ValueError('扫描目标必须是 .py 文件或目录')
    cwd=Path.cwd().resolve()
    root=cwd if target.is_relative_to(cwd) else target if target.is_dir() else target.parent
    scan_root=target if target.is_dir() else target.parent
    patterns=tuple(pattern.replace('\\','/') for pattern in exclude)
    files=[];errors=[];excluded=[]
    def is_excluded(path,is_dir=False):
        name=path.relative_to(scan_root).as_posix()+('/' if is_dir else '')
        if any(fnmatchcase(name,pattern) for pattern in patterns):
            excluded.append(name);return True
        return False
    if target.is_file():
        if not is_excluded(target):files=[target]
    else:
        def walk_error(error):errors.append({'path':str(error.filename),'error':str(error)})
        for directory,dirs,names in os.walk(target,followlinks=False,onerror=walk_error):
            dirs[:]=sorted(name for name in dirs if name not in SKIP_DIRS and not (Path(directory)/name).is_symlink()
                and not is_excluded(Path(directory)/name,is_dir=True))
            files.extend(Path(directory)/name for name in sorted(names) if name.endswith('.py')
                and not (Path(directory)/name).is_symlink() and not is_excluded(Path(directory)/name))
    findings=[];ignored=[];patches=[]
    for path in files:
        name=path.relative_to(root).as_posix()
        try:
            with tokenize.open(path) as stream:source=stream.read();encoding=stream.encoding
            found,patched=audit_source(source,name)
            if encoding.lower().replace('_','-')!='utf-8':
                patched=source
                for item in found:
                    item['patch_available']=False;item['patch_note']='非普通UTF-8编码，首版仅报告。'
            if patched!=source:
                patches.extend(line if line.endswith('\n') else line+'\n\\ No newline at end of file\n'
                    for line in difflib.unified_diff(source_lines(source),source_lines(patched),
                        fromfile='a/'+name,tofile='b/'+name))
            findings.extend(item for item in found if 'suppression_reason' not in item)
            ignored.extend(item for item in found if 'suppression_reason' in item)
        except (OSError,SyntaxError,UnicodeError,SuppressionError) as error:
            errors.append({'path':name,'error':str(error)})
    return {'kind':'defensive_code_audit','library_version':__version__,'patch_root':str(root),'scan_root':str(scan_root),
        'files_scanned':len(files),'exclude_patterns':list(patterns),'excluded_paths':sorted(excluded),
        'findings':findings,'ignored_findings':ignored,'errors':errors,'patch':''.join(patches),
        'scope':'Python local-name None/True/False identity guards with and/or/not short-circuit paths; facts stop at other statements. No imports/execution, no cross-function proof. Broad silent exceptions require review.'}


def run_cli(target,output=None,patch=None,check=False,*,html=None,exclude=()):
    try:
        if output and Path(output).suffix!='.json':raise ValueError('--output 必须以 .json 结尾')
        if patch and Path(patch).suffix!='.patch':raise ValueError('--patch 必须以 .patch 结尾')
        if html and Path(html).suffix!='.html':raise ValueError('--html 必须以 .html 结尾')
        report=audit_path(target,exclude=exclude)
        for item in report['findings']:
            print(f'{item["path"]}:{item["line"]}:{item["column"]} {item["rule"]} [{item["confidence"]}] {item["message"]}')
            print(f'  依据：{item["evidence"]}\n  建议：{item["suggestion"]}')
        for error in report['errors']:print(f'{error["path"]}: 扫描失败：{error["error"]}')
        for item in report['ignored_findings']:
            print(f'{item["path"]}:{item["line"]} {item["rule"]} 已注明忽略：{item["suppression_reason"]}')
        for destination,text in ((output,json.dumps(report,ensure_ascii=False,indent=2)+'\n'),(patch,report['patch'])):
            if destination:
                path=Path(destination);path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(text,encoding='utf-8',newline='\n')
        if html:
            from .code_audit_report import write_audit_report
            print(f'离线报告：{write_audit_report(report,html).resolve()}')
        proven=sum(item['confidence']=='path_proven' for item in report['findings'])
        review=len(report['findings'])-proven
        print(f'扫描 {report["files_scanned"]} 个文件；路径冗余 {proven} 处；人工复核 {review} 处；'
            f'已注明忽略 {len(report["ignored_findings"])} 处；排除路径 {len(report["excluded_paths"])} 个；错误 {len(report["errors"])} 处。')
        if patch:print(f'补丁：{Path(patch).resolve()}；相对目录：{report["patch_root"]}；未修改目标源码。')
        return 2 if report['errors'] else int(check and proven>0)
    except (OSError,ValueError) as error:
        print(f'AwaitLab audit: {error}')
        return 2
