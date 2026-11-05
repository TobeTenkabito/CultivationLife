# 师徒系统对抗审计（2026-11-05）

范围为[师门第一批](mentorship-stage1.md)、[传承、化身与叛师](mentorship-stage2.md)，以及旧关系入口、永久离界与原人物战斗结算。未修改用户存档，未升级版本或打包；本体仍为3.5.2、存档结构12。

## 复现与修复

修复前首轮8项对抗用例中7项失败、1项通过，证据为 `build/mentorship-audit-before.log`。

| 问题 | 修复与边界 |
| --- | --- |
| 旧师父已故仍占用拜师关系图，拒绝拜新师 | 关系图排除已故人物；成功拜入新师时先结束旧师承，保留原赠物履历。普通收录、事件收录与引导收录共用此入口。 |
| 反叛者战力次序改变会重置预警年 | 按参与者ID集合判断是否为同一批人；同一组合排序变化不延后预警，成员变化仍重新预警。 |
| 挑战师父获胜但师父元婴逃生，被误判为失败 | `victory_escape` 按获胜交接个人师承，原人物逃生仍沿战斗结算；败北、存活败退、受控、僵持均不得接管。 |
| 挑战失败后师父仍保持原好感 | 实际挑战结算后，无论胜败均转为敌对；资格失效的过期请求仍在战斗与扣费前拒绝。 |
| 旧问罪逐出等操作仅删除关系，留下活动师承与契约 | 逐出、拘禁决裂、归墟决裂、活傀／炼尸、转侍妾、旧攻击接口共同结束原师承，撤销契约和同盟；保留已用精修凭据，不因改关系返还额度。 |
| 永久离界直接清空关系，丢失赠物履历及契约收尾 | 在权威永久迁界准备入口逐一结束原关系，归档唯一原关系附属数据。临时跨界与人物迁移规则不变。 |
| 凡阶化身只有战力贡献、缺少真实伤势结算 | 化身、师门比试及叛师战保留既有逐人战斗层，即使未启用高阶能力也提交原NPC伤势／资源。普通战斗仍显示标准自动战斗，不虚构高阶能力。 |

额外怀疑的“突破事件打断年度流程导致化身漏算年龄”未复现：已有地区年度入口会推进受控人物时钟，保留回归用例，本次未改时钟实现。

离门履历只保存原关系附属信息，不复制NPC、资源池或人物属性；转侍妾不把已归档赠物再复制一份。再次收录沿原逻辑消费该履历并移回当前关系。没有新增持久字段或跨界例外；归属说明同步到[逐字段合同](world-transition-state-contract.json)。

## 验收

- 师徒两批及本轮对抗测试：`tests/test_mentorship.py`、`tests/test_mentorship_advanced.py`、`tests/test_mentorship_adversarial.py`。覆盖真实拜师保存／加载、赠物单份归属、旧关系处置、无效请求不扣费、战斗结果分支、真实化身受伤，以及永久离界后的存档往返。
- 跨界、空间符箓、2.1.1／2.1.2、玩家战斗、NPC战斗生命周期、身魂与拘管共233项通过：`build/mentorship-audit-boundaries.log`。
- 对抗用例、侍妾、归墟同行、教程及依赖结构共129项通过：`build/mentorship-audit-legacy.log`（其后补充的旧攻击结算分支纳入最终师徒测试）。
- 新浏览器对抗：真实宗门按钮拜入新师、旧问罪事件加载／选择逐出、原赠物保留：`tests/browser_mentorship_adversarial.py`，结果见 `build/mentorship-audit-browser.log`。
- 两批原浏览器：桌面1440与手机390的实际收录、晋位、旧福利按钮、生成师父事件、契约、精修、化身开关、过期页恢复、叛师事件提交和战斗动作回放均通过：`build/mentorship-audit-old-browser.log`、`build/mentorship-audit-advanced-browser.log`。
- 原事件浏览器低内存模式通过桌面／手机、拦截、过期恢复、奖励和失效按钮验证：`build/mentorship-audit-events-browser.log`。

最终师徒复测记录在 `build/mentorship-audit-final-schools.log`；工程检查记录在 `build/mentorship-audit-contract.log`、`build/mentorship-audit-modules.log`、`build/mentorship-audit-docs.log`。这些是源码与浏览器验收，未进行本轮Windows／Android发行验收。
