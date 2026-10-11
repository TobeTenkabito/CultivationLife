"""Political extension of the existing Myriad Beast Palace; no fiscal writes."""
from . import core


def blocs(game):
    from ..upper_institutions import officials
    from ..institution_state import account
    if game.player.world != 'nether':
        return []
    existing = {p['id']: p for p in officials(game) if p['present']}
    support = account(game).get('support', [45]*5)
    return [dict(id=b['id'], name=b['name'], weight=b['weight'], support=support[i],
                 present=b['official_id'] in existing) for i, b in enumerate(core.config()['blocs'])]



def propose(game, data, target):
    from ..upper_institutions import require_action, votes
    from ..institution_state import account
    require_action(game)
    original = account(game)
    if not original['joined'] or not original['seat_active']:
        raise ValueError('须持有万妖宫门阀代言资格，方可提交王庭政体提案')
    if target not in core.REGIMES:
        raise ValueError('王庭政体不合法')
    court = data['court']
    if target == court['regime'] or data['political_clock']-court['last_proposal'] < 2:
        raise ValueError('政体未改变，或尚未到下一次提案时机')
    tally = votes(game, original['policy'], player=True)
    if sum(row['weight'] for row in tally if row['yes']) < 8:
        raise ValueError('原万妖宫议席未达到八议权支持，提案未获通过')
    court.update(regime=target, phase='succession', last_proposal=data['political_clock'])
    core.fact(game, 'nether', 'court', game.player.location_id, f'五门阀议决通过：王庭采用{core.REGIMES[target]}。', [core.PLAYER], 'original_council_vote')
