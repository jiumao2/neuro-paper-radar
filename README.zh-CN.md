# NeuroPaper Radar 神经科学论文雷达

[English](README.md) · [GNU GPL v3](LICENSE)

**[打开 NeuroPaper Radar](https://jiumao2.github.io/neuro-paper-radar/)**

发现神经科学预印本与已发表论文的开放、双语静态应用。架构受到 [biorxiv-top](https://github.com/RobertoDF/biorxiv-top) 的启发；本项目独立实现，未复制其代码或界面。

使用 Python 数据采集、TypeScript 前端、GitHub Actions 和 GitHub Pages。生产元数据来自 bioRxiv、Crossref、OpenAlex 和 PLOS 官方 API。期刊为 Nature、Nature Neuroscience、Nature Methods、Nature Communications、Journal of Neuroscience、eLife、PLOS Biology、PLOS Computational Biology 和 PLOS ONE，以稳定的 ISSN 标识；综合性期刊保留神经科学分类依据。

## 指标与日期

预印本默认按真实原始阅读量排序，来自公开的 [biorxiv-top 数值快照](https://github.com/RobertoDF/biorxiv-top/blob/data/usage.json)：已有月份的全文浏览与 PDF 下载之和，保留来源提交、上游采集及本项目获取时间。仅重用 DOI 对应的数值事实；标题、作者与首次发布日期仍来自本项目的官方元数据采集。上游仅覆盖近期论文及部分月份，当月尚未结束，不能保证完整生命周期或全部版本覆盖；次数不是独立读者人数。发布日期筛选的是论文，而非阅读事件日期。

默认隐藏已有相关已发表 DOI 的预印本，可通过开关显示；没有发表链接不等于确认未发表。支持 OpenAlex 引用次数与最新日期排序。缺失值与来源报告的零值严格区分；缺失值排在有测量值的论文之后且无排名。当前筛选全部缺失阅读量时，界面明确回退至引用次数，若也全部缺失则按最新日期浏览。已发表阅读量使用允许重用的 PLOS 与 eLife 官方 API，原有五个期刊的访问量仍不可用；不虚构数据、不抓取受限页面、不使用未授权 Altmetric 数据。跨来源原始指标不能完全直接比较。

PLOS 使用来源定义的累计总浏览量作为主指标，过去 30 天浏览量单独展示。每条 PLOS 记录标注“Data Provided by PLOS”。来源报告的零值可能尚待索引更新，索引时间不是保证的指标截止时间。所有 PLOS 请求共用间隔 12.1 秒的串行队列，每次最多 100 条，遵守每分钟、每小时与每日限额。

eLife 使用官方累计 `totalValue` 页面浏览量，不使用分页首屏之和；下载量单列。计数汇总 eLife 所有版本，包含正式发表之前的经评审预印本。仅官方历史确认 `status=vor`、`stage=published` 的记录进入“已发表”；保留首次正式版本日期及更早的经评审预印本日期。版本 DOI 后缀归并为一个文章 ID。受限队列与缓存保留有效计数，并报告待处理记录。

预印本按首个 v1 发布日期筛选；已发表论文按核实的首次在线发表日期筛选，不使用入库或采集日期。保留版本历史及相关已发表 DOI；自动主题分类的不确定性明确展示。

## 许可与来源权利

本项目原创代码采用 **GPL-3.0-only**，全文见 [GNU 通用公共许可证第三版](LICENSE)。该许可不重新许可第三方论文或元数据。OpenAlex 元数据为 CC0；Crossref 元数据可重用，但摘要并非一概可重用。bioRxiv 摘要仅在已记录的许可允许再分发时展示，否则链接至原始来源。每条记录保留来源信息，不使用受限出版商内容或未经核实的访问量接口。

## 运行与验证

需要 Node.js 24 和 Python 3.12+，Python 无额外依赖，不需要 API 密钥。

```sh
npm ci
npm run dev
python -m unittest discover -s tests -v
python -m ingest.validate
npm run typecheck
npm run lint
npm test
npm run build
npx playwright install chromium
npm run test:browser
python -m ingest.refresh --mode backfill
```

已有系统 Chromium 时可设置 `PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium`。测试样本明确标记为测试数据，绝不进入生产数据。

生产快照位于 `public/data/papers.json`，实际覆盖报告采集后保存为 [data/coverage.json](data/coverage.json)，压缩的上次有效来源记录位于 `data/state.json.gz`。无效刷新不覆盖有效快照；API 故障保留旧记录并显示故障状态。浏览器 IndexedDB 也可在后续加载失败时提供上次有效快照。

共享 API 客户端在 30 分钟时间预算后停止发起新请求，计入限流等待与重试。在工作流 40 分钟期限前验证并保存已成功获取的部分记录；未完成任务与陈旧来源会明确标记，并在后续刷新继续处理。

近期元数据、eLife 指标和未发现正式出版版本的 eLife 历史缓存五小时。这可以避免短时间重复刷新，同时为采集耗时和调度延迟留出余量，使下一次六小时计划任务按期更新。

## 自动化与部署

GitHub Pages 的来源设为 **GitHub Actions**。[验证与部署](.github/workflows/verify-deploy.yml) 执行 Python 测试、数据验证、TypeScript、lint、单元测试、桌面与手机浏览器流程及无障碍检查，然后构建并部署。不会部署空的初始化快照。

[官方数据刷新](.github/workflows/refresh.yml) 每天 UTC `00:17`、`06:17`、`12:17`、`18:17` 执行。单一计划统筹元数据、每日引用和每周修复。每个来源单独记录完整回填成功时间，单个来源故障不会导致成功来源反复全年回填。Actions 可手动选择刷新模式。刷新仅提交快照、覆盖报告和有效来源记录，然后部署。GitHub 可能延迟任务，或停用不活跃仓库的定时任务。

权限按任务授予：一般验证只读内容，只有刷新任务可写数据，只有部署任务具有 `pages: write` 和 `id-token: write`。Actions 固定在已核实的上游提交。无需付费服务、新建账号、持久凭据或客户端密钥。站点 `build-info.json` 记录实际构建提交、工作流及数据时间。

默认时间为 **过去 30 天**。今天使用 UTC 日历日期；过去 7/30 天包含当天与此前 6/29 天；月/年窗口按日历回退，并处理月底与闰年。筛选保留在 URL 中，中英文选择在本地持久保存。论文标题、作者与主题名称保留原文。

分类规则、指标定义、许可与适配器要求见 [来源政策与限制](docs/SOURCES.md)，维护要求见 [AGENTS.md](AGENTS.md)。

已发表列表按出版商登记的 `journal-article` 类型收录，可能包含更正、评论或编辑讨论，并非仅限原创研究论文。

[官方接口结构检查](.github/workflows/provider-contract.yml) 仅在适配器修改或手动触发时执行四次有界只读请求，不另设定时任务。生产刷新后的在线验证要求四个新增期刊均有真实阅读量测量。
