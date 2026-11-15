"""Predeclared 24-pair real integer workload for the extended exact path."""
from awaitlab import Arm,Experiment,Settings
from benchmarks.inference_resolution import workload,formula,total

experiment=Experiment(workload,[
    Arm('formula','replacement','sum',replacements={'sum':formula}),
    Arm('unchanged','replacement','sum',replacements={'sum':total.__wrapped__})],
    Settings(blocks=24,requests=8,concurrency=1,warmup=1))
workload_version='integer-sum-extended-exact-v1-fixed-24-pairs'
title='预先固定24配对：真实求和替换与分治精确检验'
output_contract='核对每个请求的完整整数求和值；这是独立固定协议的新实验，未追加旧的6批次数据。'
