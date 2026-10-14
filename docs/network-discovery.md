# 学校接口调查记录

2026-10-14，用户在程序打开的独立 Edge 完成官方统一认证，并操作学术报告列表、第二页和一条详情。程序捕获实际 JSON 请求，字段映射来自这些响应与 EMAP 模型说明。以下不含 Cookie、认证头、报告 ID、会议信息、附件令牌或个人数据。

原始域名：`https://yjs1.ustc.edu.cn`。无会话访问官方入口，实际跳转至 `id.ustc.edu.cn` 的统一认证。

## 已验证列表

`POST /gsapp/sys/xsbgglappustc/modules/xsbgxk/wxbgbgdz.do`，表单编码。实际参数：`*order=-BGSJ`、`pageSize`、`pageNumber`。浏览器使用每页 20 条；另以相同正常会话实测 `pageSize=100` 返回 100 条。

成功响应 `code="0"`。记录位于 `datas.wxbgbgdz.rows`，分页元数据为 `totalSize`、`pageNumber`、`pageSize`。实际列表总数 2,260，100 条/页完整抓取 23 页。

| 实际字段 | 内部字段/含义 |
|---|---|
| BGBM | 稳定报告编号 report_id |
| BGTMZW / BGTMYW | 中文/英文题目 |
| BGRZW | 报告人 |
| YXDM_DISPLAY | 院系显示名 |
| DD | 完整地点（读取原始 JSON，不读取表格截断文本） |
| BGSJ | 报告时间，未知保留 null |
| JZSJ | **选课截至时间**，映射 registration_deadline，不映射 end_at |
| SFKXK | 学校是否可选课标记；结合截止时间计算当前可选 |
| BZ | 备注 |

部分历史记录没有地点或报告时间；不猜测、不用截止时间代替开始时间。

## 已验证详情

`POST /gsapp/sys/xsbgglappustc/modules/xsbgfb/xsbgfbbddz.do`，表单参数 `pageSize=1`、`pageNumber=1`、`BGBM=<列表实际编号>`。

记录位于 `datas.xsbgfbbddz.rows[0]`；校验返回 ID 与请求 ID 一致。详情含 `DD`、`BGSJ`、`BGNR`、`BZ`、`BGRZW` 等。补查完整地点、正文/备注、实际报告时间；正文保留 HTML 链接、去除标签与 script/style。

为避免每次对所有历史报告做数千次详情请求，只为待参加、时间不明或手工关注的报告补查详情。本次补查 39 条。已知已开始的历史记录使用完整列表字段；历史线上计数不能保证发现仅在旧详情中的线上信息。

目前没有捕获可信的永久详情 URL。学校通过页面弹层和上述详情 JSON 展示报告。`detail_url` 保留 null，通知点击打开本地详情，原始报告按钮回退官方入口；不生成猜测深链。

## 完整性与认证

正常分页验证总数一致、页面不重复、相同 ID 内容不冲突、详情 ID 正确。总数中途变化、达到页数上限、详情失败、字段结构异常、401/403/认证跳转时不提交新快照。

实际 `code` 值与类型写入已观察到的本机 source 配置。API 读取只允许原始学校 HTTPS 域名，关闭自动重定向；Cookie 由 Playwright 按自身域名作用域附加，不打印或导出。

本机 source 由 `login` / `discover` 自动生成在 `.auth/source.json`；这里不提供虚构的备用 API。通用页面抓取适配器需实际确认页面/详情选择器后才能启用。当前真实接入使用 API。
