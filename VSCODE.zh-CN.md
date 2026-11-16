# 在 VS Code 中使用 AwaitLab

第一次直接双击项目根目录的 **Start-AwaitLab-VSCode.cmd**。启动器会安装本地VSIX，打开一个演示副本。需要本机已安装 VS Code 和 Python 3.10+；不用启动服务、不用配置API、不用pip安装AwaitLab。

## 实际操作

1. 打开的 `review_me.py` 有两处黄色提示和一处人工复核。稍等自动分析完成，也可以点编辑器右上角盾牌按钮。
2. 鼠标停在黄色波浪线上看原因，或按 **Ctrl+Shift+M** 打开“问题 / Problems”面板。相关位置可跳到前面的条件。
3. 把光标放在黄色提示处，按 **Ctrl+.**，优先选择 **AwaitLab：只预览第…行这一处简化**；也可以选择整文件预览。
4. 左侧是原代码，右侧是建议。确认后点预览右上角 **✓**。单处预览只应用该处修改，其他提示保留。
5. 修改留在编辑器里，**Ctrl+Z** 可以撤销。确认后再保存，并运行你项目的测试。

蓝色ALD002提示需要你判断业务意图，不能一键删除异常处理。代码改动后旧预览会拒绝应用，重新预览即可。

日常使用自己的代码：在这个 VS Code 窗口中选择 **文件 → 打开文件夹**，或直接打开一个Python文件。它会在打开和编辑后自动检查，未保存的缓冲区也可以分析。默认只处理打开的文件，避免启动整仓扫描。

命令面板 **Ctrl+Shift+P** 中可以搜索 `AwaitLab`：审查、预览、应用、打开上手示例、查看运行日志。

## 安装到自己的 VS Code 配置

已有日常VS Code环境，也可以在扩展面板的 `… → 从 VSIX 安装` 中选择 [awaitlab-0.2.0.vsix](artifacts/vscode/awaitlab-0.2.0.vsix)。该安装会使用你现有VS Code的扩展存储位置；本项目启动器使用的D盘配置与之独立。

启动器固定使用：

- 扩展：`D:\CodexWork\cache\awaitlab-vscode-extensions`
- 独立用户配置：`D:\CodexWork\cache\awaitlab-vscode-user`
- 演示副本：项目下 `artifacts\vscode-demo\review_me.py`，已有副本不覆盖。
- 任务临时目录：`D:\CodexWork\temp\awaitlab`

应用程序本身沿用已安装的VS Code，并未迁移或修改其他VS Code配置。如果首次打开自己的文件夹出现信任询问，按自己对该文件夹的信任决定；扩展不会在受限工作区执行Python。

## Python 配置

状态栏显示“运行失败”时点击它，选择“设置 Python”。在 `awaitlab.pythonPath` 中填Python 3.10+可执行文件的完整路径，包含空格也不加引号。默认使用PATH中的 `python`。这个设置只控制本地审查器，不改变项目解释器。

`awaitlab.enabled` 可以关闭自动检查；关闭后旧提示清除。Python之外不需要运行时依赖，分析器不导入或执行目标文件。

## 扩展开发与复验

源码在 `extensions/vscode`，内置引擎由 `python extensions/vscode/build_engine.py` 从当前审查器生成，避免独立维护另一套规则。

Windows当前开发机：

```powershell
python extensions/vscode/build_engine.py
node extensions/vscode/test/launch.cjs
```

测试工具位于 `D:\CodexWork\cache\awaitlab-vscode-tools`，npm缓存位于D盘。其他开发机可设置 `AWAITLAB_VSCODE_TOOLS` 指向装有 `@vscode/test-electron` 的node_modules，以及 `AWAITLAB_CODE_EXE` 指向本机Code可执行文件。使用官方 [VS Code 扩展测试入口](https://code.visualstudio.com/api/working-with-extensions/testing-extension) 和 [VSIX 打包方式](https://code.visualstudio.com/api/working-with-extensions/publishing-extension)。

本版扩展0.2.0内置审查引擎0.17.0；CLI的整仓扫描、排除和暂存区核验仍通过原命令使用。编辑器修复不修改Git暂存区。更新后重新双击启动入口打开新窗口，即可加载新版；已有演示副本不覆盖。
