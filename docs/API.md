# 接口

模块GET使用仓内样例，模块POST可传csv或rows与context，直接计算当前规则。/api/runs使用完整流水线并原子保存。每个阶段返回rows、quarantine、metrics；后续阶段还返回累计隔离。/api/upload接收multipart文件file。/api/runs/<id>/archive只导出一份带清单与证据的CSV。

POST /api/runs/<id>/seal封存签证：返回业务校验值、业务事实与运行记录（分开列出），首次封存201，同一来源重试200且不重复封存；归档失败保留旧版。GET /api/runs/<id>/seal查看已封存结果，未封存返回404。业务校验值可对facts规范化串重算sha256复核。
