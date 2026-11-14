# AwaitLab

给 Python 异步服务做可复跑的性能实验：找出对响应时间敏感的操作，再用真正更快的实现核对收益。

**最快查看：双击 `Start-AwaitLab.cmd`。** 它会打开真实 SQLite 查询的本地交互报告；没有报告时才运行实验。无需后台服务、账号、API 或模型权重。重新测量双击 `Run-SQLite-Experiments.cmd`。

求职或复试现场演示见 [DEMO.zh-CN.md](DEMO.zh-CN.md)，包括五分钟操作、技术要点与可核对的简历表述。

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

当前 0.4 样例中，索引版的直接查询平均响应下降约 83%，经过 HTTP 链路下降约 28%，已测请求输出一致。这是这组数据与本机环境的实测替换结果，不是工具自动产生索引，也不保证其他数据库同样收益。原始数据与完整边界见 [VALIDATION.md](VALIDATION.md)。

数据库文件合计约 6.6 MB，存于 `D:\CodexWork\temp\awaitlab\sqlite-fixture-v1`。两份文件每块计时前都会校验并完整读取，所有线程各自预热两条路径。每次查询新建、关闭只读连接：包含线程排队、连接创建及取回结果的成本；预热主要影响 OS 文件缓存，后续新连接不继承 SQLite 私有页缓存。这是短连接的读实验，不是冷盘、持久连接池或写事务性能测试。

## 接入自己的代码

为有意义的异步操作添加标记；不要给每个几微秒函数都加标记。

**0.5 支持直接从 CLI 运行自己的实验模块。** 完整可运行例子：

```powershell
python -m awaitlab run examples.unique_case --output artifacts/unique-latest.json
python -m awaitlab run examples.unique_case --output artifacts/unique-latest.json --resume
```

例子对 3000 个整数事件 ID 做保序去重，比较列表扫描与哈希表，输出包含完整去重 ID 列表，没有人为 sleep。当前同一固定输入协议下均值约6.94ms → 0.24ms；这是提供的算法替换效果，不是工具发明或自动生成的优化。CPU工作会占用事件循环，本例设并发1，不冒充CPU并行测试。

将 examples/unique_case.py 复制到自己的项目，保留模块级 `experiment = Experiment(...)`、非空 `workload_version`，可选 `title`；替换业务 factory 与候选实现即可。在模块所在目录运行，不必额外写 asyncio 启动脚本：

```powershell
# 在 D 盘自己的项目目录中，直接引用本仓库 SDK
$env:PYTHONPATH='D:\CodexWork\projects\awaitlab'
python -m awaitlab run perf_case --output artifacts/perf.json
```

`perf_case` 对应本地 perf_case.py，也可使用包内的点分模块名。模块按普通 Python 代码导入。实验设置由模块内 Settings 决定，CLI 的 blocks/requests/concurrency 参数用于 demo 子命令。可选导出 `transport` 和 `output_contract` 字符串，分别说明实际链路和核对哪些输出字段。入口模块、workload、replacement 和 SDK 已知源码会进入断点身份；配置源码变化后拒绝恢复，测量中变化也拒绝输出完成报告。外部数据与未自动覆盖的传递依赖仍需更新 workload_version。

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
- 仅在输出一致、点估计改善至少 5%、精确检验 Holm p<.05 时标记“本轮支持继续验证此优化”。这不证明真实改善下界至少 5%，也不是注册过的确认性研究。超过 16 块时报告 Monte Carlo 近似 p，不自动升级为支持。
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

跨度记录有上限，聚合计数仍保留。延迟数组、输出摘要、批次结果和报告也会占内存，不能把“追踪有上限”说成整个实验内存恒定。报告 v2 删除重复首批数据与逐行哈希列表，保留整批摘要、不一致 ID 和逐批结果。

项目、构建后端、缓存、临时数据均放 D 盘；Python 运行时沿用现有安装位置。没有迁移 Codex 数据或系统目录。
