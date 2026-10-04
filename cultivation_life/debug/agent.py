"""Reusable CLI and a small MCP stdio tools server (2025-11-25 lifecycle).

Start the game separately with Debug enabled. This bridge cannot enable Debug,
read saves, evaluate scripts, or call ordinary gameplay HTTP routes.
"""
import argparse
import json
import sys
import traceback

from .client import DebugClient, ToolError


PROTOCOLS = ('2025-11-25', '2025-06-18')
MAX_LINE_BYTES = 70 * 1024 * 1024


class RpcError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message


class MCPServer:
    def __init__(self, client):
        self.client = client
        self.initialized = False
        self.ready = False

    def handle(self, request):
        request_id = request.get('id') if isinstance(request, dict) else None
        try:
            if (not isinstance(request, dict) or request.get('jsonrpc') != '2.0'
                    or not isinstance(request.get('method'), str)
                    or 'id' in request and type(request_id) not in (str, int)):
                raise RpcError(-32600, 'Invalid JSON-RPC request.')
            method, params = request['method'], request.get('params', {})
            if not isinstance(params, dict):
                raise RpcError(-32602, 'params must be an object.')
            if 'id' not in request:
                if method == 'notifications/initialized' and self.initialized:
                    self.ready = True
                return None
            if method == 'initialize':
                if (self.initialized or not isinstance(params.get('protocolVersion'), str)
                        or not isinstance(params.get('capabilities'), dict)
                        or not isinstance(params.get('clientInfo'), dict)):
                    raise RpcError(-32602, 'Invalid or repeated initialization.')
                self.initialized = True
                version = params['protocolVersion']
                result = {'protocolVersion': version if version in PROTOCOLS else PROTOCOLS[0],
                          'capabilities': {'tools': {'listChanged': False}},
                          'serverInfo': {'name': 'cultivation-life-debug', 'version': '1.0.0'},
                          'instructions': 'Enable Debug in the running game. Discover saves, clone with debug start, '
                              'then pass explicit session_id. Before writes read debug status; use its revision and '
                              'a new request_key. Retry uncertain writes with the identical key and parameters. '
                              'Never write source saves. Actions follow game rules and may stop at events.'}
            elif method == 'ping':
                result = {}
            elif not self.ready:
                raise RpcError(-32000, 'Initialize and send notifications/initialized first.')
            elif method == 'tools/list':
                if params.get('cursor'):
                    raise RpcError(-32602, 'This tool catalog has no continuation cursor.')
                result = {'tools': [{k: v for k, v in tool.items() if k != '_command'}
                                    for tool in self.client.tools()]}
            elif method == 'tools/call':
                if not isinstance(params.get('name'), str) or not isinstance(params.get('arguments', {}), dict):
                    raise RpcError(-32602, 'Expected tool name and argument object.')
                try:
                    value = self.client.call_tool(params['name'], params.get('arguments', {}))
                    result = {'content': [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False)}],
                              'structuredContent': value, 'isError': False}
                except (ToolError, ValueError) as error:
                    value = {'error': str(error), 'status': getattr(error, 'status', None),
                             'details': getattr(error, 'details', None)}
                    result = {'content': [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False)}],
                              'structuredContent': value, 'isError': True}
            else:
                raise RpcError(-32601, 'Method not found.')
            return {'jsonrpc': '2.0', 'id': request_id, 'result': result}
        except RpcError as error:
            response = {'code': error.code, 'message': error.message}
        except ToolError as error:
            response = {'code': -32000, 'message': str(error)}
        except Exception:
            traceback.print_exc(file=sys.stderr)
            response = {'code': -32603, 'message': 'Internal bridge error; see stderr.'}
        if isinstance(request, dict) and 'id' not in request and request.get('jsonrpc') == '2.0':
            return None
        return {'jsonrpc': '2.0', 'id': request_id, 'error': response}


def serve(client, source, target):
    server = MCPServer(client)
    while True:
        line = source.readline(MAX_LINE_BYTES + 1)
        if not line:
            return
        if len(line) > MAX_LINE_BYTES:
            print('MCP input exceeds 70 MiB; closing transport.', file=sys.stderr)
            return
        try:
            request = json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            response = server.handle(request)
        except (ValueError, UnicodeError):
            response = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Invalid JSON.'}}
        if response is not None:
            target.write(json.dumps(response, ensure_ascii=False, allow_nan=False).encode('utf-8') + b'\n')
            target.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    sub = parser.add_subparsers(dest='mode', required=True)
    sub.add_parser('mcp', help='Serve MCP tools over UTF-8 stdio.')
    sub.add_parser('tools', help='Print tool names and JSON Schemas from the running game.')
    call = sub.add_parser('call', help='Call an exact registered command with structured JSON arguments.')
    call.add_argument('command')
    call.add_argument('--arguments', default='{}')
    call.add_argument('--session-id')
    call.add_argument('--game-id')
    call.add_argument('--expected-revision', type=int)
    call.add_argument('--request-key')
    args = parser.parse_args(argv)
    try:
        client = DebugClient(args.url)
        if args.mode == 'mcp':
            serve(client, sys.stdin.buffer, sys.stdout.buffer)
            return 0
        if args.mode == 'tools':
            result = [{k: v for k, v in tool.items() if k != '_command'} for tool in client.tools()]
        else:
            result = client.call(args.command, json.loads(args.arguments), session_id=args.session_id,
                                 game_id=args.game_id, expected_revision=args.expected_revision,
                                 request_key=args.request_key)
            result.pop('catalog', None)
        sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
        return 0
    except (ToolError, ValueError) as error:
        sys.stderr.write(str(error) + '\n')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
