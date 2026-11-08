"""Land-temple specializations; two physical slots, no passive player multiplier."""
FACILITIES = {
    'watch': dict(name='护境阵台', mark='境', purpose='维护原址镇地阵，再亲自巡护百年。',
                  materials=(60, 30, 15), labor=1200),
    'care': dict(name='济用坊', mark='生', purpose='修复本地原建筑，再主持百年公共养护。',
                 materials=(40, 20, 10), labor=800),
    'teach': dict(name='传习堂', mark='教', purpose='当面培养一位门人或亲友，再主持百年公共讲习。',
                  materials=(20, 10, 5), labor=400),
}
