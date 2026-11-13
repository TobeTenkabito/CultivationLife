# 3888部通用功法书名重写

2026-11-14，重写全部 `TECH_OPEN_` 书名，保留前370部固定功法。完整对照：[Markdown](names.md) · [JSON](names.json) · [命名校验](validation.json)。当前4258部功法的描述与专属规则仍可在[完整设计目录](../technique-design-4258/techniques.md)按新名查阅。

## 命名来源

新名逐项存放在[道修](../../tools/data/common_titles/dao.txt)、[魔修](../../tools/data/common_titles/demonic.txt)、[妖修](../../tools/data/common_titles/monster.txt)、[鬼修](../../tools/data/common_titles/ghost.txt)四份完整书名表。每行一个灵根系列，每组对应一阶，组内依次是修炼、辅助、杀伐。每个词都是完整标题；读取器不再组合双字意象和统一尾词，也不补数字处理重名。

道修侧重观物、内景、修持与山川意趣；魔修侧重逆取、刑罚、饵气与执念；妖修侧重物种、身体动作、巢穴与溯祖；鬼修侧重旧物、遗愿、丧葬、记忆与幽冥。书名保留金木水火土、风雷阴阳的意象，但不强制同组共用开头或统一字数。

硬性校验：3888条全部改名，完整4258部目录不重名；同组不共用双字开头；不存在仅替换“经／诀／录／篇／法／书／典／藏／图／术”尾字的同题名。字数、前缀统计用于复核，不把统计结果等同于文学质量。通用题材词允许重复。

## 接入与保持

只改变目录 `name`。原ID、道途、品阶、灵根条件、类别、成长、数值、专属战斗规则、法力消耗、描述文本与7938条流通记录保持。新书名不赋予字面暗示的复活、传送等额外能力。

旧藏书、装备、货架及玉简复用现有按ID同步目录的入口；学习等级、数量和价格继续属于原记录。自创功法、自命名物品和历史文字保持。没有新增存档字段，不更改结构12兼容范围，也没有批量改写用户存档。

设计目录同步新书名，但保留原设计输入的SHA256作为历史证据，并在 `source.title_revision` 单独记录本次审阅清单及其摘要。除此以外，设计条目与编译效果保持。

## 维护与验证

- `python tools/generate_common_techniques.py`：核对完整书名表与离线目录。
- `python tools/design_techniques_4258.py`、`python tools/compile_fixed_techniques.py`：核对设计分册与实战编译内容。
- `python tools/export_common_technique_titles.py`：核对清单、重名及完整对照文件；`--write`重新导出。
- `python tools/export_common_technique_titles.py --verify-original-values`：对比本次改名前非名称字段、原370部与流通目录的语义摘要；这是本次改名的专项验证，后续获准调整机制或数值后不应冒充仍通过旧快照。
- `tests/test_technique_names_332.py`：旧名真实加载、属性与等级保留、玉简合参、自命名文字及完整目录名称校验。
- `tests/browser_handbook_revision.py`：两套当前像素主题、桌面与窄屏真实加载、读书、合参和检索。

全局书名唯一性是本固定目录的约束；动态道统、自创作品或玩家自命名文本不在这3888条清单内，不借本次改名重抽它们。
