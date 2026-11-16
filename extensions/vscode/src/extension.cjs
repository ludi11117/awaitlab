const vscode=require('vscode');
const {execFile}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path');

function activate(context){
 const diagnostics=vscode.languages.createDiagnosticCollection('AwaitLab');
 const output=vscode.window.createOutputChannel('AwaitLab');
 const status=vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left,30);
 const states=new Map(),pending=new Map(),timers=new Map(),previews=new Map(),failures=new Set();
 let sequence=0,disposed=false;
 const config=uri=>vscode.workspace.getConfiguration('awaitlab',uri);
 const supported=doc=>doc.languageId==='python'&&['file','untitled'].includes(doc.uri.scheme);
 const fullRange=doc=>new vscode.Range(0,0,doc.lineCount-1,doc.lineAt(doc.lineCount-1).text.length);
 function updateStatus(){
  const doc=vscode.window.activeTextEditor?.document;
  if(!doc||(!supported(doc)&&doc.uri.scheme!=='awaitlab-preview')){status.hide();return;}
  status.show();status.command='awaitlab.audit';
  if(doc.uri.scheme==='awaitlab-preview'){status.text='$(diff) AwaitLab · 简化预览';status.command='awaitlab.apply';status.tooltip='确认差异后应用；可用 Ctrl+Z 撤销。';return;}
  if(!config(doc.uri).get('enabled')){status.text='$(circle-slash) AwaitLab · 已关闭';return;}
  const key=doc.uri.toString(),state=states.get(key);
  if(failures.has(key)){status.text='$(error) AwaitLab · 运行失败';status.tooltip='点击检查 Python 路径，或运行 AwaitLab: 查看运行日志。';return;}
  status.text=pending.has(key)?'$(sync~spin) AwaitLab':`$(shield) AwaitLab${state?' · '+state.findings.length+' 处':''}`;
  status.tooltip='审查当前 Python 文件；路径冗余提供简化，宽泛异常仅供人工复核。';
 }
 function cancel(key){
  clearTimeout(timers.get(key));timers.delete(key);
  const job=pending.get(key);pending.delete(key);if(job)job.child.kill();
 }
 async function audit(doc,manual=false){
  if(disposed||!supported(doc)||!config(doc.uri).get('enabled'))return;
  const key=doc.uri.toString();cancel(key);
  const text=doc.getText(),version=doc.version,job={};
  const promise=new Promise((resolve,reject)=>{
   job.child=execFile(config(doc.uri).get('pythonPath'),['-I','-S','-B','-u',context.asAbsolutePath('bridge.py')],
    {encoding:'utf8',windowsHide:true,timeout:15000,maxBuffer:16*1024*1024},(error,stdout,stderr)=>{
     if(error){reject(new Error(stderr.trim()||error.message));return;}
     try{resolve(JSON.parse(stdout));}catch(error){reject(error);}
    });
   // Process startup errors also close stdin; execFile's callback reports the failure.
   job.child.stdin.on('error',()=>{});
   job.child.stdin.end(JSON.stringify({text,filename:doc.uri.fsPath||'untitled.py'}));
  });
  pending.set(key,job);updateStatus();
  try{
   const result=await promise;
   if(disposed||pending.get(key)!==job||doc.isClosed||doc.version!==version)return;
   failures.delete(key);
   const state={...result,uri:key,text,documentVersion:version,id:++sequence};states.set(key,state);
   const items=result.findings.map(item=>{
    const range=new vscode.Range(item.line-1,item.character,item.line-1,item.endCharacter);
    const diagnostic=new vscode.Diagnostic(range,`${item.message}\n依据：${item.evidence}\n${item.patch_note||item.suggestion}`,
      item.confidence==='path_proven'?vscode.DiagnosticSeverity.Warning:vscode.DiagnosticSeverity.Information);
    diagnostic.source='AwaitLab';diagnostic.code=item.rule;
    diagnostic.relatedInformation=(item.related_conditions||[]).flatMap(row=>row.lines.map(line=>new vscode.DiagnosticRelatedInformation(
      new vscode.Location(doc.uri,new vscode.Position(line-1,0)),`前置条件：${row.name} is ${row.identity?'':'not '}${row.singleton}`)));
    return diagnostic;
   });
   items.push(...result.errors.map(error=>new vscode.Diagnostic(new vscode.Range(error.line,0,error.line,1),error.message,vscode.DiagnosticSeverity.Error)));
   diagnostics.set(doc.uri,items);return state;
  }catch(error){
   if(pending.get(key)!==job||disposed)return;
   failures.add(key);states.delete(key);diagnostics.delete(doc.uri);output.appendLine(`${doc.uri.toString()}: ${error.message}`);
   if(manual){const action=await vscode.window.showErrorMessage('AwaitLab 无法运行。请确认 Python 3.10+ 已安装，并检查解释器路径。','设置 Python','查看日志');
    if(action==='设置 Python')vscode.commands.executeCommand('workbench.action.openSettings','awaitlab.pythonPath');
    if(action==='查看日志')output.show();}
  }finally{if(pending.get(key)===job)pending.delete(key);updateStatus();}
 }
 function schedule(doc){
  if(!supported(doc))return;
  const key=doc.uri.toString();cancel(key);states.delete(key);failures.delete(key);diagnostics.delete(doc.uri);
  if(config(doc.uri).get('enabled'))timers.set(key,setTimeout(()=>{timers.delete(key);void audit(doc);},400));
  updateStatus();
 }
 async function getState(arg){
  if(arg?.uri){const state=states.get(arg.uri);return state?.documentVersion===arg.version?state:undefined;}
  const doc=vscode.window.activeTextEditor?.document;if(!doc)return;
  if(doc.uri.scheme==='awaitlab-preview')return previews.get(doc.uri.toString());
  return states.get(doc.uri.toString())||await audit(doc,true);
 }
 async function preview(arg){
  const state=await getState(arg);if(!state||state.patched===state.text)return;
  const original=vscode.Uri.parse(state.uri);
  const uri=vscode.Uri.from({scheme:'awaitlab-preview',path:original.path||'/简化预览.py',query:String(state.id)});
  previews.set(uri.toString(),state);
  await vscode.commands.executeCommand('vscode.diff',original,uri,'AwaitLab · 原代码 ↔ 建议简化');
 }
 async function apply(arg){
  const state=await getState(arg);if(!state||state.patched===state.text)return false;
  const doc=await vscode.workspace.openTextDocument(vscode.Uri.parse(state.uri));
  if(doc.version!==state.documentVersion||doc.getText()!==state.text){
   void vscode.window.showWarningMessage('代码已变化，请重新审查并预览。');return false;
  }
  const edit=new vscode.WorkspaceEdit();edit.replace(doc.uri,fullRange(doc),state.patched);
  const applied=await vscode.workspace.applyEdit(edit);
  if(applied){await vscode.window.showTextDocument(doc);void audit(doc);}
  return applied;
 }
 context.subscriptions.push(diagnostics,output,status,
  vscode.workspace.registerTextDocumentContentProvider('awaitlab-preview',{provideTextDocumentContent:uri=>previews.get(uri.toString())?.patched||''}),
  vscode.commands.registerCommand('awaitlab.audit',()=>{const doc=vscode.window.activeTextEditor?.document;return doc&&audit(doc,true);}),
  vscode.commands.registerCommand('awaitlab.preview',preview),vscode.commands.registerCommand('awaitlab.apply',apply),
  vscode.commands.registerCommand('awaitlab.log',()=>output.show()),
  vscode.commands.registerCommand('awaitlab.demo',async()=>{
   const content=fs.readFileSync(context.asAbsolutePath('engine/demo.py'),'utf8');
   const doc=await vscode.workspace.openTextDocument({language:'python',content});await vscode.window.showTextDocument(doc);await audit(doc,true);
  }),
  vscode.languages.registerCodeActionsProvider({language:'python',scheme:'file'}, {provideCodeActions}, {providedCodeActionKinds:[vscode.CodeActionKind.QuickFix]}),
  vscode.languages.registerCodeActionsProvider({language:'python',scheme:'untitled'}, {provideCodeActions}, {providedCodeActionKinds:[vscode.CodeActionKind.QuickFix]}),
  vscode.workspace.onDidOpenTextDocument(schedule),vscode.workspace.onDidChangeTextDocument(event=>schedule(event.document)),
  vscode.workspace.onDidCloseTextDocument(doc=>{const key=doc.uri.toString();cancel(key);states.delete(key);previews.delete(key);diagnostics.delete(doc.uri);}),
  vscode.window.onDidChangeActiveTextEditor(updateStatus),
  vscode.workspace.onDidChangeConfiguration(event=>{if(event.affectsConfiguration('awaitlab'))vscode.workspace.textDocuments.forEach(schedule);}),
  {dispose(){disposed=true;for(const key of new Set([...pending.keys(),...timers.keys()]))cancel(key);previews.clear();states.clear();}}
 );
 function provideCodeActions(doc,range,context){
  const state=states.get(doc.uri.toString());
  if(!state||state.documentVersion!==doc.version||state.patched===state.text)return [];
  if(!context.diagnostics.some(item=>item.source==='AwaitLab'&&item.code==='ALD001'))return [];
  const count=state.findings.filter(item=>item.patch_available).length;
  const action=new vscode.CodeAction(`AwaitLab：预览本文件 ${count} 处可生成的简化`,vscode.CodeActionKind.QuickFix);
  action.command={command:'awaitlab.preview',title:action.title,arguments:[{uri:state.uri,version:state.documentVersion}]};
  return [action];
 }
 vscode.workspace.textDocuments.forEach(schedule);updateStatus();
 return {audit,preview,apply};
}
module.exports={activate};
