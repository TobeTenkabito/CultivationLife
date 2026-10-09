"""Trace legacy rewards through finite aggregate counterparties, not NPC wallets."""
from .state import ensure_state
from .ledger import balance, transfer_value, account


def grant(game, amount, reason):
    ensure_state(game)
    amount = max(0,int(amount))
    source = f'background:{game.player.world}'
    if game.player.world not in game.economy_v2['worlds']:
        # Isolated discoveries are explicit issuance, never a guessed human
        # economy. Only this concrete reward is minted and reported.
        source = f'discovery:{game.player.world}'
        pool = account(game,source)
        pool['balance'] += amount
        game.economy_v2['issued'] = game.economy_v2.get('issued',0)+amount
    paid = min(amount,balance(game,source))
    transfer_value(game,source,'player',paid,reason)
    return paid
