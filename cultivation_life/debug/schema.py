"""Small, explicit JSON Schema subset used by debug arguments (not gameplay rules)."""
import math


def validate(value, schema, path, error_type):
    kinds = schema.get('type', [])
    kinds = [kinds] if isinstance(kinds, str) else kinds
    actual = ('null' if value is None else 'boolean' if type(value) is bool else
              'integer' if type(value) is int else 'number' if type(value) is float else
              'string' if isinstance(value, str) else 'object' if isinstance(value, dict) else
              'array' if isinstance(value, list) else 'invalid')
    if actual not in kinds and not (actual == 'integer' and 'number' in kinds):
        raise error_type(f'{path}: expected {kinds}.')
    if 'enum' in schema and value not in schema['enum']:
        raise error_type(f'{path}: expected one of {schema["enum"]}.')
    if actual in {'integer', 'number'}:
        if (actual == 'number' and not math.isfinite(value)
                or 'minimum' in schema and value < schema['minimum']
                or 'maximum' in schema and value > schema['maximum']):
            raise error_type(f'{path}: outside its finite numeric range.')
    elif actual == 'string':
        if len(value) > schema.get('maxLength', 2048):
            raise error_type(f'{path}: string is too long.')
    elif actual == 'array':
        if not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', 999):
            raise error_type(f'{path}: invalid array length.')
        for index, item in enumerate(value):
            validate(item, schema['items'], f'{path}/{index}', error_type)
    elif actual == 'object':
        properties = schema.get('properties', {})
        additional = schema.get('additionalProperties', False)
        if set(schema.get('required', [])) - set(value) or len(value) > 128:
            raise error_type(f'{path}: missing required fields or too many keys.')
        for key, item in value.items():
            if key in properties:
                validate(item, properties[key], f'{path}/{key}', error_type)
            elif isinstance(additional, dict):
                validate(item, additional, f'{path}/{key}', error_type)
            else:
                raise error_type(f'{path}: unknown field {key}.')
    return value
