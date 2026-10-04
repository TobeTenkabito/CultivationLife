"""Standard-library agent client. Knows HTTP contracts, never game/storage internals."""
import copy
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class ToolError(RuntimeError):
    def __init__(self, message, *, status=None, details=None):
        super().__init__(message)
        self.status = status
        self.details = details


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class DebugClient:
    """Explicit sessions, no automatic retries, no fallback to normal gameplay endpoints."""
    def __init__(self, url='http://127.0.0.1:8000', timeout=60):
        parsed = urlsplit(url)
        if (parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}
                or parsed.username or parsed.password or parsed.path not in {'', '/'}
                or parsed.query or parsed.fragment):
            raise ValueError('Debug tools require a local HTTP origin without a path or credentials.')
        # Validate malformed ports before sending any request; bypass environment proxies.
        _ = parsed.port
        self.url = url.rstrip('/') + '/api/debug/command'
        self.timeout = timeout
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def call(self, command, arguments=None, *, session_id=None, game_id=None,
             expected_revision=None, request_key=None, bundle=None):
        payload = {'command': command, 'arguments': {} if arguments is None else arguments}
        payload.update({key: value for key, value in {
            'session_id': session_id, 'game_id': game_id, 'expected_revision': expected_revision,
            'request_key': request_key, 'bundle': bundle}.items() if value is not None})
        request = Request(self.url, data=json.dumps(payload, allow_nan=False).encode('utf-8'),
                          headers={'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                return json.load(response)
        except HTTPError as error:
            try:
                details = json.load(error)
            except (ValueError, UnicodeError):
                details = {'error': f'HTTP {error.code}'}
            raise ToolError(details.get('error', f'HTTP {error.code}'), status=error.code, details=details) from error
        except (URLError, TimeoutError, ConnectionError) as error:
            raise ToolError('Debug server unavailable; a timed-out write may have committed. '
                            'Retry only with the same request_key and arguments.', details=str(error)) from error

    def tools(self):
        """Build schemas from the running game's registry, including loaded content IDs."""
        catalog = self.call('help')['catalog']
        tools = []
        for command in catalog:
            properties = {'arguments': copy.deepcopy(command['input_schema'])}
            required = ['arguments']
            properties['session_id'] = {'type': 'string', 'pattern': '^[a-f0-9]{32}$'}
            if command['requires_session']:
                required.append('session_id')
            if command['name'] == 'debug start':
                properties['game_id'] = {'type': 'string', 'description': 'Source ID from save list.'}
                required.append('game_id')
            if command['name'] == 'repro import':
                properties['bundle'] = {'type': 'object', 'description': 'Complete reproduction bundle, not a path.'}
                required.append('bundle')
            writes = command['type'] in {'mutation', 'snapshot', 'simulation'}
            if writes:
                properties.update(expected_revision={'type': 'integer', 'minimum': 0},
                                  request_key={'type': 'string', 'pattern': '^[A-Za-z0-9_-]{1,64}$'})
                required.extend(['expected_revision', 'request_key'])
            tools.append({'name': 'cultivation_' + command['name'].replace(' ', '_'),
                          'description': command['description'],
                          'inputSchema': {'type': 'object', 'properties': properties,
                                          'required': required, 'additionalProperties': False},
                          'annotations': {'readOnlyHint': command['type'] in {'query', 'preview', 'export'},
                                          'destructiveHint': writes, 'openWorldHint': False},
                          '_command': command['name']})
        return tools

    def call_tool(self, name, arguments):
        tool = next((tool for tool in self.tools() if tool['name'] == name), None)
        if tool is None:
            raise ToolError('Unknown tool; discover tools from the running server.')
        schema = tool['inputSchema']
        if (not isinstance(arguments, dict) or set(arguments) - set(schema['properties'])
                or set(schema['required']) - set(arguments)):
            raise ToolError('Tool arguments do not match inputSchema.')
        result = self.call(tool['_command'], **arguments)
        # Metadata discovery has its own tool; avoid repeating all schemas on every action.
        result.pop('catalog', None)
        return result
