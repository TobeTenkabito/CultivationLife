"""Explicit English command grammar; no evaluation, reflection or fuzzy aliases."""
from dataclasses import dataclass
import shlex
import math
import re
from typing import Callable


class CommandError(ValueError):
    """An expected console input error, distinct from an implementation failure."""


@dataclass(frozen=True)
class Argument:
    name: str
    choices: tuple[str, ...] = ()
    type: str = 'string'
    minimum: float | None = None
    maximum: float | None = None

    def schema(self):
        result = {'type': self.type}
        if self.choices:
            result['enum'] = list(self.choices)
        if self.minimum is not None:
            result['minimum'] = self.minimum
        if self.maximum is not None:
            result['maximum'] = self.maximum
        return result

    def validate(self, value, *, textual=False):
        if textual and self.type != 'string':
            try:
                value = (int if self.type == 'integer' else float)(value)
            except (ValueError, TypeError, OverflowError) as error:
                raise CommandError(f'{self.name} expects {self.type}.') from error
        valid = (isinstance(value, str) if self.type == 'string' else
                 type(value) is int if self.type == 'integer' else type(value) in (int, float))
        if not valid:
            raise CommandError(f'{self.name} expects {self.type}.')
        if self.type != 'string' and (type(value) is float and not math.isfinite(value)
                or self.minimum is not None and value < self.minimum
                or self.maximum is not None and value > self.maximum):
            raise CommandError(f'{self.name} is outside its finite numeric range.')
        if self.choices and value not in self.choices:
            raise CommandError(f'{self.name}: expected one of {", ".join(self.choices)}')
        return value


@dataclass(frozen=True)
class Command:
    name: str
    kind: str
    description: str
    handler: Callable
    arguments: tuple[Argument, ...] = ()
    requires_session: bool = True

    def describe(self):
        return {'name': self.name, 'type': self.kind, 'description': self.description,
                'usage': ' '.join([self.name, *(f'<{a.name}>' for a in self.arguments)]),
                'arguments': [{'name': a.name, 'choices': list(a.choices), **a.schema()} for a in self.arguments],
                'requires_session': self.requires_session,
                'input_schema': {'type': 'object', 'properties': {a.name: a.schema() for a in self.arguments},
                                 'required': [a.name for a in self.arguments], 'additionalProperties': False}}


@dataclass
class Services:
    start: Callable
    resume: Callable
    sessions: Callable
    export: Callable
    import_bundle: Callable
    sources: Callable
    simulate: Callable


@dataclass
class Context:
    session: dict | None
    services: Services

    @property
    def document(self):
        if self.session is None:
            raise CommandError('Start an isolated copy first: debug start')
        return self.session['current']['game']


class Registry:
    def __init__(self):
        self.commands = {}

    def register(self, command):
        if command.name in self.commands:
            raise RuntimeError(f'Duplicate debug command: {command.name}')
        if not re.fullmatch(r'[a-z][a-z0-9_]*(?: [a-z][a-z0-9_]*)*', command.name):
            raise RuntimeError(f'Invalid debug command name: {command.name}')
        if any(name.replace(' ', '_') == command.name.replace(' ', '_') for name in self.commands):
            raise RuntimeError(f'Duplicate generated tool name: {command.name}')
        if (len({a.name for a in command.arguments}) != len(command.arguments)
                or any(a.type not in {'string', 'integer', 'number'} for a in command.arguments)):
            raise RuntimeError(f'Invalid debug argument schema: {command.name}')
        if command.kind not in {'query', 'mutation', 'session', 'snapshot', 'export', 'simulation'}:
            raise RuntimeError(f'Invalid command type: {command.kind}')
        self.commands[command.name] = command

    def parse(self, text):
        if not isinstance(text, str) or not text.strip() or len(text) > 2048:
            raise CommandError('Expected a command of 1–2048 characters.')
        try:
            words = shlex.split(text)
        except ValueError as error:
            raise CommandError(str(error)) from error
        if words[0] == 'help':
            return self.commands['help'], [' '.join(words[1:])]
        for name in sorted(self.commands, key=lambda value: len(value.split()), reverse=True):
            prefix = name.split()
            if words[:len(prefix)] != prefix:
                continue
            command = self.commands[name]
            values = words[len(prefix):]
            if len(values) != len(command.arguments):
                raise CommandError('Usage: ' + command.describe()['usage'])
            return command, [a.validate(v, textual=True) for a, v in zip(command.arguments, values)]
        raise CommandError(f'Unknown command: {text}. Try help.')

    def structured(self, name, arguments):
        if not isinstance(name, str) or name not in self.commands:
            raise CommandError('Unknown exact command name.')
        command = self.commands[name]
        if not isinstance(arguments, dict) or set(arguments) != {a.name for a in command.arguments}:
            raise CommandError('Arguments must match the command input_schema exactly.')
        return command, [a.validate(arguments[a.name]) for a in command.arguments]

    def catalog(self, prefix=''):
        rows = [command.describe() for name, command in sorted(self.commands.items())
                if not prefix or name == prefix or name.startswith(prefix + ' ')]
        if not rows:
            raise CommandError(f'Unknown command group: {prefix}')
        return rows
