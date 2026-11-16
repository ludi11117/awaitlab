const path=require('node:path'),fs=require('node:fs');
const tools=process.env.AWAITLAB_VSCODE_TOOLS||'D:/CodexWork/cache/awaitlab-vscode-tools/node_modules';
const {runTests}=require(path.join(tools,'@vscode/test-electron'));
const root=path.resolve(__dirname,'..');
const folder='D:/CodexWork/temp/awaitlab/vscode-test';fs.mkdirSync(folder,{recursive:true});
runTests({
 vscodeExecutablePath:process.env.AWAITLAB_CODE_EXE||'C:/Users/余梓岳/AppData/Local/Programs/Microsoft VS Code/Code.exe',
 extensionDevelopmentPath:process.env.AWAITLAB_EXTENSION_PATH||root,extensionTestsPath:path.join(__dirname,'run.cjs'),
 launchArgs:[folder,'--user-data-dir='+folder+'/user','--extensions-dir='+folder+'/extensions',
  '--disable-workspace-trust','--disable-extensions','--disable-gpu','--skip-welcome','--skip-release-notes',
  '--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows',
  ...(process.env.AWAITLAB_SCREENSHOT?['--remote-debugging-port=9539']:[])],
 extensionTestsEnv:{PYTHONDONTWRITEBYTECODE:'1',TEMP:'D:/CodexWork/temp/awaitlab',TMP:'D:/CodexWork/temp/awaitlab',
  AWAITLAB_SCREENSHOT:process.env.AWAITLAB_SCREENSHOT||''}
}).catch(error=>{console.error(error);process.exitCode=1;});
