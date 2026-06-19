# 梅森交易知识库 Skill

本仓库内置 `skills/mason-trading-knowledge`，用于把本地 `D:\梅森` 资料库转成交易知识索引、主题逻辑和盘中动作卡。

边界：

- 不上传原始 PDF、Word、Excel 或课程资料。
- 不自动交易，不连接券商，不承诺收益。
- 只生成索引、主题映射、动作卡和复盘材料。

本地更新索引：

```powershell
.\run_mason_library_update.ps1
```

安装每日自动更新任务：

```powershell
.\install_mason_library_update_task.ps1
```

默认每天 `21:30` 更新一次本地索引。

自定义资料路径：

```powershell
$env:MASON_LIBRARY_SOURCE="D:\梅森"
.\run_mason_library_update.ps1
```

输出默认位于：

```text
data\mason_library\mason_library_index.json
data\mason_library\mason_library_study_map.md
```

`data/` 默认被 `.gitignore` 忽略，避免把私人资料索引和摘要提交到 GitHub。

## 盘中使用方式

当用户询问：

- 这个题材/股票能不能买？
- 梅花庄这句话是什么意思？
- 这是不是双跌买点？
- 当前账户要不要加仓/减仓？

先从索引中检索对应主题，再输出：

```text
动作：买 / 不买 / 持有 / 减 / 清
触发：价格或盘面条件
失效：跌破/放量转弱/主题证伪
仓位：股数/份额/金额上限
风险：T+1、同方向拥挤、节假日、回撤金额
下次检查：时间或价格
```
