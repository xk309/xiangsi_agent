# 上海污染过程相似度匹配

2025固定数据联调应用：选择预测批次和连续1—7天，联合检索Top50、数值精排Top10、生成四类气象图，再使用可配置Qwen多模态接口复核并输出Top3/Top1。

## 运行

需要 Python 3.11+、Node.js 20+、现有PostgreSQL兼容PolarDB与已入库的八张业务表。

1. 将 `.env.example` 复制为 `.env`，填写数据库密码与模型密钥；配置气象NC路径。已有本地 `.env` 时直接编辑，勿覆盖。
2. 执行 `python -m pip install -r requirements.txt`。
3. 进入 `frontend`，执行 `npm install` 和 `npm run build`，再回到项目根目录。
4. 执行 `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`。
5. 浏览器打开 http://127.0.0.1:8000 。接口说明在 http://127.0.0.1:8000/docs 。

Windows可在安装依赖并构建后使用 `start.ps1`。默认只监听本机。应用为单进程、单后台匹配任务模式，不使用多个worker或自动reload运行任务。服务重启会将上次未完成任务标记为失败，已保存结果仍可回看；重新创建任务可以复用相同输入的图像评分缓存。

开发前端可在 `frontend` 执行 `npm run dev`，API代理到8000端口。生产预览使用构建后的同源页面。

## 数据口径与边界

- 复用 `similarity_match` 内现有八表；启动只创建缺失的三个扩展表，不重建或导入基础数据。需要扩展表建表权限，以及任务和结果写入权限。
- 气象为合成日均场，不是09:00真实预报。污染物为时刻值派生统计量，O3不是合规MDA8。页面持续显示此边界。
- 固定2025数据用于统一基准联调；季节标签沿用已确认入库口径，数值均值、样本标准差及变化容差由完整可用库计算，不声称无未来数据的历史回放。
- 日期选择取同一批次首个完整日期起七个自然日内的真实覆盖，不拼接缺日；历史窗口早于查询窗口与任务日，按自然日去重。
- 最终分由程序合成：污染物60%、气象数值20%、图像20%。模型提供分项与证据；缺少完整Top3时为部分完成，不产生正式Top1。
- 模型失败重试一次，并从固定Top50中按数值排名补位。未启用模型时可查看数值候选及四图，不生成最终排名。
- 历史误差只按相同站点、污染物及预报日序关联；2025同源新模型为测试前提，既有表缺少模型版本字段。未通过独立回放，不启用定量订正。
- 扩展表 `match_task_evidence` 保存任务输入、基准和分项快照；`match_image` 保存PNG与哈希；`match_image_review` 保存模型原始响应、验证结果和缓存键。源数据替换时新任务会重新计算，已有任务保留其证据。
- 密钥只在后端 `.env` 或环境变量中读取，不进入前端、Git或接口响应。应用不含登录系统，仅适用于本机联调。

## 核心接口

| 接口 | 用途 |
|---|---|
| GET /api/health | 数据、模型配置状态 |
| GET /api/batches | 起报批次与可选日期 |
| POST /api/tasks | 新建后台匹配任务 |
| GET /api/tasks | 最近50项任务 |
| GET /api/tasks/{task_id} | 状态、分项、图像引用、对比值与误差 |
| GET /api/images/{image_hash} | PNG原图 |
| GET /api/reviews/{cache_key} | 模型原始响应与评分证据 |

任务创建请求字段为 `forecast_start_time`、`window_start_date`、`window_end_date`、`should_review`。日期格式 `YYYY-MM-DD`，批次时间使用接口返回的北京时间字符串。

## 验证

在项目根目录运行 `python -m unittest discover -s tests -v`；在 `frontend` 运行 `npm run build`。公式期望值来自V2.1配套算例，离线测试不会调用付费模型。

规格与任务：https://github.com/xk309/xiangsi_agent/issues/1 。
