"""Exercise the release acceptance scenario against source before building."""
from pathlib import Path
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cultivation_life.engine import GameEngine
from cultivation_life import server
from scripts.verify_technique_exe import verify_techniques

with tempfile.TemporaryDirectory() as directory:
    folder=Path(directory);engine=GameEngine(ROOT,folder/'data/saves')
    class Handler(server.Handler):
        def log_message(self,*args):pass
    with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',folder):
        http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=http.serve_forever,daemon=True).start()
        try:verify_techniques(f'http://127.0.0.1:{http.server_port}',True,folder)
        finally:http.shutdown();http.server_close()
