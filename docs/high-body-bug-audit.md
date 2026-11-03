# 四道途高阶炼体缺陷与对抗审计

2026-11-03源码审计，覆盖仙修五色神光、魔修五蕴、妖修五蜕和鬼修五法。只使用临时测试角色与原战斗内账本，不读写用户游玩存档，不改培养数值、价格、版本或结构12兼容政策。

以下数值与统计为当时的缺陷审计记录；同日后续另按用户要求完成[首轮数值平衡](high-body-balance.md)和[缩差平衡](high-body-close-balance.md)，照业现为40%–65%，最新对抗与回归数据以缩差平衡报告为准。

## 已复现并修复

| 问题 | 修复后的边界 | 主要回归 |
| --- | --- | --- |
| 照业先拆基础比例再封顶，高威能时每段接近满强度 | 完整原段先计算威能、暴击、增益与上限，再继承40%–60%；固定派生攻击同样先封顶再拆段。语义事件的基础量仍报告实际分段比例 | `test_zhaoye_inherits_capped_original_power_instead_of_capping_each_scaled_part` |
| 首段被庇护解除覆盖，后两段仍追击原目标 | 后续每段重新校验存活、触及及原邻域合法覆盖；烈脏仍仅针对触发自己的实际施术者 | `test_sheltered_target_is_not_hit_by_later_zhaoye_segments_after_coverage_is_released` |
| 神游仍能借原肉身机制，NPC旧护体资格也会漏出 | 四体系共用真实占身判定；身体留在原处或已毁都不借其战斗机制。寄身仍先解析实际宿主，原养成账本保留 | 玩家四道途×身体完好／已毁，以及NPC四道途投影检查 |
| 身体修炼入口在神游时仍可能支付并培养原躯 | 高阶身体及独修入口在扣费前拒绝；仙躯页面的按钮可用性同步拒绝。普通神魂修行规则不变 | `test_high_body_cultivation_audit.py`四套真实命令、只读与文件字节检查 |
| 镇压把态势降至0时误发阵亡，触发御魂回复 | 镇压是非致死态势变化；后续明确合法诛杀仍可产生一次实际阵亡 | `test_body_death_is_not_fabricated_by_pure_state_suppression` |
| 续战丢失擒拿目的，恢复后默认诛杀 | 原快照保存目的、对抗比例、明确供给、封域日程及已执行封域标记，不重复执行封域 | 快照定向检查与全矩阵续战核对 |
| 劫战旧MP链路没有将场地与普通行动费用正确累计；虚影重凝还可补满封存容量 | 共用账本在轮首、普通行动及轮末同步真实比例；独立元府仍保持独立，封存容量不参与重凝补充 | `test_trial_legacy_mp_tracks_real_maintenance_plus_ordinary_spending`、可用容量检查 |
| 可反复重凝、原本不视为真实阵亡的耐久劫影给御魂发奖励 | 原耐久劫战为该场虚影显式登记不发阵亡凭据，重凝也不保留死亡标记；其它一次性镜像仍按真实本场击杀计算 | `test_reforming_endurance_manifestation_never_grants_yuhun_death_reward` |
| 低元力鬼修群战仅倒转人物列表，就改变因果爆发与胜负 | 展域扣费、普通资源预留、旧MP同步及施权以本轮先手、战力、稳定ID定序。默认覆盖按稳定ID，显式目标优先表保留；主MP链接优先原主战单位，不靠序列化顺序选择 | 四组合定向反序测试和全矩阵每轮反序核对 |

修复前的反例记录在`build/high-body-audit-initial.log`、`build/high-body-trial-audit-initial.log`、`build/high-body-roster-order.log`及`build/high-body-simulation-initial.json`。初版模拟断言曾把“先制伏、随后真的被诛杀”误判为异常，现改为检查实际死亡者不得复活；镇压误发阵亡仍由独立定向用例验证，未将这项测试断言修正算作玩法缺陷。

## 对抗方法

入口为`python scripts/simulate_high_body_combat.py --seeds 8`，结果写入`build/high-body-simulation.json`。使用实际四体系投影、内容数值、资源限制、轮首裁决及原`VoisinageBattle`结算；普通攻防输入是受控夹具，用来覆盖机制，不代替完整六维、装备和成长配置的正式平衡评估。

16种有向道途组合（含镜像）×0／5／10重×单挑／二对二×常规杀伤、单体、治疗、镇压、低元力、擒拿六种情形×8个固定种子，共4608场。奇数种子使用受限可用容量与旧MP链接，其余使用独立账本；先手轮流切换，真实随机只沿各场原RNG。

每第三轮把原战斗快照经过真实JSON往返，再以保存的RNG执行同一轮，核对战报、全部单位状态和随机状态。每轮另用逆序参战列表执行一次，核对数值、结局和RNG。检查有限数值、HP／态势／元力上限、因果余量、因果链无重入、结算队列清空、静默实际输出及死亡者不被恢复。每场24轮仅为仿真工作量边界，达到边界记录`round_limit`，不截断游戏真实劫战，也不把相持算作卡死。

最终矩阵：4608场、26543轮主对抗、7339次JSON续战核对、26543次名册反序核对，失败0。统计覆盖全部20种机制，包括实际神魂交换、沸血解控、逆骨闪避、烈脏兑现、识蕴回复、照业、忘情、因果和御魂。原始轮首资格与实际作用仍分开，未改变行蕴读取静默前原始记录的规则。

定向用例见[高阶炼体审计测试](../tests/test_high_body_audit.py)、[培养命令审计](../tests/test_high_body_cultivation_audit.py)。本轮还运行原四体系、劫战、普通战斗、语义、NPC、身魂存活、跨界与旧事件回归，并复核架构三项门禁；发行EXE和Android验收属于将来打包步骤，不用旧dist替代本轮源码证据。

最终回归：`build/high-body-audit-domain.xml` 348项、`build/high-body-audit-combat.xml` 167项、`build/high-body-audit-boundary.xml` 270项，共785项全部通过。新增[四道途真实页面边界验收](../tests/browser_high_body_audit.py)实际点击离体前保留的旧按钮，四套入口全部400拒绝、文件字节不变，复归后可正常支付并只升级一次；截图与结果在`build/high-body-audit-browser/`。原事件四主题真实页面验收通过；跨界契约、模块依赖和文档三项门禁通过，未发现禁止的玩家world直写或依赖环。
