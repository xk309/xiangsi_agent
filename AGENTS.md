# 项目约定

使用中文解释业务行为，代码命名使用完整清楚的英文。

## Agent skills

### Issue tracker
规格与任务使用 https://github.com/xk309/xiangsi_agent/issues ，规格为 #1，六个任务为 #2—#7。按阻塞关系推进；操作记录见 docs/agents/issue-tracker.md。

### Domain docs
本项目为单一业务上下文；改变业务术语前读取 CONTEXT.md。

### Testing
测试边界为检索计算公共接口、HTTP接口及完整页面操作。独立期望值来自V2.1算例；真实模型调用与离线替身验证分别报告。

### Data boundary
基础八表复用现有数据；只新增扩展表和写入本应用任务结果。首版为2025固定数据联调：合成日均气象和时刻值派生污染物统计量，不作为正式气象或AQI评价。密钥及数据库密码仅在Git忽略的本地环境配置中保存。
