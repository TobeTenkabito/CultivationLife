"""Bounded political receipts; no economic settlement."""


def note(game, row, title, text):
    row.setdefault('logs', []).append(dict(age=game.player.age, title=title[:32], text=text[:160]))
    row['logs'] = row['logs'][-80:]
