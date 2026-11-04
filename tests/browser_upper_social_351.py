import sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cultivation_life import server
from cultivation_life.engine import GameEngine
from scripts.verify_upper_social_exe import verify_upper_social

def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as name:
        folder=Path(name);engine=GameEngine(ROOT,folder/'data/saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',folder):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:verify_upper_social(f'http://127.0.0.1:{http.server_port}',True,folder)
            finally:http.shutdown();http.server_close()
if __name__=='__main__':main()
