"""Strict personal progress; no gameplay or random work during save decoding."""
from __future__ import annotations

import copy
from .secret_art_content import AFFINITIES


def decode_state(value):
    if value is None or value == {}:
        return {}
    if not isinstance(value, dict) or value.get('schema_version') != 1 or set(value) != {'schema_version', 'revision', 'arts'}:
        raise ValueError('秘法存档版本或字段不受支持')
    if type(value['revision']) is not int or value['revision'] < 0 or not isinstance(value['arts'], dict):
        raise ValueError('秘法存档进度不合法')
    for key, row in value['arts'].items():
        if key not in {'root_' + a for a in AFFINITIES} or not isinstance(row, dict):
            raise ValueError('秘法存档含未知传承')
        if set(row) != {'study_years', 'study_required', 'casting'}:
            raise ValueError('秘法存档字段不合法')
        if any(type(row[k]) is not int for k in ('study_years', 'study_required')) or not 0 <= row['study_years'] <= row['study_required'] or row['study_required'] < 1:
            raise ValueError('秘法修习进度不合法')
        cast = row['casting']
        if cast is None:
            continue
        if not isinstance(cast, dict) or set(cast) != {'years', 'required', 'material_name', 'material_id', 'material_kind'}:
            raise ValueError('秘法施术记录不合法')
        if (any(type(cast[k]) is not int for k in ('years', 'required')) or not 0 <= cast['years'] <= cast['required']
                or cast['required'] < 1 or cast['material_kind'] not in {'core', 'soul'}
                or any(not isinstance(cast[k], str) or not cast[k] for k in ('material_name', 'material_id'))
                or row['study_years'] != row['study_required']):
            raise ValueError('秘法施术进度或材料收据不合法')
    return copy.deepcopy(value)
