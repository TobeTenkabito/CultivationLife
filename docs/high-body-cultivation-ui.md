# 四道途高阶炼体界面与鬼躯专材

2026-11-03源码更新，仍采用结构12，无旧档迁移、升版或打包。界面沿现有修行导航：仙躯与五色神光、修罗魔躯与五蕴、独立妖躯、独立鬼躯。没有在邻域面板堆叠培养入口。

## 四道途外观

共用`web/body-cultivation-ui.js`及`web/body-cultivation-ui.css`，只生成DOM与外观，不结算养成。原四套命令、事件忙碌、过期快照、扣费与解锁规则仍由原权威入口执行。开关面板、滚动和查看图片不请求培养、不写档、不消耗游戏RNG。

| 道途 | 主视觉 | 修持内容 |
| --- | --- | --- |
| 仙 | 五色光谱、圆形玉印、五光各自配色 | 仙躯层数、五色神光十重修持 |
| 魔 | 赤金、棱角煞印、方形刻印 | 五十层魔躯、色受想行识五蕴 |
| 妖 | 青玉、骨金、带棱骨牌 | 妖躯五蜕、烈脏择一功能 |
| 鬼 | 幽青、轮环、虚线魂印 | 鬼躯五法及其对应专材 |

统一提供十层解锁进程、五段节点、每项十重刻度、已解锁／未解锁文字、库存与所需数量、缺额文字、真实报价和操作禁用原因。宽屏双列，手机单列，窄屏按钮整行；文字主题继续保留全部信息，关闭像素外观不请求专属图片。原烈脏选择、独修按钮和返回操作使用原控件及事件。

## 素材与绘制记录

五种材料均由内置`image_gen`分别生成，以现有`design/inventory-icons-v2-20261020/source/special_materials.png`及已采用妖躯魂珀立绘为风格参考。提示词要求硬边32逻辑像素、深色阶梯轮廓、左上高光、每表面3–5档色块、紧凑斜视轮廓、透明留白，禁止地面、投影、边框、文字、人物、光晕或平滑绘画。

| 对应 | 图稿ID | 视觉区别 |
| --- | --- | --- |
| 无相 | ghost_formless_amber | 带中空幽核的浅青矿珀 |
| 照业 | ghost_karma_mirror | 三折紫色镜面、古铜短柄冥镜 |
| 御魂 | ghost_returning_lotus | 五瓣幽青莲、三点紫色魂籽 |
| 忘情 | ghost_oblivion_crystal | 冰蓝泪晶、浅绯色内核 |
| 因果 | ghost_causality_thread | 赤金双环丝结、旧玉珠 |

原稿与工作提示词位于`design/ghost-body-materials-20261103/`。游戏成品、提示词和来源哈希全部在`dlc/ghost-reincarnation/assets/visual/body-materials/`，运行和打包不依赖design或生成缓存。可直接审阅[运行提示词](../dlc/ghost-reincarnation/assets/visual/body-materials/prompts.json)和[图稿来源](../dlc/ghost-reincarnation/assets/visual/body-materials/provenance.json)。

每种提供32×32 RGBA二值透明图标、128×128最近邻整数放大立绘。机械导出入口为`python scripts/prepare_wuyun_material_assets.py --family ghost-body --write`，日常验证使用`--check`，不重新生成图片。只做透明裁切、统一26像素主体和最近邻导出，不程序补绘。DLC视觉清单登记稳定语义ID、大小、SHA256及所有权；通过原受控`/extension-assets/official.ghost-reincarnation/`访问，停用时404，不借本体路径泄漏图稿。

## 验证

[鬼躯材料测试](../tests/test_ghost_body_materials.py)覆盖十一界货架与拍卖的产地限制、黑市真实购买与伪造异界报价拒绝、专材逐项扣除、后续重数费用、停用DLC及透明像素成品。原培养测试覆盖解锁、过期、缺材、寄身与已毁肉身边界。

真实页面验收使用`browser_divine_lights.py`、`browser_wuyun.py`、`browser_monster_body.py`、`browser_ghost_body.py`，覆盖桌面、手机、横屏及文字／像素主题，核实五段进度、十重刻度、真实提交、过期恢复、缺材禁用、立绘读取、只读开关和战报。事件旧页面仍运行`browser_events_212.py`。本轮源码验收不代替未来最终发行脚本要求的Windows与签名Android原生验收。

最终源码结果：`build/high-body-domain.xml` 209项领域测试、`build/high-body-boundary.xml` 174项边界测试全部通过；四套培养页面共13组主题／布局及旧事件页面真实点击全部通过，日志为`build/high-body-*-browser.log`。鬼躯页面另验证满重刻度、培养圆满文字与按钮停用。三项仓库门禁通过，依赖检查无循环；图稿通过二值透明、尺寸、最近邻同源、DLC归属和SHA256检查。四套界面截图分别保存在`build/divine-lights-browser/`、`build/wuyun-browser/`、`build/monster-body-browser/`、`build/ghost-body-browser/`。
