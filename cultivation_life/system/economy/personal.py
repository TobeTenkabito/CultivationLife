"""A bounded personal cash statement, separate from the busy world ledger."""
def cash_balance(game):
    return sum(i.quantity for i in game.player.inventory if i.id == 'spirit_stone')


def ensure_personal(game):
    if 'personal' in game.economy_v2:
        return False
    game.economy_v2['personal'] = dict(since=game.player.age, opening=cash_balance(game),
                                      income=0, expense=0, entries=[])
    return True


def record(game, entry):
    if 'player' not in (entry['source'], entry['destination']):
        return
    statement = game.economy_v2.get('personal')
    if statement is None:
        return
    statement['income' if entry['destination'] == 'player' else 'expense'] += entry['amount']
    statement['entries'].append(dict(entry, world=game.player.world))
    del statement['entries'][:-80]


def public_personal(game):
    statement = game.economy_v2.get('personal', {})
    cash = cash_balance(game)
    income, expense = statement.get('income', 0), statement.get('expense', 0)
    opening = statement.get('opening', cash)
    return dict(balance=cash, since=statement.get('since', game.player.age), opening=opening,
                income=income, expense=expense, other_change=cash - opening - income + expense,
                entries=list(reversed(statement.get('entries', []))))
