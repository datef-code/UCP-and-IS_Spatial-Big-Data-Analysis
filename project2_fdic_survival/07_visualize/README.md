# 07_visualize · ⑦ 可视化

> 项目：[project2_fdic_survival](../README.md)　|　规范：`datakit/PROJECT_STRUCTURE.md` §8 / §8.8

## 定位

| 登记项 | 值 |
| --- | --- |
| `stage` | `07_visualize` |
| `kind` | `visualization` |
| `depends_on` | `06_train` |
| `requires` | `metrics.json`, `shap_importance.csv` |
| `extras` | `modeling`（matplotlib） |
| `blocking` | `false` |

## 本阶段做什么

按 §8.8 出图：先选对图型 → 中文可用（微软雅黑）→ 双格式（PNG + PDF）→
统一落 `figures/` → `manifest.json` 登记每张图的口径与来源。

## 输入 / 输出

- **输入**：只读 `05_map/output/data/`（网点维度 / 银行脆弱性）+ `06_train/output/`
  （系数、SHAP、测试集预测、Moran's I）
- **输出**（本阶段 `output/`）：

| 产物 | 内容 |
| --- | --- |
| `manifest.json` | 图清单：文件名 → 标题（结论）/ 问题 / alt_text / 口径 / 来源 / n / 单位 |
| `figures/*.png` + `*.pdf` | 6 张图（位图 + 矢量） |

## 图目录（由 `manifest.json` 生成，勿手写第二份清单）

| 文件 | 标题（结论） | 图型 |
| --- | --- | --- |
| `01-baseline-hazard-by-year.png` | 危机后整合窗口，网点关闭率翻倍 | 小倍数折线（数据 + 模型年份效应，禁双 Y 轴） |
| `02-km-by-group.png` | 银行越脆弱，网点存活率越低 | 分组 KM 阶梯（脆弱性 / 类别 / 历史关闭率） |
| `03-shap-importance.png` | 年份之后，银行层因素最强 | 排序条形 |
| `04-roc-calibration.png` | 区分度良好，高危段概率略低估 | ROC + 校准折线 |
| `05-cloglog-forest.png` | 规模是护城河，地理分散更易被整合 | 系数森林图（点 + 95% CI） |
| `06-spatial-closures.png` | 残差仍有空间聚集，本地因素未进模型 | hexbin 密度 + Moran 注记 |

## 本阶段口径要点

- 样本：进入风险集的 140,751 个网点（左截断已剔除），右删失计入风险集。
- 中文字体：微软雅黑（`msyh.ttc` 注册 + `axes.unicode_minus=False`），PDF 内嵌 TrueType。
- 每张图带脚注（来源产物路径 + 生成时间）；`manifest.json` 记录 matplotlib 版本与字体。
