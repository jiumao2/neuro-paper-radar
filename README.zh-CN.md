# NeuroPaper Radar 神经科学论文雷达

[English](README.md) · [GNU GPL v3](LICENSE)

**[打开 NeuroPaper Radar](https://jiumao2.github.io/neuro-paper-radar/)**

发现神经科学预印本与已发表论文的开放、双语静态应用。架构受到 [biorxiv-top](https://github.com/RobertoDF/biorxiv-top) 的启发；本项目独立实现，未复制其代码或界面。

使用 Python 数据采集、TypeScript 前端、GitHub Actions 和 GitHub Pages。生产元数据来自 bioRxiv、Crossref 和 OpenAlex 官方 API。初始期刊为 Nature、Nature Neuroscience、Nature Methods、Nature Communications 和 Journal of Neuroscience，以稳定的 ISSN 标识；综合性期刊保留神经科学分类依据。

## 指标与日期

支持原始访问量、OpenAlex 引用次数与发表日期降序。缺失值与真实零值严格区分。目前尚未确认允许自动采集和公开展示的逐篇访问量来源，因此访问量显示为缺失，访问量视图明确回退到引用次数，若引用次数也全部缺失则按最新日期浏览。不虚构数据、不抓取受限的出版商指标页面、不使用 Altmetric 未授权数据。跨出版商访问量即使可用，也不能完全直接比较。

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

## 自动化与部署

GitHub Pages 的来源设为 **GitHub Actions**。[验证与部署](.github/workflows/verify-deploy.yml) 执行 Python 测试、数据验证、TypeScript、lint、单元测试、桌面与手机浏览器流程及无障碍检查，然后构建并部署。不会部署空的初始化快照。

[官方数据刷新](.github/workflows/refresh.yml) 每天 UTC `00:17`、`06:17`、`12:17`、`18:17` 执行。单一计划统筹元数据、每日引用和每周修复。每个来源单独记录完整回填成功时间，单个来源故障不会导致成功来源反复全年回填。Actions 可手动选择刷新模式。刷新仅提交快照、覆盖报告和有效来源记录，然后部署。GitHub 可能延迟任务，或停用不活跃仓库的定时任务。

权限按任务授予：一般验证只读内容，只有刷新任务可写数据，只有部署任务具有 `pages: write` 和 `id-token: write`。Actions 固定在已核实的上游提交。无需付费服务、新建账号、持久凭据或客户端密钥。站点 `build-info.json` 记录实际构建提交、工作流及数据时间。

默认时间为 **过去 30 天**。今天使用 UTC 日历日期；过去 7/30 天包含当天与此前 6/29 天；月/年窗口按日历回退，并处理月底与闰年。筛选保留在 URL 中，中英文选择在本地持久保存。论文标题、作者与主题名称保留原文。

分类规则、指标定义、许可与适配器要求见 [来源政策与限制](docs/SOURCES.md)，维护要求见 [AGENTS.md](AGENTS.md)。

已发表列表按出版商登记的 `journal-article` 类型收录，可能包含更正、评论或编辑讨论，并非仅限原创研究论文。
