# NeuroPaper Radar 神经科学论文雷达

[English](README.md) · [GNU GPL v3](LICENSE)

发现神经科学预印本与已发表论文的开放、双语静态应用。架构受到 [biorxiv-top](https://github.com/RobertoDF/biorxiv-top) 的启发；本项目独立实现，未复制其代码或界面。

使用 Python 数据采集、TypeScript 前端、GitHub Actions 和 GitHub Pages。生产元数据来自 bioRxiv、Crossref 和 OpenAlex 官方 API。初始期刊为 Nature、Nature Neuroscience、Nature Methods、Nature Communications 和 Journal of Neuroscience，以稳定的 ISSN 标识；综合性期刊保留神经科学分类依据。

## 指标与日期

支持原始访问量、OpenAlex 引用次数与发表日期降序。缺失值与真实零值严格区分。目前尚未确认允许自动采集和公开展示的逐篇访问量来源，因此访问量显示为缺失，访问量视图明确回退到引用次数，若引用次数也全部缺失则按最新日期浏览。不虚构数据、不抓取受限的出版商指标页面、不使用 Altmetric 未授权数据。跨出版商访问量即使可用，也不能完全直接比较。

预印本按首个 v1 发布日期筛选；已发表论文按核实的首次在线发表日期筛选，不使用入库或采集日期。保留版本历史及相关已发表 DOI；自动主题分类的不确定性明确展示。

## 许可与来源权利

本项目原创代码采用 **GPL-3.0-only**，全文见 [GNU 通用公共许可证第三版](LICENSE)。该许可不重新许可第三方论文或元数据。OpenAlex 元数据为 CC0；Crossref 元数据可重用，但摘要并非一概可重用。bioRxiv 摘要仅在已记录的许可允许再分发时展示，否则链接至原始来源。每条记录保留来源信息，不使用受限出版商内容或未经核实的访问量接口。

后续实现、数据来源、验证结果、覆盖报告和部署说明将在此持续维护。
