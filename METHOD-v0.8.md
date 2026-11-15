# 0.8：负面对照的角色与异常解释

0.7的24批次极短求和实验中，原函数作为替换实现，仍测得-7.50%、Holm p=.012099266，并被标为优化候选。这里有两个不同问题：计时变化的原因尚未确认；系统当时没有负面对照角色，所有replacement都按候选解释。0.8修复第二个问题，保留第一个问题及其原始证据。

## 固定协议复验，没有挑选通过的结果

benchmarks/negative_control_diagnosis.py在开始测量前写入plan.json：固定原seed173、24配对、8请求、并发1，每种配置8次；配置顺序用另一个固定seed9137随机安排。

| 配置 | 工作量 | 预热 | 采样请求 |
| --- | --- | --- | --- |
| short | sum(range(5000+i)) | 1 | 2 |
| long | sum(range(500000+i)) | 1 | 2 |
| warmup50 | 与short相同 | 50 | 2 |
| unsampled | 与short相同 | 1 | 0 |

每项只改变一个设置。驱动在禁用site-packages的环境中使用D盘已安装的0.7.0 wheel，逐文件核对安装内容与wheel，记录源码/包SHA、顺序与全部原始报告。32个原实现对照的raw p另组成预定诊断family作Holm调整，双向点变化至少5%且调整p < .05才报警；不把各运行内的2臂family与32臂诊断family混用。

32次均未再次被各自运行的旧规则判为支持，诊断family也无报警，包括原short配置的8次。各配置仍有正负波动。这个结果**不能确定原事件由预热、采样或其他具体因素造成**，也不证明后续一定稳定；系统负载、进程和OS缓存没有恢复成原事件当时的状态。没有继续加次数直到复现，也没有改seed覆盖旧结果。

完整数据在 artifacts/negative-control-diagnosis-v0.7.0/，包括plan.json、summary.json和32份原始报告。它是冻结0.7的后续诊断，不冒充0.8的性能测量。

## 可确定的呈现问题与修复

旧数据回放命令 `python benchmarks/negative_control_replay.py` 稳定返回RED：原实现对照的candidate_improvement为true。最小回归在Experiment.run的决策接缝提供确定测量值：即使传入带negative_control角色的Arm子类，旧引擎仍把该对照和另一个候选一起推荐。该测试修复前真实失败，修复后通过；没有靠不稳定的实时计时作测试断言。

新增Arm末尾可选字段role，默认candidate；replacement可显式声明negative_control。系统依赖接入者预先提供有意义的对照，不根据名称或函数表面推断。内置SQLite与客户HTTP的原实现对照已声明角色。--plan输出每个replacement的角色；checkpoint身份包含角色，不能只改角色后继续恢复旧测量。

```python
Arm('unchanged', 'replacement', 'sum',
    replacements={'sum': total.__wrapped__}, role='negative_control')
```

`__wrapped__`在此表示原先已装饰函数的原始实现；不要把同名已装饰包装器作为替换，避免递归。其他业务可提供等效的明确对照实现，输出核对仍只覆盖已测输入。

候选和负面对照仍处于同一个预定replacement Holm family；raw/adjusted p、效应、区间、原有evidence_level均保留。新增control_status与整轮quality：

| 对照情况 | control_status | 整轮解释 |
| --- | --- | --- |
| 输出不一致 | output_mismatch | warning，暂停所有候选推荐 |
| 任一方向点变化达到min_gain_pct，精确Holm p < alpha | change_detected | warning，暂停所有候选推荐 |
| 仅近似检验 | not_assessed | inconclusive，不伪装精确检查 |
| 未满足上述报警规则 | no_alarm_detected | 未检出异常，不是等价或功效保证 |
| 没有声明对照 | 不生成对照判定 | not_checked，不补造对照已通过 |

负面对照的candidate_improvement始终false。warning也使其他候选该标志为false；原有数值规则分级不被抹掉，因此仍可审查为什么出现信号。默认未声明对照的旧接入保留原有候选行为。5%仍是点估计门槛，不是改善或等价的置信界限；实际门槛取Settings。

## 原异常数据的解释回放

`python benchmarks/replay_control_roles.py`读取原0.7报告，依据已知协议“unchanged使用原函数”补充角色，再应用新解释规则。输出标题、analysis_replay和合同均注明：这是**测量后的角色注释回放，没有新测量，不是原先已预注册角色的确认性证据**。

回放逐字段核对效应、区间、p、evidence_level和全部blocks完全不变，原文件SHA不变。原p=.012099266和-7.50%仍在；对照显示“检出变化”，整轮暂停候选推荐。新文件可用相同检测器检查：

```powershell
python benchmarks/negative_control_replay.py artifacts/control-role-anomaly-replay-v0.8.0.json
```

结果为GREEN。原历史文件仍保持原始RED证据。没有给历史实验名自动授予角色，也没有把“不报警”写成“通过”。

## 原生接入与限制

0.8以新SDK、预先声明角色独立运行同样24批次业务，完成48对恢复；公式候选约-84.95%，对照约-3.07%、p=.3560425、未检出异常。它与0.7分开保留，不解释为计时问题被治好。

真实客户API完成40生命周期与20对恢复。索引约-50.78%、Holm p=.00390625；原实现对照约+12.97%、p=.05078125，严格规则未报警。这个相邻门槛的结果也保留，并非“对照等价”或“实验绝无干扰”的证据，未为它放宽alpha。驱动峰值工作集约78.5MiB，不是服务内存上界。

负面对照只能检查预先选定的部分风险；报警不诊断具体原因，未报警不证明不存在问题。质量门槛只是减少误导性推荐，不消除多轮搜索、功效不足、观察者干扰或业务投影的边界。根本计时异常仍未稳定复现，不能写成已找到或修复某个计时根因。

99项单元/集成测试、85项浏览器检查通过；17个安装文件逐字节一致，独立-S环境中的原异常解释、32批次精确计数及CLI恢复通过。独立HTTP用户项目8生命周期/4对恢复，角色及其checkpoint身份保持正确。小p用科学计数法，短时延不再把.051ms和.047ms都显示成.05ms；显示精度不代表真实测量精度。
