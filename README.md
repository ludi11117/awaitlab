# AwaitLab

给 Python 异步服务做可复跑的性能实验：找出对响应时间敏感的操作，再用真正更快的实现核对收益。

**最快查看：双击 `Start-AwaitLab.cmd`。** 它会打开已生成的本地交互报告；没有报告时才运行演示。无需后台服务、账号、API 或模型权重。

## 目前能看到什么

- 并行订单查询：12 个库存查询累计耗时很高，但替换它们后，响应时间基本不变；定价查询替换后，当前受控负载下响应明显下降。
- 共享连接池：区分取得连接前的排队跨度和持有连接时的查询跨度；核对查询加快后排队响应的变化。
- FastAPI 接入例子：实际运行路由、类型验证、请求/响应序列化；当前使用进程内 ASGI，不包含 TCP 和 uvicorn 多 worker。
- 0.2 新增真实本机 TCP / HTTPX / Uvicorn / FastAPI 示例。通过显式本地票据桥接上下文，不依赖 ContextVar 自动穿过网络；仍限单进程、同一事件循环。
- 报告包括配对批次、均值差的 bootstrap 区间、输出核对、采样任务时间线、累计跨度和定时器校准。

**这不是“优化加速保证器”。** 等待干预测的是操作增加协作式等待后的响应变化，不能据此反推任意加速效果。真实替换才报告已实测的 A/B 变化；示例收益不是该工具自身把业务程序自动加速的比例。

## 运行要求

Python 3.10+。核心与报告仅使用标准库，直接在本目录运行即可，无需安装。FastAPI 例子另需 fastapi、httpx；本机已存在这两个库，项目没有把它们设为核心依赖。

```powershell
python -m awaitlab demo --scenario parallel --output artifacts/parallel-latest.json
python -m awaitlab demo --scenario pool --output artifacts/pool-latest.json
python examples/fastapi_lab.py
python examples/fastapi_tcp.py
```

每次生成同名 JSON 和 HTML。HTML 可离线打开，无外部脚本、字体或网络请求。要重新运行两个基础演示，双击 `Rerun-Experiments.cmd`。默认 6 个配对批次、每批 40 请求、8 个闭环并发 worker；运行时间随 Windows 调度和机器负载变化。

## 接入自己的代码

为有意义的异步操作添加标记；不要给每个几微秒函数都加标记。

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
    ], Settings(blocks=6, requests=40, concurrency=8))
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
- 按配对工作负载批次重采样，而不是把同一批内的请求当成独立试验。区间是探索性的百分位 bootstrap，未进行多重比较校正。
- p95 只作描述，不提供尾分位显著性结论。闭环并发不是生产环境固定外部到达率的负载。
- Windows 上名义 sleep 时长可能明显小于实测值。报告会记录空闲定时校准和实际负载中的注入等待；程序不修改系统定时器分辨率。
- 仅追踪明确标记的跨度和前几个请求，不是完整 await 依赖图，也不自动证明关键路径。
- 资源与后台任务必须在 workload 退出时清理。遗留任务会导致本块实验被拒绝；只清理在实验上下文创建的任务，不碰进程中的无关任务。取消处理必须合作，不能吞掉 CancelledError 后永久运行。
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

## 中断与恢复

CLI 每完成一整对实验就原子写入同名 `.checkpoint.json`。Ctrl+C / 任务取消时保留已完成配对；正在进行的半对不算完成。完成报告只在全部测量成功后覆盖，失败不会把半成品伪装成新结果。

```powershell
python -m awaitlab demo --scenario parallel --output artifacts/my-run.json
# 中断后，保持代码和参数一致：
python -m awaitlab demo --scenario parallel --output artifacts/my-run.json --resume
```

SDK 方式：`await experiment.run(checkpoint='run.checkpoint.json', resume=True, workload_version='fixture-v1')`。断点绑定设置、运行环境、库源码、workload 与 replacement 所在的已知源码文件，以及显式工作负载版本。开始与结束均核对已知代码，检测运行期间的源码变化。

外部数据、数据库状态、闭包配置和所有传递依赖无法自动完整指纹化，变更这些内容必须更新 workload_version；不要把文件哈希当作全环境可复现保证。断点不支持并发写入。同一路径不加 --resume 是重新运行，不复用旧配对。

进一步的方法审查和一手来源见 [METHOD.md](METHOD.md)。因果性能分析、异步追踪和实验统计都有前人工作，本项目未证明原创性，也没有宣称胜过 Coz、Pyinstrument 或 Codex。

## 验证与自身开销

```powershell
python -m unittest discover -s tests -v
python benchmarks/overhead.py
python benchmarks/paired_overhead.py
node --check awaitlab/assets/report.js
```

可选浏览器验收 `node tests/browser.cjs`，默认复用 D 盘现有 Playwright/Chromium，可用 AWAITLAB_PLAYWRIGHT 和 AWAITLAB_CHROMIUM 指定位置。应用不需要这些依赖。

当前微基准每组 30,000 次无 I/O 的空异步调用、7 次随机顺序重复。第一次自身优化将聚合追踪中位数从约 2.54 降到 1.78 微秒/调用；这是先后两轮微基准，不是业务整体加速或严格配对显著性证据。输出在 artifacts/overhead-v0.1.json 与 artifacts/overhead.json。该进程包含测量脚本的工作集约 27 MiB，不包含浏览器。

0.2 增加同进程、11 个随机配对批次的旧/新实现比较，冻结基线取自 0.1.0 安装包并记录源码 SHA256。当前测到约29%开销下降，均值差约 -0.72 微秒/调用，95% 配对 bootstrap 区间约 [-0.74, -0.69] 微秒/调用。原始数据在 artifacts/paired-overhead.json；仍只代表本机空操作聚合追踪微基准，不代表业务服务同比加速。

跨度记录有上限，聚合计数仍保留。延迟数组、输出摘要、批次结果和报告也会占内存，不能把“追踪有上限”说成整个实验内存恒定。报告 v2 删除重复首批数据与逐行哈希列表，保留整批摘要、不一致 ID 和逐批结果。

项目、构建后端、缓存、临时数据均放 D 盘；Python 运行时沿用现有安装位置。没有迁移 Codex 数据或系统目录。
