"""Strict additive incident storage contract; old saves need no rewrite."""
import math
from .incident_definitions import BY_ID, INCIDENT_IDS, INCIDENT_ACTIONS, response, terms


def validate_incidents(rows, year):
    if type(rows) is not dict or rows.keys() - INCIDENT_IDS:
        raise ValueError('界域事务目录无效')
    for identity, row in rows.items():
        if type(row) is not dict or set(row) != {'stage', 'choice', 'opened_at', 'closed_at', 'remaining', 'base', 'claimed'}:
            raise ValueError('界域事务字段无效')
        if row['stage'] not in {'surveying', 'surveyed', 'treated', 'closed'}:
            raise ValueError('界域事务阶段无效')
        if type(row['opened_at']) is not int or not 0 <= row['opened_at'] <= year:
            raise ValueError('界域事务起年无效')
        if type(row['remaining']) is not int or row['remaining'] < 0:
            raise ValueError('界域事务余量无效')
        for key in ('base', 'claimed'):
            if type(row[key]) not in (int, float) or not math.isfinite(row[key]) or row[key] < 0:
                raise ValueError('界域事务所得无效')
        if row['stage'] in {'treated', 'closed'}:
            if row['choice'] not in {'incident_preserve', 'incident_seal'}:
                raise ValueError('界域事务处理分支无效')
        elif row['choice'] is not None:
            raise ValueError('未处理事务不能保存结局')
        if row['stage'] == 'closed':
            if (type(row['closed_at']) is not int or not row['opened_at'] <= row['closed_at'] <= year
                    or row['remaining'] > response(BY_ID[identity], row['choice']).allowance
                    or row['claimed'] > row['base'] * .02 + 1e-9):
                raise ValueError('界域事务结案账目无效')
        elif row['closed_at'] is not None or row['remaining'] or row['base'] or row['claimed']:
            raise ValueError('尚未复核的事务不能产生余量')


def validate_incident_task(task, row):
    action = task['action']
    if action not in INCIDENT_ACTIONS:
        raise ValueError('界域事务动作无效')
    years, stones, mana = terms(BY_ID[task['target_id']], action)
    escrow = task['escrow']
    if (task['cycle'] != 0 or task['person_id'] is not None or task['duration'] != years
            or escrow['material'] is not None or escrow['total'] != stones
            or escrow['spent'] != stones * task['progress'] // years
            or not mana and escrow['mp_paid'] != 0):
        raise ValueError('界域事务工时或托管无效')
    if task['status'] in {'reserved', 'running', 'paused'}:
        expected = 'surveying' if action == 'incident_survey' else 'treated' if action == 'incident_review' else 'surveyed'
        if row['stage'] != expected:
            raise ValueError('界域任务与处理阶段不一致')
    if task['status'] == 'completed':
        if (task['progress'] != years or row['stage'] == 'surveying'
                or action == 'incident_review' and row['stage'] != 'closed'
                or action in {'incident_preserve', 'incident_seal'} and row['choice'] != action):
            raise ValueError('界域任务完成事实不一致')
