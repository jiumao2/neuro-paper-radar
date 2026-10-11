# Nature 访问量导入

[English](NATURE_IMPORTS.md)

已部署模块支持 Nature、Nature Neuroscience、Nature Methods、Nature Communications 的**经授权本地 HTML、CSV、JSON 数字导入**。**Nature 在线采集已禁用，尚未提供获准的生产数据导出文件。** 解析器可用不等于阅读量来源已连接。界面展示实际测量覆盖；访问量缺失时明确使用引用或最新日期。

## 来源边界与代码参考

[ScrapeJournal](https://github.com/danmonyak/ScrapeJournal/tree/0d9b84a214b7104b57fb7363791e4caacafdee9c) 采用 MIT 许可，其文章解析器定位普通文章页面的 `.c-article-metrics-bar__wrapper`。这不同于 `/metrics`；仅限制 `/metrics` 不能判断普通文章解析器是否可用。其下载脚本使用 Nature 搜索页面，并跳过数据库中已存在的 DOI，因此本项目不采用其采集和更新流程。

2026-10-11 核查的 [Nature robots](https://www.nature.com/robots.txt) 对 `ChatGPT-User`、`GPTBot` 禁止所有页面，一般规则还限制搜索及 metrics 路径。[附加条款](https://www.nature.com/info/additional-terms) 限制自动访问与复用。尚未核实允许本项目在线采集并公开转载数字的来源。导入器不会请求 Nature 搜索、文章、metrics 页面或替代端点，也不会使用代理或伪装身份。模块无需 API 密钥、付费服务、新凭据，也不联系出版商或导师。

本项目以 Python 标准库独立实现解析器与导入流程，未复制 ScrapeJournal 代码，代码继续采用 GPL-3.0-only。上游的 [MIT 许可](https://github.com/danmonyak/ScrapeJournal/blob/0d9b84a214b7104b57fb7363791e4caacafdee9c/LICENSE.txt) 适用于代码，不授予 Nature 内容或数据权利。

## 必须记录的授权

操作人员须核实**取得指定输入及公开转载其数字事实**的权利，并提供独立的本地授权 JSON。声明记录已存在的权利，本身不授予许可，也不会自动核实出版商合同。一般条款、订阅、成功的 HTTP 请求、上游代码许可或 robots 文件均不能作为数字转载许可。

以下仅为**不可直接运行的结构示意**，不代表授权或生产数据。替换占位符；仅在已核实对应权利后，将两个布尔值改为 true。私有授权文件、凭据、原始 HTML、输入导出文件应存放于版本控制之外，例如已忽略的 `scratch/`。只保存可公开引用的信息与数字事实。

```json
{
  "permission_url": "https://<公开许可或授权依据>",
  "permission_basis": "<已核实的具体数字采集及公开转载权利>",
  "license": "LicenseRef-ExplicitPermission",
  "verified_at": "<含 UTC 偏移的 ISO 时间戳>",
  "journal_ids": ["nature-neuroscience"],
  "collection_allowed": false,
  "redistribution_allowed": false
}
```

支持的数字许可标识为 `CC0-1.0`、`CC-BY-4.0`、`LicenseRef-ExplicitPermission`。授权范围使用精确的期刊 ID；依据链接必须为不含凭据或签名查询参数的公开 HTTPS 链接。Nature 首页、robots 和限制性一般条款不能作为转载许可依据。

## CSV / JSON 数字导入

CSV 列为 `doi,journal_id,accesses,observed_at,source_url,source_updated_at,source_label`。末三列可选：普通文章 URL 可按 DOI 映射；未知的出版商指标时间保持未知；来源标签默认为 `Accesses`，也支持 `Views`。不导入引用或 Altmetric，OpenAlex 引用保持独立。

JSON 接受同字段的数组，或 `{"schema_version":1,"records":[...]}`。记录不接受标题、作者、摘要、全文、任意附加字段或凭据。**DOI 必须已存在于官方出版商元数据中，精确期刊 ISSN 及授权范围均须匹配。** 是否进入可见语料库仍由既有神经科学分类和日期规则决定。

```sh
python -m ingest.nature_import --file scratch/authorized-counts.csv \
  --authorization scratch/verified-numerical-permission.json
```

`observed_at` 必须是实际来源观测时间，含 UTC 偏移。若来源提供 `source_updated_at`，它不能晚于观测时间。不以文件修改时间或导入时间代替来源时间，拒绝未来时间戳。

## 经授权保存的文章 HTML

HTML 的 DOI / canonical 元数据须指向同一篇文章。提供真实保存时间及已核实的期刊 ID：

```sh
python -m ingest.nature_import --file scratch/authorized-article.html \
  --authorization scratch/verified-numerical-permission.json \
  --doi '<已存在的核实 DOI>' --journal-id nature-neuroscience \
  --observed-at '<真实来源观测时间，含 UTC 偏移>'
```

不会请求任何 URL。HTML 上限 5 MB，只提取 DOI 身份和普通文章指标栏中的访问 / 浏览计数，不保存正文、摘要、作者或其他指标。缺少指标栏或计数会成为缺失观测，不导致崩溃。DOI 冲突、计数格式错误、重复指标栏数值冲突、未闭合指标栏会拒绝整个批次。搜索及 metrics URL 不能作为计数来源。

## 精度、更新和发布

精确的 `0` 是已测量零值；空值、缺失、`—`、`N/A` 保持缺失。`1.2k`、`2.3M`、`0k` 保留来源原始显示及近似标记，按展开后的 1,200、2,300,000、0 排序，界面显示 `≈` 和出版商舍入提示。不推断精确范围、阅读人数或统计截止时间。界面对精确计数的紧凑显示，与来源本身的舍入分开标记。

较新的 DOI 观测替换旧值，包括合理下降和零值，绝不相加。缺失或较旧观测保留上次有效计数、来源时间及许可依据。同一时间戳的冲突值拒绝整个批次。写入前验证完整批次及快照；错误输入不改变有效文件，修正后可正常导入。

只更新 `data/state.json.gz`、`public/data/papers.json`、`data/coverage.json` 中的已清理状态。保留来源 URL / 观测时间、可选出版商时间、导入时间、原始显示与精度、格式、输入指纹和公开许可依据。SHA-256 指纹用于追踪，不是许可证明。原始 HTML 与授权文件不会存入公开快照。

验证后，通过已获授权的仓库发布流程提交这三个文件。普通提交会触发验证及 Pages 部署；手动导入发布不要使用刷新工作流的 `[skip ci]` 标记。后续定时刷新保留并重新验证导入数据，不会请求 Nature。浏览器拒绝格式或来源信息错误的 Nature 快照，并保留上次有效缓存。
