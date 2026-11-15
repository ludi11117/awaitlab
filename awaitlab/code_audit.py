"""Small, local Python audit: path facts first, review-only heuristics second."""
import ast
import difflib
import json
import os
from pathlib import Path
import tokenize


SKIP_DIRS={'.git','.venv','venv','__pycache__','node_modules','build','dist','.mypy_cache','.pytest_cache'}


def none_test(node):
    if (isinstance(node,ast.Compare) and len(node.ops)==1 and
            isinstance(node.left,ast.Name) and isinstance(node.comparators[0],ast.Constant) and
            node.comparators[0].value is None and isinstance(node.ops[0],(ast.Is,ast.IsNot))):
        return node.left.id,isinstance(node.ops[0],ast.Is)


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


class FlowAudit:
    def __init__(self,source,filename):
        self.source=source;self.filename=filename;self.findings=[];self.edits=[]

    def finding(self,node,rule,confidence,message,evidence,suggestion):
        item={'path':self.filename,'line':node.lineno,'column':node.col_offset+1,
              'rule':rule,'confidence':confidence,'message':message,'evidence':evidence,
              'suggestion':suggestion,'patch_available':False}
        self.findings.append(item)
        return item

    def block(self,statements,facts,locals_):
        facts=dict(facts)
        for node in statements:
            if isinstance(node,ast.If):
                test=none_test(node.test)
                if test and test[0] in locals_:
                    name,wants_none=test
                    if name in facts:
                        is_none,origin=facts[name];truth=is_none==wants_none
                        item=self.finding(node,'ALD001','path_proven',
                            f'{ast.get_source_segment(self.source,node.test)} 在当前路径恒为 {truth}',
                            f'第 {origin} 行条件确定 {name} {"is" if is_none else "is not"} None；中间没有跨越其他语句。',
                            '移除重复条件，保留实际可达分支。')
                        self.propose(node,truth,item)
                        selected=node.body if truth else node.orelse
                        facts=self.block(selected,facts,locals_)
                        if facts is None:return None
                        continue
                    positive={**facts,name:(wants_none,node.lineno)}
                    negative={**facts,name:(not wants_none,node.lineno)}
                    left=self.block(node.body,positive,locals_)
                    right=self.block(node.orelse,negative,locals_)
                    if left is None:facts=right
                    elif right is None:facts=left
                    else:facts={name:value for name,value in left.items() if name in right and right[name][0]==value[0]}
                    if facts is None:return None
                    continue
                # Unknown conditions may execute user code. Discard incoming facts.
                self.block(node.body,{},locals_);self.block(node.orelse,{},locals_)
                facts={}
            elif isinstance(node,(ast.Return,ast.Raise)):
                return None
            elif not isinstance(node,ast.Pass):
                # Assignment, call, await, loops and context managers are barriers.
                facts={}
                if isinstance(node,(ast.For,ast.AsyncFor,ast.While,ast.With,ast.AsyncWith,ast.Try)):
                    self.block(node.body,{},locals_)
                    if hasattr(node,'orelse'):self.block(node.orelse,{},locals_)
                    if isinstance(node,ast.Try):
                        for handler in node.handlers:self.block(handler.body,{},locals_)
                        self.block(node.finalbody,{},locals_)
        return facts

    def propose(self,node,truth,item):
        # Keep source formatting. Complex headers/else suites stay reviewable findings.
        lines=self.source.splitlines(keepends=True)
        if node.orelse or node.body[0].lineno==node.lineno or not lines[node.lineno-1].lstrip().startswith('if '):
            item['patch_note']='带 else/elif 或行内语句，首版仅报告，不生成补丁。';return
        if node.body[0].lineno!=node.lineno+1:
            item['patch_note']='多行条件或条件后的独立注释需要人工保留。';return
        start=node.lineno-1;end=node.end_lineno
        replacement=[]
        if not truth and any(isinstance(child,(ast.Yield,ast.YieldFrom,ast.Global,ast.Nonlocal,
                ast.Import,ast.ImportFrom,ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.ExceptHandler,ast.Match)) or
                isinstance(child,ast.Name) and isinstance(child.ctx,(ast.Store,ast.Del))
                for statement in node.body for child in ast.walk(statement)):
            item['patch_note']='死分支含绑定或生成器声明，删除可能改变函数作用域/类型。';return
        if truth:
            if any(isinstance(child,(ast.Constant,ast.JoinedStr)) and child.end_lineno>child.lineno
                    for statement in node.body for child in ast.walk(statement)):
                item['patch_note']='分支含多行字符串，避免改变字符串内容。';return
            header_indent=lines[start][:len(lines[start])-len(lines[start].lstrip())]
            body_indent=lines[start+1][:len(lines[start+1])-len(lines[start+1].lstrip())]
            if '\t' in body_indent:
                item['patch_note']='含制表符缩进，首版不生成补丁。';return
            replacement=[header_indent+line[len(body_indent):] if line.strip() else line for line in lines[start+1:end]]
        self.edits.append((start,end,replacement,item))


def audit_source(source,filename='<string>'):
    tree=ast.parse(source,filename=filename)
    compile(tree,filename,'exec')
    audit=FlowAudit(source,filename)
    for node in ast.walk(tree):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            audit.block(node.body,{},local_names(node))
        elif isinstance(node,ast.ExceptHandler):
            types=node.type.elts if isinstance(node.type,ast.Tuple) else [node.type]
            broad=node.type is None or any(isinstance(t,ast.Name) and t.id in ('Exception','BaseException') for t in types)
            swallowed=len(node.body)==1 and (isinstance(node.body[0],ast.Pass) or
                isinstance(node.body[0],ast.Return) and (node.body[0].value is None or isinstance(node.body[0].value,ast.Constant)))
            if broad and swallowed:
                audit.finding(node,'ALD002','needs_review','宽泛异常被静默忽略或转成固定结果',
                    ast.get_source_segment(source,node),
                    '核实是否为业务合同；可考虑捕获具体异常或向上传播。不会自动删除异常处理。')
    # Avoid overlapping edits; a later audit can simplify nested residual guards.
    accepted=[];end=-1
    for edit in sorted(audit.edits,key=lambda e:(e[0],-e[1])):
        if edit[0]<end:
            edit[3]['patch_note']='与外层修改重叠，先复核外层补丁。';continue
        accepted.append(edit);end=edit[1]
    lines=source.splitlines(keepends=True)
    patched=lines[:]
    for start,end,replacement,_ in reversed(accepted):patched[start:end]=replacement
    result=''.join(patched)
    try:compile(result,filename,'exec')
    except SyntaxError:
        for *_,item in accepted:item['patch_note']='修改会留下空代码块，需人工调整。'
        result=source
    else:
        for *_,item in accepted:item['patch_available']=True
    return sorted(audit.findings,key=lambda f:(f['line'],f['column'],f['rule'])),result


def audit_path(target):
    target=Path(target).resolve()
    if not target.exists():raise ValueError(f'路径不存在：{target}')
    if target.is_file() and target.suffix!='.py':raise ValueError('扫描目标必须是 .py 文件或目录')
    cwd=Path.cwd().resolve()
    root=cwd if target.is_relative_to(cwd) else target if target.is_dir() else target.parent
    files=[];errors=[]
    if target.is_file():files=[target]
    else:
        def walk_error(error):errors.append({'path':str(error.filename),'error':str(error)})
        for directory,dirs,names in os.walk(target,followlinks=False,onerror=walk_error):
            dirs[:]=sorted(name for name in dirs if name not in SKIP_DIRS and not (Path(directory)/name).is_symlink())
            files.extend(Path(directory)/name for name in sorted(names) if name.endswith('.py') and not (Path(directory)/name).is_symlink())
    findings=[];patches=[]
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
                    for line in difflib.unified_diff(source.splitlines(keepends=True),patched.splitlines(keepends=True),
                        fromfile='a/'+name,tofile='b/'+name))
            findings.extend(found)
        except (OSError,SyntaxError,UnicodeError) as error:
            errors.append({'path':name,'error':str(error)})
    return {'kind':'defensive_code_audit','patch_root':str(root),'files_scanned':len(files),
        'findings':findings,'errors':errors,'patch':''.join(patches),
        'scope':'Python local-name None identity guards; facts stop at other statements. No imports/execution, no cross-function proof. Broad silent exceptions require review.'}


def run_cli(target,output=None,patch=None,check=False):
    try:
        if output and Path(output).suffix!='.json':raise ValueError('--output 必须以 .json 结尾')
        if patch and Path(patch).suffix!='.patch':raise ValueError('--patch 必须以 .patch 结尾')
        report=audit_path(target)
        for item in report['findings']:
            print(f'{item["path"]}:{item["line"]}:{item["column"]} {item["rule"]} [{item["confidence"]}] {item["message"]}')
            print(f'  依据：{item["evidence"]}\n  建议：{item["suggestion"]}')
        for error in report['errors']:print(f'{error["path"]}: 扫描失败：{error["error"]}')
        for destination,text in ((output,json.dumps(report,ensure_ascii=False,indent=2)+'\n'),(patch,report['patch'])):
            if destination:
                path=Path(destination);path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(text,encoding='utf-8',newline='\n')
        proven=sum(item['confidence']=='path_proven' for item in report['findings'])
        review=len(report['findings'])-proven
        print(f'扫描 {report["files_scanned"]} 个文件；路径冗余 {proven} 处；人工复核 {review} 处；错误 {len(report["errors"])} 处。')
        if patch:print(f'补丁：{Path(patch).resolve()}；相对目录：{report["patch_root"]}；未修改目标源码。')
        return 2 if report['errors'] else int(check and proven>0)
    except (OSError,ValueError) as error:
        print(f'AwaitLab audit: {error}')
        return 2
