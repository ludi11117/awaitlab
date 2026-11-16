# AwaitLab

本地 Python 代码核查与性能实验：识别部分重复防御条件，再用可复跑的实验核对已提供优化的输出和响应变化。

**日常使用推荐 VS Code 扩展。** Windows 下双击 [Start-AwaitLab-VSCode.cmd](Start-AwaitLab-VSCode.cmd)，自动安装本地扩展并打开演示副本；扩展和独立配置都在D盘。在黄色波浪线处按 **Ctrl+.**，优先选择“只预览这一处”，再点预览右上角 **✓** 应用；**Ctrl+Z** 撤销。也可预览整文件。支持未保存代码，不需要API、账号或pip安装。使用自己的项目时在此窗口打开文件或文件夹即可。[完整操作说明](VSCODE.zh-CN.md)。

**最快查看审查功能：打开 [循环示例报告](artifacts/loop-flow-v0.16.0.html)。** 可以看到循环提前退出后多余的条件、判断依据及补丁建议，无需后台服务、账号、API或模型权重。带理由保留及排除目录见 [接入策略示例](artifacts/audit-policy-v0.13.0.html)，完整分支修改另见 [补丁报告](artifacts/defensive-patches-v0.12.0.html)。

性能实验入口：双击 `Start-AwaitLab.cmd`，默认打开0.8版本的真实SQLite本地报告，包含已声明的负面对照和质量提示；没有报告时才运行实验。重新测量双击 `Run-SQLite-Experiments.cmd`。三个Windows入口都将临时文件放在D盘，结束后恢复调用者的工作目录和环境设置。

求职或复试现场演示见 [DEMO.zh-CN.md](DEMO.zh-CN.md)，包括五分钟操作、技术要点与可核对的简历表述。

## 审查过度防御代码（0.17.0）

这是面向使用者的新功能：扫描自己的 Python 项目，查看代码位置、路径依据和修改建议，生成可复核的补丁。仅使用标准库，不导入或执行扫描目标，不需要模型 API。先看自带示例：

```powershell
python -m awaitlab audit examples/defensive_patch_sample.py --html artifacts/audit.html --output artifacts/audit.json --patch artifacts/audit.patch
```

该示例会报告四处重复条件和一处需复核的吞异常。其中三处能生成补丁，另一处修改会留下空代码块，需手动调整；这一处不再使同文件的其他补丁失效。打开 HTML 可查看每处源码、依据、无法生成补丁的原因及完整差异。简单情形例如：

```python
if value is None:
    return None
if value is None:  # 前面的退出条件已确定这里不可达
    return fallback
```

工具会指出前置条件的行号。扫描目录时替换目标路径即可，默认跳过 `.git`、虚拟环境、node_modules、build/dist 等目录：

```powershell
python -m awaitlab audit D:\CodexWork\projects\your-project --html artifacts/audit.html --output artifacts/audit.json --patch artifacts/audit.patch
```

循环里的 `continue` / `break` 也会确定后续路径。例如 `if value is None: continue` 后的重复 None 检查可以移除，`if value is not None` 可以展开。支持 for、while、async for；退出只影响所在循环的路径，不当作退出整个函数。两个 if 分支都已退出时，停止给后续不可达代码生成 ALD001 提示。可运行 `python benchmarks/loop_flow_check.py`，在受控副本实际应用补丁并核对800个输出；不会执行使用者项目。

| 规则 | 判断依据 | 处理方式 |
| --- | --- | --- |
| ALD001 重复单例条件 | 当前函数局部名称对 None/True/False 的身份关系已确定，支持反向比较、not 及纯身份比较的 and/or 短路路径 | 展示前置条件行号，简单情形生成删除死分支或展开恒真分支的补丁 |
| ALD002 静默宽泛异常 | 裸 except、Exception/BaseException 仅 pass 或返回固定常量 | 仅提示人工复核；合法业务约定不应自动删除 |

`--patch` **只生成差异文件，不改写源码**。在报告的 `patch_root` 目录复核后，可对补丁绝对路径执行 `git apply --check ...`，再自行 `git apply ...`。现在支持简单 if/else：保留实际可达分支，将其注释和 if 头行尾注释保留下来。不可达分支若有说明注释，不猜测是否应该删除，改为提示人工处理；elif链、多行条件、行内语句、制表符缩进等仍只报告。

JSON、补丁和HTML各自完整写入后再替换目标；写入或替换失败时，该文件的上一份完整产物保留，命令返回2。临时文件位于目标目录，默认随D盘项目保存。多个产物分别更新，后续文件保存失败时，前面已成功的文件可能已经更新。

每处候选补丁与此前已接受的修改一起编译检查语法、核对函数/类文档字符串；某处被拒绝，不撤回其他独立有效修改。会改变局部绑定或生成器类型的死分支、多行字符串、非普通 UTF-8 编码等继续保留诊断。原文件变化后应重新扫描，再执行项目测试。

源码定位按Python物理行，导出的Git补丁另按LF分行；LF、CRLF、CR单独换行和混合换行有实际应用回归，字符串内的Unicode分隔符不会被拆成源码行。

形参也可能被删除：`del value`、异常变量清理或闭包的 `nonlocal` 操作后，不再假定读取一定成功。涉及这些绑定的条件保留必要读取，防止将原本的 `UnboundLocalError` 改成正常返回；后续实际条件读取仍可重新建立路径事实。这是局部静态规则，不覆盖任意动态反射或业务语义。

### 提交前：审查真正进入 Git 暂存区的源码

部分暂存时，工作区的代码与准备提交的代码可能不同。进入目标 Git 仓库后运行：

```powershell
python -m awaitlab audit --staged --check --output artifacts/staged.json --html artifacts/staged.html --patch artifacts/staged.patch
python -m awaitlab apply-index artifacts/staged.json --check
# 复核报告后应用；只修改暂存区
python -m awaitlab apply-index artifacts/staged.json
git diff --cached
git diff
```

`audit --staged` 读取相对扫描开始时 HEAD 有变化的 Python 文件的**完整暂存内容**，不是只分析新增行。不会读取未暂存或未跟踪的源码；删除和非普通文件分别记录，冲突文件报错，intent-to-add 不作为已暂存源码。可指定子目录或单文件，`--exclude` 仍相对扫描目录。普通 `audit` 保持扫描工作区。需要本机 Git；不需要模型或新增 Python 依赖。

JSON 保存原始源码 SHA-256、Git blob ID、基准 HEAD 及暂存差异摘要。`apply-index --check` 重新审查并核对版本和建议内容；去掉 `--check` 后，在 Git 索引锁内重新核对，在 D 盘临时索引应用并核对结果，再替换实际索引。已有锁、扫描错误、报告版本不同、暂存内容变化或结果不一致均拒绝应用；工作区源码保持原样。整个暂存快照的变化都会要求重扫，包括范围外文件。支持首次提交、linked worktree、替代索引、split index 和 SHA-256 仓库；split index 应用后可转为完整索引。

**单独 `git apply --cached --check` 不能代替整份源码版本核验。** 已保留反例：修改位于补丁上下文之外的前置条件后，Git 仍接受旧补丁，新命令会拒绝。Git 的补丁选项说明见[官方文档](https://git-scm.com/docs/git-apply)。暂存修复与工作区编辑仍可能不同；同步修改后再运行目标项目测试，避免直接 `git add` 原文件覆盖暂存修复。此命令不提交代码，也不将 HEAD 检查与索引更新声明为跨引用事务。

可打开[暂存区示例报告](artifacts/git-index-v0.15.0.html)。示例来自临时仓库，路径已失效；在自己的仓库重新生成报告后应用。

追加 `--check` 时：存在未忽略的 ALD001 路径冗余返回 1，**包括无法生成补丁的冗余**；仅有 ALD002 异常复核或带理由忽略的项时返回 0，语法/读取/扫描错误返回 2。分支示例应用三处补丁后仍有一处未忽略 ALD001，返回码继续为 1。默认不加 --check 时只打印报告并返回 0，扫描错误仍为 2。

### 整仓接入：排除目录与带理由保留

使用可重复的 `--exclude` 排除生成代码、历史模块或刻意构造的问题样例，例如审查本仓库实际代码：

```powershell
python -m awaitlab audit . --exclude "examples/defensive_*.py" --check --output artifacts/self-audit.json --html artifacts/self-audit.html
```

模式相对扫描目录（扫描单文件时相对其父目录），使用大小写敏感的 fnmatch；`*` 可跨目录，`generated/**` 可以在遍历前跳过整个目录。Windows反斜杠会归一成 `/`。这不是 `.gitignore` 语法，也不自动读取它；排除模式和实际跳过的路径会写进报告。

确实需要保留的某一行可声明理由，必须写在对应 `if` 或 `except` 的同一行：

```python
def optional_plugin(loader):
    try:
        return loader()
    except Exception:  # awaitlab: ignore[ALD002] -- 插件可选，加载失败保留禁用状态
        return None
```

支持 `ALD001`、`ALD002`，多个编号用逗号分隔。理由不可为空，未知编号或错误格式会作为扫描错误返回 2；字符串里的相同文字不能充当指令。忽略只作用于该行实际命中的规则，不会传播到后续行，也不会生成该项补丁。JSON与HTML仍保留被忽略的诊断和理由，**忽略不等于已修复**。

0.13时的 [整仓实测](artifacts/self-audit-v0.13.0.html) 排除3个刻意的问题样例后，扫描82个Python文件，没有触发当前两类规则；不代表完整代码质量证明。策略验收在D盘临时项目中验证目录剪枝、带理由保留及补丁应用，见 [audit-policy-check-v0.13.0.json](artifacts/audit-policy-check-v0.13.0.json)。复跑用 `python benchmarks/audit_policy_check.py`。

### 多处候选修改的验证成本

0.14先验证整批非重叠修改，整批失败才回到逐项验证，不删除语法、文档字符串或独立补丁保留检查。固定构造负载中，每个文件的候选修改数与三对测量的描述性中位数如下：

| 候选修改数 | 冻结0.13源码 | 0.14 |
| --- | ---: | ---: |
| 20 | 24.66 ms | 5.54 ms |
| 100 | 600.35 ms | 56.07 ms |
| 200 | 2837.85 ms | 204.66 ms |

这是本机扫描构造文件的成本，不是业务接口加速或跨机器保证。200处负载约少用92.8%时间；只做3对计时，没有性能显著性结论，也未消除所有其他扫描开销。含拒绝项时还需逐项验证，单次小探针从2.85变3.78ms，这个成本保留在记录中。

新旧结果在87个当前Git列出的Python文件、12条诊断及所生成源码上完全一致；该有限语料不构成全域等价证明。记录与固定基线SHA见 [audit-validation-cost-v0.14.0.json](artifacts/audit-validation-cost-v0.14.0.json) 和 [audit-validation-equivalence-v0.14.0.json](artifacts/audit-validation-equivalence-v0.14.0.json)。复跑命令是 `python benchmarks/audit_validation_cost.py`，等价核对另用 `--corpus`；`--gate-ms 1000` 只是本机回归探针，不加入跨机器单元测试。

0.14.1再缓存UTF-8源码切片，并按Python实际的LF/CRLF/CR换行处理行号，修复字符串内Unicode分隔字符导致补丁误拒绝的问题。8种字符串分隔字符、中文标识符、不同换行和无末尾换行均有回归；非空格特殊缩进仍交给人工。新一轮同协议中，200候选相对冻结0.13的中位数为2863.97→49.31ms；这是构造扫描成本、3对描述性计时，不是业务响应或跨机器保证，也不把不同轮次的0.14/0.14.1数字当作直接配对检验。新语料88文件的诊断与建议源码仍与冻结基线一致；特殊字符补丁则按新的正确行为单独验证。记录见 [0.14.1计时](artifacts/audit-validation-cost-v0.14.1.json) 与 [语料核对](artifacts/audit-validation-equivalence-v0.14.1.json)。

分析限局部语法模型：在赋值、调用、await 和其他不支持的语句处丢弃已知事实，不推断跨函数、全局变量、动态反射或业务必要性。and 为假不表示每项都为假；or 为真不表示每项都为真，合流只保留所有可达路径共有的事实。`value is True` 与 `if value` 或 `value == True` 不混用，不假设用户对象的真值/相等方法没有副作用。

它覆盖两类明确模式，不是全部过度防御问题的检测器，也不承诺补丁在所有 Python 元编程环境中语义等价。当前验收见 [defensive-patch-check-v0.12.0.json](artifacts/defensive-patch-check-v0.12.0.json)：三处补丁应用到 D 盘临时副本，六条注释原文全部保留，28 个示例输入输出一致；一处手动修改和一处异常复核仍存在，原源码未改。原0.10/0.11样例保持原版本。重新执行当前验收用 `python benchmarks/defensive_patch_check.py`。

## 减少多余数据库查询：订单列表补全客户资料

新增真实 SQLite 案例：48 条订单关联 12 个已有客户及 1 个缺失客户，比较三种实现。它们使用同一有索引数据库，每个请求只开一个连接和只读事务，没有人为延迟。订单列表是固定构造的输入，下面只统计补全客户资料的 SELECT，不包含订单列表查询。

| 实现 | 每请求实际 SELECT 数 | 本次平均响应变化 |
| --- | ---: | ---: |
| 每条订单查询一次客户 | 48 | 各候选的配对基线 |
| 请求内按客户去重，再还原订单 | 13 | -26.36% |
| 去重后用参数化 IN 分批查询，再还原订单 | 1 | -28.22% |

```powershell
python -m awaitlab run examples.order_query_case --plan
python -m awaitlab run examples.order_query_case --output artifacts/my-orders.json
python -m awaitlab run examples.order_query_case --output artifacts/my-orders.json --resume
```

输出完整保留订单顺序、重复客户关联、同一 email 的全部客户行和缺失客户空列表；没有通过去重订单或丢掉缺失行来减少查询。去重字典只在单个请求内存在，下一个请求重新查询，不引入跨请求缓存过期问题。批量查询每组最多 256 个不同 key，超过后分批，不把不受限的列表直接塞进一条 SQL。

查询数由 `sqlite3.set_trace_callback` 逐请求记录，不靠代码行数估计。固定 10 配对、16 请求、4 并发、预热 2，本次执行 37,080 次 SELECT，完整输出一致，30 对恢复不再查询。原实现对照变化 +5.07%、Holm p=.6387，未触发预设报警，不证明等价。候选 Holm p 均 .005859375；这只是该合成负载下的响应收益，不能把 48→1 次查询说成响应快 98%，也没有检验批量与去重二者的直接差异。

可复用实现见 [examples/order_query_case.py](examples/order_query_case.py)，离线报告见 [artifacts/order-queries-v1.html](artifacts/order-queries-v1.html)，原始 SQL 次数见 [artifacts/order-query-check-v1.json](artifacts/order-query-check-v1.json)。运行 `python benchmarks/order_query_check.py` 会重新执行固定验收并更新该案例报告。它展示 N+1 查询消除，不会自动扫描任意 ORM；同一请求内复用读取结果需要稳定读取语义，本例用显式只读事务保持一致快照。

## 直接比较自己的两个接口（0.9）

已有优化前后的 GET / JSON 接口时，不必再编写 Python 实验模块：

```powershell
python -m pip install ".[http]"
python -m awaitlab http --before "http://127.0.0.1:8000/old?id={id}" --after "http://127.0.0.1:8000/new?id={id}" --workload-version local-build-1 --output artifacts/my-api.json
```

命令用相同 ID 比较原接口与候选接口，再将原接口与自身比较作为负面对照，生成可离线打开的 HTML 和 JSON。追加 `--plan` 只看方案、不发请求；追加 `--resume` 恢复身份相同的完整配对，不重复已完成请求。报告核对状态码与完整 JSON，不自动忽略时间戳、随机 ID 或其他差异。仅接受 2xx JSON 响应。

`{id}` 默认依次取 0 到 39，可通过 `--first-id` 和 `--requests` 调整；不写占位符就重复请求同一地址。每块预热复用测量范围内的 ID。默认 10 批次、40 请求、8 并发，加上预热及负面对照共发出 1760 次 GET，请在可控环境使用。`--workload-version` 必须非空，由接入者标记服务代码及数据版本；服务或数据改变时要更新标签，工具不能自动核实外部版本。

没有自己的服务时，可用项目内的真实 SQLite 服务练习。第一个终端运行：

```powershell
python examples/http_service.py
```

复制它打印的 `workload_version`，在第二个终端将下方 `SERVICE_VERSION` 替换为该值：

```powershell
python -m awaitlab http --before "http://127.0.0.1:8765/before?id={id}" --after "http://127.0.0.1:8765/after?id={id}" --workload-version SERVICE_VERSION --requests 12 --concurrency 4 --output artifacts/my-api.json
```

这会执行 640 次真实查询；在第一个终端按回车关闭服务。示例比较相同数据的无索引/有索引查询，索引实现由示例提供。

每块新建客户端与连接池，外部服务和缓存不会重置。测量包括客户端接收、JSON 解码和追踪，不包含服务内部跨度。`--timeout` 默认 10 秒，限制完整响应接收，不能中断同步 JSON 解码；`--max-response-bytes` 默认 1 MiB，限制已解码响应内容，并非进程内存上限。报告只保存 URL 的来源站点与摘要，不保存路径、查询参数或响应正文；地址仍可能存在于调用者的命令历史。需要认证请求头、POST 或明确的业务字段投影时，使用下文的自定义 `run` 模块。

## 目前能看到什么

- 并行订单查询：12 个库存查询累计耗时很高，但替换它们后，响应时间基本不变；定价查询替换后，当前受控负载下响应明显下降。
- 共享连接池：区分取得连接前的排队跨度和持有连接时的查询跨度；核对查询加快后排队响应的变化。
- **0.3 真实 SQLite 查询**：同样的 5 万行客户数据、相同 SQL，比较无索引与有索引实现；另设不改实现的对照，检查随机波动会不会被误报为收益。查询由实际数据库引擎执行，没有人为 sleep。
- **0.3 SQLite HTTP 接口**：真实本机 TCP / HTTPX / Uvicorn / FastAPI 链路，比较端到端收益。通过一次性本地票据显式桥接上下文，限单进程、同一事件循环。
- FastAPI 另有进程内 ASGI 与可控 sleep 示例，用于解释并行等待机制，不冒充真实数据库负载。
- 报告包括配对批次、均值差的 bootstrap 区间、输出核对、采样任务时间线、累计跨度和定时器校准。
- 0.3.1 时间线可选择已有采样的批次和请求；同任务的重叠跨度分轨显示，点击可查看已记录父跨度。轨道序号不等于依赖深度。
- 0.4 将业务响应、含输出校验的 worker 周期、同步校验段和整批 wall 分开展示。请求窗口覆盖按区间并集计算，不能把并行重叠的累计跨度相加为响应时间。
- 实际替换结果经过固定比较组内的 Holm 调整，结合预先声明的 5% 点估计门槛分级；不会把“小幅变快”直接标为优化成立。

**这不是“优化加速保证器”。** 等待干预测的是操作增加协作式等待后的响应变化，不能据此反推任意加速效果。真实替换才报告已实测的 A/B 变化；示例收益不是该工具自身把业务程序自动加速的比例。

## 运行要求

Python 3.10+，本机验证版本为 3.13.15。核心、SQLite 实验与报告仅使用标准库，直接在本目录运行即可，无需安装。HTTP 例子另需 fastapi、httpx、uvicorn；本机已存在，项目没有将它们设为核心依赖。

```powershell
python -m awaitlab demo --scenario sqlite --output artifacts/sqlite-latest.json
python -m awaitlab demo --scenario sqlite-http --output artifacts/sqlite-http-latest.json
python -m awaitlab demo --scenario parallel --output artifacts/parallel-latest.json
python -m awaitlab demo --scenario pool --output artifacts/pool-latest.json
python examples/fastapi_lab.py
python examples/fastapi_tcp.py
```

每次生成同名 JSON 和 HTML。HTML 可离线打开，无外部脚本、字体或网络请求。SQLite 两个场景默认 10 个配对批次，其他演示默认 6 个；每批 40 请求、8 个闭环并发 worker。要重跑两个等待机制演示，双击 `Rerun-Experiments.cmd`。运行时间随 Windows 调度和机器负载变化。

当前0.8样例中，索引版的直接查询平均响应下降约79%，HTTP场景下降约13%，已测输出一致；两个原实现对照都未触发预设报警规则，不等于证明等价。两个场景分别实测，不作跨版本加速推断；索引由接入者提供。原始数据与边界见 [VALIDATION.md](VALIDATION.md)。旧0.4 JSON/HTML保留在 artifacts/history/，发布时的0.8快照另存为 sqlite-v0.8.0 与 sqlite-http-v0.8.0，后续重跑latest不会覆盖这些快照。

数据库文件合计约 6.6 MB，存于 `D:\CodexWork\temp\awaitlab\sqlite-fixture-v1`。两份文件每块计时前都会校验并完整读取，所有线程各自预热两条路径。每次查询新建、关闭只读连接：包含线程排队、连接创建及取回结果的成本；预热主要影响 OS 文件缓存，后续新连接不继承 SQLite 私有页缓存。这是短连接的读实验，不是冷盘、持久连接池或写事务性能测试。

**0.6.4 支持先看方案再测量：** `python -m awaitlab demo --scenario sqlite --blocks 6 --plan`，或 `python -m awaitlab run examples.events_bundle_case --plan`。只打印设置、替换候选组和检验分辨率，不调用内置数据准备、校准、workload或断点，也不新建输出目录。自定义模块仍会导入，其顶层代码照常执行。

例如6个配对批次、2个替换候选，双侧精确检验的最佳原始p为.03125，最佳Holm p为.0625，无法满足当前 `p < .05`。运行前和新报告都会说明；增加每批请求数不能代替独立配对批次。7批次只意味着该候选组理论上具备分辨率，不保证统计功效或观察到收益。0.7将精确范围从16扩到32批次，超过32仍使用近似检验且不会自动分级为支持。实验前固定方案，不补样直到显著，也不截取已测批次。

**0.7 使用整数分治计数减少统计计算成本。** 固定夹具下16批次从约73ms降至.14ms，32批次约26ms即可精确计数；单次32批次的Python追踪分配峰值约7MiB。它不会因此让业务请求同比加快。数值边界约定、独立参考、内存取舍以及“极短负载的原实现对照也被判支持”的反例均见 [METHOD-v0.7.md](METHOD-v0.7.md)。

**0.8 支持声明负面对照角色。** `Arm(..., role='negative_control')`表示该替换用于检查实验条件，默认role仍为candidate。内置SQLite和客户HTTP的原实现对照已声明；`--plan`可检查角色，改变角色会使旧断点身份不匹配。对照不会作为优化候选：输出不一致，或任一方向变化达到同一5%点门槛且精确Holm p < .05时，报告提示异常并暂停整轮候选推荐。实际门槛取Settings；对照仍计入同一比较组。

没有报警不证明等价，没有配置对照也不补造“已通过”。原始效应和p始终保留，`evidence_level`记录原有数值规则分级，`candidate_improvement`再结合角色与quality决定是否推荐。32次固定后续诊断未稳定复现旧计时异常，未宣称已找到计时根因；原异常的解释回放与全部证据见 [METHOD-v0.8.md](METHOD-v0.8.md)。

## 接入自己的代码

为有意义的异步操作添加标记；不要给每个几微秒函数都加标记。

**0.5 支持直接从 CLI 运行自己的实验模块。** 完整可运行例子：

```powershell
python -m awaitlab run examples.unique_case --output artifacts/unique-latest.json
python -m awaitlab run examples.unique_case --output artifacts/unique-latest.json --resume
```

例子对 3000 个整数事件 ID 做保序去重，比较列表扫描与哈希表，输出包含完整去重 ID 列表，没有人为 sleep。当前同一固定输入协议下均值约6.94ms → 0.24ms；这是提供的算法替换效果，不是工具发明或自动生成的优化。CPU工作会占用事件循环，本例设并发1，不冒充CPU并行测试。

**0.6.3 增加组合替换示例**：`python -m awaitlab run examples.events_bundle_case --output artifacts/events-bundle-latest.json`。对同一批事件分别替换去重、计数和二者组合，核对完整保序ID与频次；离线示例见 artifacts/events-bundle-v0.6.3.html。报告展开“替换范围与实际触达”可看每个站点实际执行多少次。收益属于整组配置，不能把组合结果归给主站点，也不能把独立实验的百分比直接相加。

主要替换站点必须在每个实验块的测量阶段实际分派到候选实现；其他站点、预热、同名观测跨度和退出后的清理调用都不能代替该证据。每块保留总次数及 `replacement_calls_by_site`；额外配置但未调用的站点允许为0。捕获或继承的会话上下文在本次会话退出后失效，重新进入同一Session也不会复活旧上下文。计数表示分派尝试，输出是否一致仍单独核对。

将 examples/unique_case.py 复制到自己的项目，保留模块级 `experiment = Experiment(...)`、非空 `workload_version`，可选 `title`；替换业务 factory 与候选实现即可。在模块所在目录运行，不必额外写 asyncio 启动脚本：

```powershell
# 在 D 盘自己的项目目录中，直接引用本仓库 SDK
$env:PYTHONPATH='D:\CodexWork\projects\awaitlab'
python -m awaitlab run perf_case --output artifacts/perf.json
```

`perf_case` 对应本地 perf_case.py，也可使用包内的点分模块名。模块按普通 Python 代码导入。实验设置由模块内 Settings 决定，CLI 的 blocks/requests/concurrency 参数用于 demo 子命令。可选导出 `transport` 和 `output_contract` 字符串，分别说明实际链路和核对哪些输出字段。入口模块、workload、replacement 和 SDK 已知源码会进入断点身份；配置源码变化后拒绝恢复，测量中变化也拒绝输出完成报告。外部数据与未自动覆盖的传递依赖仍需更新 workload_version。

0.9.1 收紧模块配置合同：`title`、`transport`、`output_contract` 若声明就必须是字符串，不再把 `None` 或数字强转成报告文案。无需这些字段时直接省略；标题默认模块名，其余两项不补造。配置错误会在测量前说明字段名，不覆盖已有完整报告。SDK 源码变化会使旧断点身份不匹配，旧报告仍可查看，新版本请使用新输出路径开始测量。

纯实现替换不运行额外定时器校准；包含等待干预的实验会测量名义等待与实际等待的偏差。以下为直接使用 Python API 的方式：

```python
import asyncio
from contextlib import asynccontextmanager
from awaitlab import operation, stage, Arm, Experiment, Settings
from awaitlab.report import write_report

@operation('fetch')
async def fetch(i):
    await asyncio.sleep(0.03)
    return {'id': i, 'amount': i * 2}

async def faster_fetch(i):  # 用待验证的新实现替代这里
    await asyncio.sleep(0.008)
    return {'id': i, 'amount': i * 2}

@asynccontextmanager
async def workload():
    # 每次创建自己的池、客户端、缓存；退出时关闭资源与后台任务。
    yield fetch

async def main():
    experiment = Experiment(workload, [
        Arm('delay_fetch', 'delay', 'fetch', delay_ms=4),
        Arm('new_fetch', 'replacement', 'fetch',
            replacements={'fetch': faster_fetch}),
    ], Settings(blocks=10, requests=40, concurrency=8))
    report = await experiment.run()
    write_report(report, 'my-report.html')

asyncio.run(main())
```

目标函数收到固定请求 ID；控制组和实验组必须为同一 ID 产生可比较的 JSON 业务结果。若响应包含时间戳、随机追踪 ID，请在 workload 的 handler 中明确提取要核对的稳定业务字段；系统不会擅自忽略差异。输出内容不进入报告，只保存整批摘要和不一致的请求 ID。哈希一致只支持已测输入，不证明全域语义等价。

资源等待可以单独标记：

```python
async with stage('pool_wait'):
    await semaphore.acquire()
try:
    result = await fetch(i)  # 包括注入等待，连接仍由外层持有
finally:
    semaphore.release()
```

把标记移到释放连接之后，就测了另一个机制。不能把一次函数末尾延迟注入解释成任意锁内部、CPU 计算或网络服务器都发生了相同变化。

## 方法边界

- 额外等待使用 `asyncio.sleep`，不会故意阻塞整个事件循环；不模拟增加 CPU 工作。零干预不调用 sleep(0)。
- 先按实验臂预热，再在同一批次随机排列控制/实验顺序。资源每次重建，请求输入按 ID 固定，不能用全局 RNG 的调度消费顺序决定业务数据。
- 按配对工作负载批次重采样，而不是把同一批内的请求当成独立试验。显示的区间是未调整的探索性百分位 bootstrap，不是多个实验臂同时覆盖的区间。
- 真实替换另做双侧配对随机化检验，并在预先列出的所有替换臂内作 Holm 调整。需满足随机执行顺序、标签可交换、无跨轮残留干扰等条件；随机顺序本身不证明这些条件成立。
- 仅在输出一致、点估计改善至少 5%、精确检验 Holm p<.05 且负面对照未报警时标记“本轮支持继续验证此优化”。这不证明真实改善下界至少 5%，也不是注册过的确认性研究。超过 32 块时报告 Monte Carlo 近似 p，不自动升级为支持。
- 6 块、两个替换臂时最小 Holm p 为 .0625；即便图中 bootstrap 区间不跨零，也无法按此规则升级。应在开始前确定块数，不能为了过线而事后不断追加。
- p95 只作描述，不提供尾分位显著性结论。闭环并发不是生产环境固定外部到达率的负载。
- 输出校验不计入自身请求的响应，却会影响其他任务与下一次发起节拍；wall 与 worker 周期包含校验。报告显示实测成本，不能靠减去哈希耗时恢复“无干扰响应”。大输出探针与处理边界见 [OUTPUT-METHOD.md](OUTPUT-METHOD.md)。
- Windows 上名义 sleep 时长可能明显小于实测值。报告会记录空闲定时校准和实际负载中的注入等待；程序不修改系统定时器分辨率。
- 仅追踪明确标记的跨度和前几个请求，不是完整 await 依赖图，也不自动证明关键路径。
- 资源与后台任务必须在 workload 退出时清理。遗留任务会导致本块实验被拒绝；只清理在实验上下文创建的任务，不碰进程中的无关任务。取消处理必须合作，不能吞掉 CancelledError 后永久运行。
- 0.6.1 持有尚未完成的本批任务，完成回调移除引用，避免应用丢失引用后Task被GC回收而绕过遗留检测；取消期间产生的有限子任务也会继续清理。这个持有/完成释放方式符合 [Python 3.13 asyncio 文档](https://docs.python.org/3.13/library/asyncio-task.html#asyncio.create_task) 的任务生命周期建议。它不能代替应用自身正确收尾，也不支持无限生成子任务的非合作式清理。
- 首版限单进程、合作式 asyncio 与可控制的实验环境，不应直接在生产服务中开启干预。真实本机 TCP 可通过 LocalASGITrace 显式接入；跨线程、多 worker 和跨进程分布式上下文仍未实现。

## 接入真实本机 HTTP

`examples/fastapi_tcp.py` 是完整可运行示例。把同一个桥接对象交给 ASGI middleware 和本地压测客户端：

```python
from awaitlab.asgi import LocalASGITrace
bridge = LocalASGITrace()
instrumented_asgi_app = bridge.middleware(app)

# 在 Experiment 的 handler 内：
with bridge.headers() as headers:
    response = await client.get('/orders/1', headers=headers)
```

票据只引用同一进程内的会话，单次使用且离开请求上下文后移除。无票据请求正常透传；无法识别、重复或来自非本机客户端的票据返回403。没有票据内容进入实验报告。服务绑定 127.0.0.1 临时端口，关闭实验即关闭服务，不启动常驻进程。

### 含初始化资源与动态响应的接口

0.6 的 `serve_local(app)` 默认启用 ASGI lifespan，等 startup 完成后才交付客户端，关闭时等待 shutdown。启动失败、关闭失败均会拒绝本次测量；Uvicorn 的启动 SystemExit 在嵌入边界转为 RuntimeError。启动中或关闭中取消会清理受控任务并保留 CancelledError。资源需合作式清理；HTTP-only ASGI 应用可明确使用 `serve_local(app, lifespan='off')`。

完整例子 [examples/customer_api_case.py](examples/customer_api_case.py)：在 FastAPI lifespan 中创建专用线程池，HTTPX 客户端在每块内复用连接；SQLite仍每次查询新建并关闭只读连接。

```powershell
python -m awaitlab run examples.customer_api_case --output artifacts/my-customer-api.json
python -m awaitlab run examples.customer_api_case --output artifacts/my-customer-api.json --resume
```

接口每次都会返回新的追踪ID与时间戳。示例的 `business_output` 明确返回 HTTP 状态及完整客户数据，排除这两个追踪元数据字段；报告显示 output_contract，避免把投影一致误认为整个响应相同。测试另验证原始整响应会因动态字段而不一致，客户余额变化在投影后仍会被检出。业务时间字段若属于结果语义，应纳入你自己的投影。

固定10配对、每批24请求、4并发的复验记录见 artifacts/customer-api-v0.6.0.json 与 customer-lifecycle-check-v0.6.0.json：40次应用生命周期均正确开关资源，HTTP连接在块内复用；完整恢复20对数据不重新启动应用。此负载与旧版8并发SQLite样例不同，不作版本性能提升比较。用 `python benchmarks/customer_lifecycle.py` 可复跑并核对这些生命周期记录。

## 中断与恢复

CLI 每完成一整对实验就原子写入同名 `.checkpoint.json`。Ctrl+C / 任务取消时保留已完成配对；正在进行的半对不算完成。完成报告只在全部测量成功后覆盖，失败不会把半成品伪装成新结果。

`--output` 必须是 `.json` 路径，对应 HTML 自动生成。已知测量/恢复错误会给出非零退出码、原因与断点位置，并明确旧数据没有替换；取消退出码为 130。JSON 和 HTML 各自原子替换，二者不构成跨文件事务；若保存中途失败，以错误提示和完整断点为准。

```powershell
python -m awaitlab demo --scenario parallel --output artifacts/my-run.json
# 中断后，保持代码和参数一致：
python -m awaitlab demo --scenario parallel --output artifacts/my-run.json --resume
```

SDK 方式：`await experiment.run(checkpoint='run.checkpoint.json', resume=True, workload_version='fixture-v1')`。断点绑定设置、运行环境、库源码、workload 与 replacement 所在的已知源码文件，以及显式工作负载版本。开始与结束均核对已知代码，检测运行期间的源码变化。

使用SDK时可额外传入 `source_files=['perf_case.py']` 将入口/配置文件纳入核对；CLI run 会自动加入入口模块。

外部数据、数据库状态、闭包配置和所有传递依赖无法自动完整指纹化，变更这些内容必须更新 workload_version；不要把文件哈希当作全环境可复现保证。断点不支持并发写入。同一路径不加 --resume 是重新运行，不复用旧配对。

进一步的方法审查和一手来源见 [METHOD.md](METHOD.md) 与 [METHOD-v0.3.md](METHOD-v0.3.md)。旧版 JSON 的 verified_improvement 字段不沿用为新版证据；用新版渲染器打开时标为“历史报告：未按新版规则分级”。因果性能分析、异步追踪和实验统计都有前人工作，本项目未证明原创性，也没有宣称胜过 Coz、Pyinstrument 或 Codex。

## 验证与自身开销

```powershell
python -m unittest discover -s tests -v
python benchmarks/overhead.py
python benchmarks/paired_overhead.py
node --check awaitlab/assets/report.js
node tests/timeline.cjs
```

可选浏览器验收 `node tests/browser.cjs`，默认复用 D 盘现有 Playwright/Chromium，可用 AWAITLAB_PLAYWRIGHT 和 AWAITLAB_CHROMIUM 指定位置。应用不需要这些依赖。

固定并发梯度实验：`python benchmarks/concurrency_suite.py`，依次测量直接 SQLite 与 HTTP 链路的 1、4、8 并发，各 10 配对块、每批 32 请求、seed=173。协议先写入 `artifacts/concurrency-v1-<库版本>/plan.json`，完整块可使用 `--resume` 恢复；不同库版本分目录，保留历史测量。此脚本是探索性复验，不是为了达到显著性而搜索参数；Holm 只覆盖每个场景内部的替换臂，不覆盖全部反复试验。若安装了 psutil，另记录整个驱动进程的 RSS 采样峰值，包含导入与之前场景，不能当隔离服务的内存需求。

已完成的 0.3.1 梯度原始记录保存在 `artifacts/concurrency-v1/`；使用已有 matplotlib 导出图：`python benchmarks/plot_concurrency.py --folder artifacts/concurrency-v1`。这不是核心运行依赖。

当前微基准每组 30,000 次无 I/O 的空异步调用、7 次随机顺序重复。第一次自身优化将聚合追踪中位数从约 2.54 降到 1.78 微秒/调用；这是先后两轮微基准，不是业务整体加速或严格配对显著性证据。输出在 artifacts/overhead-v0.1.json 与 artifacts/overhead.json。该进程包含测量脚本的工作集约 27 MiB，不包含浏览器。

0.2 增加同进程、11 个随机配对批次的旧/新实现比较，冻结基线取自 0.1.0 安装包并记录源码 SHA256。当前测到约29%开销下降，均值差约 -0.72 微秒/调用，95% 配对 bootstrap 区间约 [-0.74, -0.69] 微秒/调用。原始数据在 artifacts/paired-overhead.json；仍只代表本机空操作聚合追踪微基准，不代表业务服务同比加速。

0.4.1 避免在已有聚合项命中时重复构造默认字典。相对冻结 0.4.0 源码，同进程 12 个随机配对批次中，10 万次聚合空调用从约1.85降至1.70微秒/调用（约8%）；3万次、4096条采样上限的模式也约下降8%。4千个不同操作名的差值区间跨零，不宣称该模式收益。完整协议、逐批数值和三模式 Holm 调整见 artifacts/trace-allocation-v0.4.1.json。这里的数值包含空函数与驱动循环，不是生产业务的整体加速。

0.6.1 的任务持有修复有可测成本：固定12配对、4096任务/组、64任务/波，立即返回模式从约2.80到3.19微秒/任务，约增加0.39微秒；单次yield模式的差值区间跨零，证据不足。这里包含Task/gather/调度和登记成本，不是业务请求同比变慢。完整原始数据见 artifacts/task-ownership-v0.6.1.json，故障复现见 artifacts/ownership-gc-v0.6.1.json；没有用关闭遗留检查换取更漂亮的耗时。

0.6.2 复用本机HTTP压测客户端的SSL配置，逐批新建应用、客户端和连接池。12个随机配对中，配置已加载后的辅助器就绪时间约320ms → 13ms；首次SSL配置构造仍约277ms。包括3个请求和关闭的完整辅助器周期约538ms → 217ms。这减少实验准备成本，不表示业务响应快了96%。配置保留默认信任证书和验证设置，进程内作为固定快照复用；证书配置变化后重启进程。实现依据 [HTTPX SSLContext配置](https://www.python-httpx.org/advanced/ssl/) 与 [Python SSLContext共享规则](https://docs.python.org/3.13/library/ssl.html#ssl.SSLContext)。

复跑：`python benchmarks/http_setup.py`；分进程描述内存与含首次加载的12次生命周期：`python benchmarks/http_setup.py --memory`。原始数据在 artifacts/http-setup-v0.6.2.json / http-setup-memory-v0.6.2.json，阶段图在 http-setup-phases-v0.6.2.png；可选matplotlib导出脚本为 benchmarks/plot_http_setup.py。

跨度记录有上限，聚合计数仍保留。延迟数组、输出摘要、批次结果和报告也会占内存，不能把“追踪有上限”说成整个实验内存恒定。报告 v2 删除重复首批数据与逐行哈希列表，保留整批摘要、不一致 ID 和逐批结果。

项目、构建后端、缓存、临时数据均放 D 盘；Python 运行时沿用现有安装位置。没有迁移 Codex 数据或系统目录。
