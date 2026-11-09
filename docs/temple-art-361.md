# v3.6.1 寺庙立绘

土地庙原先在场景营造图中回退为普通产业、在建筑详情共用佛寺图。现在按原建筑 `subtype` 与 `status` 选图，不新增建筑或存档字段。

- 土地庙完好／受损：`web/assets/building-portraits/land-temple-intact-361.png`。
- 土地庙毁坏：`web/assets/building-portraits/land-temple-ruin-361.png`。
- 佛寺继续按原等级使用 `web/assets/pixel/buildings/temple-1.png` 至 `temple-3.png`；毁坏使用 `temple-ruin.png`。

新图使用内置 OpenAI `image_gen` 生成，遗址图以完好图为编辑目标，保持同一建筑基址、视角与颜色。两张原始 1254×1254 RGBA 图片直接复制进项目，未做像素修改，透明通道保留。完整原始提示词、尺寸和 SHA-256 见[素材清单](../web/assets/building-portraits/manifest.json)。

场景营造、地图建筑详情和土地庙庙务标题区共用同一选图入口。未建庙时明确标注「奉建示意」，不表示已有建筑；遗址显示对应倒塌图；受损沿原状态提示。深浅主题均直接承载透明图，手机下缩为紧凑侧图，不增加操作按钮。
