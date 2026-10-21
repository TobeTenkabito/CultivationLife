"""Run the real UI with an isolated preview save library and appearance settings."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8773)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    from cultivation_life import server
    from cultivation_life.engine import GameEngine
    from cultivation_life.ui_preferences import write_ui_preferences
    server.PERSISTENCE_ROOT = ROOT / ('build/pixel-ui-preview' if args.port == 8773 else f'build/pixel-ui-preview-{args.port}')
    server.ENGINE = GameEngine(ROOT, server.PERSISTENCE_ROOT / 'data/saves')
    write_ui_preferences(server.PERSISTENCE_ROOT, {'pixel_art': True})
    if not list((server.PERSISTENCE_ROOT / 'data/saves').glob('*.json')):
        server.ENGINE.create_game('沈清和', 'heavenly', 'dao', 2172, preset_id='core')
        server.ENGINE.create_game('云知微', 'heavenly', 'dao', 2173, preset_id='core', gender='female')
    httpd = server.ThreadingHTTPServer(('127.0.0.1', args.port), server.Handler)
    print(f'Isolated pixel preview: http://127.0.0.1:{args.port}', flush=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


if __name__ == '__main__':
    main()
