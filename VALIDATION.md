# 0.2.0 验证记录

日期：2026-11-15。原始记录：artifacts/validation-v0.2.json。0.1版证据保留在 artifacts/validation-v0.1.1.json。

- 28 项单元/集成测试、12 项浏览器检查通过。
- 安装包与当前13个源码/资源文件逐字节核对通过；独立D盘目录中导出报告、完成实验并恢复2个完整配对。
- 新增真实127.0.0.1 TCP、HTTPX、Uvicorn、FastAPI链路。不是进程内ASGI模拟，也不是跨进程分布式追踪。
- 普通无票据请求清除偶然继承的干预；无效、复用及非本机票据均有测试。

## 受控测量结果

| 场景 | 实验臂 | 平均响应变化 | 已测输出一致 |
| --- | --- | --- | --- |
| parallel-latest | delay_inventory | -3.58% | True |
| parallel-latest | delay_pricing | +31.97% | True |
| parallel-latest | faster_inventory | +1.22% | True |
| parallel-latest | faster_pricing | -66.53% | True |
| fastapi-tcp | faster_inventory | -1.21% | True |
| fastapi-tcp | faster_pricing | -33.08% | True |

这些负载的业务等待仍是可控fixture，不是实际数据库或线上业务。负比例是指定负载下的响应下降，不代表工具自动让任意服务快这么多。

## 自身开销的更强复验

使用冻结0.1.0源码与当前实现，在同一进程内随机配对11批、每批30,000次无I/O异步调用，测得聚合追踪开销变化 -29.32%。均值差 -0.717 微秒/调用，95%配对bootstrap区间 [-0.7400131363636365, -0.6935712727272728]。基线源码SHA与每批数值见 artifacts/paired-overhead.json。只支持本机微基准结论。

## 中断与身份检查

真实CLI完整运行后使用 --resume 成功复用全部配对、不重新发送实验请求；单元测试另验证中断后只复用完整配对、取消半对丢弃、身份不符拒绝、校验和不符拒绝、测量期间源码变化拒绝生成完成状态。外部数据与全部传递依赖仍须由 workload_version 明确管理。

## 本轮剩余工作

实用收益阈值、多组比较校正、真实非sleep数据库负载及更方便的时间线过滤尚未完成，列入NEXT.md。未将目标标记完成。