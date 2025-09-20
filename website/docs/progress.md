# 当前进展与后续推进建议

## 当前进展（v0 站点雏形）
- 完成网站脚手架（MkDocs Material），目录位于 `website/`。
- 信息架构：已生成首页、快速开始、功能、示例、架构、故障排查、贡献、路线图、方案。
- 自定义样式：`docs/styles/overrides.css`（Hero、CTA、卡片、画廊、品牌栅格、动画）。
- 首页强化：Hero + CTA、功能卡片（含图标）、“信任与指标”徽章区、对比表、合作方 Logo 栅格。
- 图标与增强：启用 `pymdownx.emoji`（Material 图标），示例页使用 Tab 视图（CLI/MCP/API）。
- 资源占位：Logo/Favicon、CLI/API/MCP 截图、品牌 Logo 占位图。

## 建议的下一步（优先级从高到低）
1) 品牌与视觉
   - 替换真实 Logo/Favicon；根据品牌色微调 `--brand-primary` 与 Hero 渐变。
   - 选择 2–3 张真实截图（CLI、API、MCP）替换占位图。
2) 内容完善
   - Quickstart 增加“常见错误”短列表；Examples 增补 1–2 个端到端示例。
   - Architecture 配图（PNG/SVG）替换目录示意，突出双模式与核心共享。
   - Troubleshooting 增加更多 MCP/代理案例与日志排查指引。
3) 文档/多语言
   - 考虑英文镜像（en/）以覆盖海外开发者；或先添加英文首页。
   - 增补“命令参考”与“配置参考”板块，指向 `simacode` CLI 与 `.simacode/config.yaml`。
4) 部署与 SEO
   - GitHub Pages 部署：添加 Actions 工作流（构建 + 发布）。
   - 自定义域名与 Open Graph/Twitter 卡片（社媒分享预览）。
   - 可选：站内搜索优化、站点地图。
5) 观测与反馈
   - 轻量统计（如 Plausible/Umami）；
   - 在首页或页脚添加反馈入口与 GitHub Issues 链接。

## 本地预览与部署
- 本地预览：
  - `pip install mkdocs-material pymdown-extensions`
  - `cd website && mkdocs serve` → http://127.0.0.1:8000
- 部署（GitHub Pages）：
  - 手动：`cd website && mkdocs gh-deploy`
  - CI：添加 GitHub Actions 工作流（建议后续由我补充）。

## 备注
- 所有文件已集中在 `website/`，便于独立维护与部署。
- 如需更贴近 Continue 的视觉，可继续增强首屏的对比度与插画风格（保持轻量 CSS）。
