# AwaitLab v0.3 方法审查

审查日期：2026-11-15。本文是针对拟议协议的审查与实现建议，不声称产品已实现全部要求，也不包含新跑出的性能结果。沿用 METHOD.md 的闭环负载和输出一致性边界。未调用模型 API，未修改产品代码。

## 统计协议

以完整 block 为统计单位；block 内的请求共享事件循环、线程池和系统噪声，不能把请求数当独立重复次数。每个候选使用同一 block 配对的均值延迟 C_i、T_i，差值 d_i=C_i-T_i（正数表示改善）。主要检验统计量固定为 abs(sum(d_i))，不是对请求逐条检验，也不是在看到数据后挑均值、p95 或收益率中最显著的一项。

精确 sign-flip 需要条件：block 内两次执行的控制/处理顺序独立、公平随机；在无处理效应的零假设下标签可交换；没有跨执行残留影响。仅仅随机顺序并不能消除处理引起的跨 arm 缓存或后台线程残留。若不是依靠真实随机分配，而是将观察性配对差值直接翻符号，则还需零假设下差值联合分布对相应符号翻转不变；仅“均值为零”不够。这里拒绝的是该随机化零假设，不是一般异质分布下均值差为零的通用精确检验。SciPy 官方文档区分配对标签交换与重新配对，并给出差值翻符号构造。[配对置换与数值比较](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.permutation_test.html)

以下公式和分辨率是按上述设计直接推导的协议定义：

```text
S_obs = abs(sum_i d_i)
S(s) = abs(sum_i s_i*d_i), s_i in {-1,+1}
p_exact = count(S(s) >= S_obs) / 2**n
```

n<=16 时枚举全部 2**n 个符号向量，包含观察到的配置与其反号；相等值计入尾部。完整枚举不再加 1。d_i 全为零时 p=1。浮点比较须事先定义一个仅处理舍入误差的容差并记录规则，不能按显著性调容差。使用 abs 统计量定义双侧，不能再乘 2。

n>16 时可独立均匀、有放回抽样 B 个符号向量，并使用 p_mc=(b+1)/(B+1)，b 为“至少同样极端”的抽样数。固定并记录 B、seed、b 和近似方法；不能输出 0，也不能拿枚举公式 b/B 代替。不要因为 MC p 刚好过线就自动称为确认；可报告二项抽样不确定性（对有放回独立抽样成立）。SciPy 的双侧默认定义是双倍较小尾；本文采用 abs 尾部，MC 时尤其不可不加说明地混用。上述链接支持 +1 规则与数值边界提示；本段为工程协议选择。

固定 family 包含本次实验预先列出的全部 replacement arms。按原始 p 升序排列 p_(1)...p_(m)，Holm 调整为：

```text
p_adj_(i) = min(1, max_{j<=i} ((m-j+1)*p_(j)))
```

恢复原 arm 顺序输出。共享 control 导致的检验间相关性本身不妨碍 Holm；但每个原始 p 必须先有效。不能先剔除无收益或输出不符的候选再缩小 m；无效候选不授予收益结论，可保留原 family 槽位并按 p=1 作保守调整。Holm 只覆盖这个预先固定的 family，不覆盖反复更换 seed、block 数、负载或候选直到过线的搜索。[R stats 官方 p.adjust：Holm 与 family-wise error](https://stat.ethz.ch/R-manual/R-devel/library/stats/html/p.adjust.html)

随机化设计必须与检验一致：本次实现者说明，每个候选在各 block 都拥有自己 fresh control 与 fresh treatment，并单独公平随机先后，不共享 control；该设计与上述二元翻符号空间一致，前提仍是没有残留干扰。若未来改成一次随机排列多个 arms 并复用 control，须重新核实联合分配。固定平衡先后次数的设计也不等于独立抛硬币，枚举空间需与实际分配规则一致。

按公式计算，6 blocks 的最小非零双侧精确 p 是 2/64=.03125（零差值和并列只会使分辨率更差）。若 family 有两个 replacement comparisons，最小 Holm 调整值为 .0625，因此默认六块无法有任何候选达到 .05；这是设计分辨率所限，不能解释成“优化无效”。单个 replacement 对 control 的两臂实验 m=1，则不受该两比较倍数限制。预先增加 blocks 可以改善分辨率；不要看到未过线才追加并仍按固定样本检验解释。

## 候选标签与区间解释

推荐将 verified_improvement 改成明确的探索性候选标签。候选条件同时满足：所有预期 request ID 均有且仅有一份完整成功输出并与 control 规范化 JSON/hash 一致；预先定义的改善点估计至少 min_gain_pct（默认5）；有效的 Holm p_adj<alpha（默认.05）。MC 路径另标 approximate/exploratory，不自动称已确认。检查配置为有限值，alpha 在(0,1)，说明 min_gain_pct 的单位是百分数。

必须固定改善率的估计目标，例如 G=100*(mean(C)-mean(T))/mean(C)。mean(100*(C_i-T_i)/C_i) 是另一个估计量，不应混用。保留 block 配对 bootstrap CI 可用于展示，但注明估计量、重复次数、seed 及少块不稳定性；未经 simultaneous 校正的单臂 CI 不能充当 family 级覆盖保证。

“点估计>=5%且零效应检验显著”不证明真实改善至少5%；要支持该下界，需要针对5%阈值的假设/区间及多重性方案。输出一致仅覆盖本次观察输入，不是语义等价证明。结果仅适用于记录的输入、并发、连接策略、环境和闭环负载；不推断生产开放到达率尾延迟、其他负载或全域性能保证。默认文案用“此负载下的探索性候选，点估计X%，Holm调整p=Y”。未通过应写“证据不足/未满足候选规则”。

## SQLite 案例：公平性与实现陷阱

建议以固定 seed 生成一份数据，再 backup 为两份 DB，仅在 treatment 建立事先声明的 email 索引。先完成建库、建索引及决定好的统计信息步骤，再关闭写连接。记录逻辑行数、按 id 排序的数据摘要、schema、索引定义、SQLite/Python 版本、page_size、cache_size、mmap_size、journal_mode、automatic_index 与统计信息策略。文件二进制 hash 不可能因有无索引而相等；核对逻辑数据与请求输出。

两边执行同一参数化 SQL（同列、WHERE email=?、ORDER BY 唯一 id），固定 request ID 到键的映射，含明确比例的无命中与重复命中键。必须消费全部行，不只创建 cursor。连接在工作线程内部创建、使用，并用 finally 显式关闭；只用连接的事务 context manager 不等于关闭连接。只读连接仍需报告连接/SQL 编译成本是否包含在请求计时里。@operation 包住 await asyncio.to_thread(...) 时，测到的是提交、线程池等待、开关连接、执行、取回结果的总跨度，不能命名为纯 SQL 执行时间。

SQLite 的 page cache 参数对当前 session 生效，重开连接会恢复默认。由此推断：每请求新连接时，预热连接的 SQLite 私有 page cache 不能当作后续请求继承的暖缓存；预热更可能主要影响 OS 文件缓存。两份 DB 都全表扫描也不保证 treatment 索引页被访问；索引、表、文件大小和全表扫描的物理成本不同。[SQLite PRAGMA：cache_size、mmap_size 与 optimize](https://www.sqlite.org/pragma.html)

建议把缓存条件写为“统一预热协议下、短连接的本机读实验”，不要称完全相同或可证明全暖。预热时真正遍历数据表并消费结果，不能假定 COUNT(*) 必然读全表数据；再对两臂以同一请求键序列做不计时查询预热，使索引访问路径也被覆盖。每次执行前采用相同协议，并独立记录/平衡预热顺序；数据与索引总量应足够小以减少互相驱逐，否则承认缓存竞争限制。建索引带来的初始缓存热度须经统一预热处理。不要在计时期间执行 ANALYZE/optimize，也不要只给某一臂额外的优化步骤。这里只声明具体缓存协议，未验证 OS 实际命中率。

EXPLAIN QUERY PLAN 可以保留原始行和 SQLite 版本，作为人工诊断索引是否被使用的证据。官方明确说其输出格式可变，曾跨版本变化；禁止断言完整字符串恒等、依靠固定节点编号或把包含“INDEX”当正确性/收益认证。SCAN 也可能是索引扫描，SEARCH 表示访问子集，不等于必然更快；检查 WHERE、排序和覆盖索引的实际含义。[SQLite EXPLAIN QUERY PLAN 官方限制](https://www.sqlite.org/eqp.html)

Python 默认 executor 会惰性创建。由此建议：正式计时前使用相同 executor，并以足够重叠任务预热到预期并发；单次 no-op 不保证所有线程创建。固定/记录线程池 max_workers，等预热任务全部结束，control 与 treatment 共享一致策略。不要将线程初启成本偶然全算给先运行的臂。新建 workload 不意味着新建进程、线程池或 OS 缓存；报告实际重置边界。[Python 官方 executor 生命周期](https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.run_in_executor)

所有上一 arm 的 to_thread 调用必须真实完成，才可开始下一 arm 或清理 DB；取消 await 不应被误当作底层线程已经停止。异常、遗漏、重复 request ID、超时或部分输出不得被成功请求均值掩盖。hash 核对在计时区间外统一完成，或者明确两边都包含相同序列化成本。该案例验证的是短连接+线程池查询这一个真实替换，不代表长连接池、写事务或模型服务性能。

