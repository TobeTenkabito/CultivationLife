"""Finite public procurement with real escrow; no duplicate court treasury."""
from .westward_rules import config, merit_balance
from .economy import organizations as finance
from .economy.ledger import account, balance, transfer_value

COURT = 'organization:court:heavenly'
YAOCHI = 'institution:celestial:yaochi'
BACKGROUND = 'background:celestial'


def budget(game):
    cfg = config()
    period = int(cfg.get('budget_years', 100))
    window = int(game.player.age) // period
    current = game.heavenly_court.get('westward_budget', {})
    scale = game.economy_v2.get('worlds', {}).get('celestial', {}).get('scale', 1)
    if current.get('window') != window:
        current = dict(window=window, cap=int(cfg.get('budget_base', 2000000) * scale), committed=0)
    return dict(current, remaining=max(0, current['cap'] - current['committed']),
                ends=(window + 1) * period,
                funding=balance(game, BACKGROUND) if BACKGROUND in game.economy_v2.get('accounts', {}) else 0)


def payment_reason(game, price, currency):
    if currency == 'merit':
        if game.yaochi_state.get('merit', 0) < price:
            return '瑶池功勋不足'
        return ''
    if 'merit_account' not in game.heavenly_court:
        return '请先确认功德账本'
    if merit_balance(game) < (price + 39) // 40:
        return '可用功德不足'
    b = budget(game)
    if b['remaining'] < price * 250:
        return '本期公共服务承兑额度不足'
    if b['funding'] < price * 250:
        return '仙界公共服务采购经费不足'
    return ''


def reserve(game, order, price, currency):
    reason = payment_reason(game, price, currency)
    if reason:
        raise ValueError(reason)
    finance.register(game, 'yaochi', 'yaochi', 'celestial')
    order.update(currency=currency, paid=price if currency == 'merit' else (price + 39) // 40,
                 price=price, cash=0)
    if currency == 'merit':
        game.yaochi_state['merit'] = game.yaochi_state.get('merit', 0) - price
        return
    b = budget(game)
    cash = price * 250
    escrow = f"escrow:yaochi-westward:{order['id']}"
    finance.register(game, 'court', 'heavenly', 'celestial')
    account(game, escrow)
    transfer_value(game, BACKGROUND, COURT, cash, '瑶池专项公共服务采购')
    transfer_value(game, COURT, escrow, cash, '公共服务经费托管')
    game.heavenly_court['westward_budget'] = dict(window=b['window'], cap=b['cap'], committed=b['committed'] + cash)
    game.heavenly_court['merit_account']['available'] -= order['paid']
    order.update(escrow=escrow, cash=cash, budget_window=b['window'])


def close(game, order, used, total):
    """Refund original currency once; paid work rounds up, refunds round down."""
    refund = order['paid'] * (total - used) // total
    if order['currency'] == 'merit':
        game.yaochi_state['merit'] = game.yaochi_state.get('merit', 0) + refund
    else:
        game.heavenly_court['merit_account']['available'] += refund
        cash_refund = order['cash'] * (total - used) // total
        transfer_value(game, order['escrow'], YAOCHI, order['cash'] - cash_refund, '瑶池已完成专修服务')
        transfer_value(game, order['escrow'], COURT, cash_refund, '未使用公共服务款退回原府库')
        transfer_value(game, COURT, BACKGROUND, cash_refund, '未使用专项退回原出资方')
        current = game.heavenly_court.get('westward_budget', {})
        if current.get('window') == order['budget_window']:
            current['committed'] -= cash_refund
        # Only the zero-balance unique escrow is removed. Serial never rewinds.
        del game.economy_v2['accounts'][order['escrow']]
    return refund
