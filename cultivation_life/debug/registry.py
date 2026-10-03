"""Explicit English command grammar; no evaluation, reflection or fuzzy aliases."""
from dataclasses import dataclass
import shlex
from typing import Callable


class CommandError(ValueError):
    """An expected console input error, distinct from an implementation failure."""


@dataclass(frozen=True)
class Argument:
    name: str
    choices: tuple[str, ...] = ()


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
                'arguments': [{'name': a.name, 'choices': list(a.choices)} for a in self.arguments]}


@dataclass
class Services:
    start: Callable
    resume: Callable
    sessions: Callable
    export: Callable
    import_bundle: Callable


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
            for argument, value in zip(command.arguments, values):
                if argument.choices and value not in argument.choices:
                    raise CommandError(f'{argument.name}: expected one of {", ".join(argument.choices)}')
            return command, values
        raise CommandError(f'Unknown command: {text}. Try help.')

    def catalog(self, prefix=''):
        rows = [command.describe() for name, command in sorted(self.commands.items())
                if not prefix or name == prefix or name.startswith(prefix + ' ')]
        if not rows:
            raise CommandError(f'Unknown command group: {prefix}')
        return rows
