"""Six distinct local petitions; outcomes name their actual costs and authorities."""
CASES = {
    'water': dict(name='用水冲突', mark='水', intro='药田与街坊请求重新安排共用水源。', missing='本地须有你拥有经营权限的完好药田。'),
    'supply': dict(name='供货短缺', mark='货', intro='坊市请求补充一项实际短缺的标准商品。', missing='本地市场没有可受理的短缺标准商品。'),
    'road': dict(name='道路阻断', mark='路', intro='道路来报登记一处塌方，须清障或标出缓行通路。', missing='此地没有当前可通行的相邻普通道路。'),
    'property': dict(name='庙产争议', mark='契', intro='街坊希望开放庙产；主持须明确公共使用与自用边界。', missing='须有本人所有的原土地庙。'),
    'guard': dict(name='护境失职', mark='阵', intro='原镇地阵已经受损，街坊请求修复或暂停承诺。', missing='此地没有需要修复的自有镇地阵。'),
    'rebuild': dict(name='灾后重建', mark='工', intro='本地已有遗址，请决定完整复建还是先行应急安置。', missing='此地没有你有重建权限的非佛寺遗址。'),
}
