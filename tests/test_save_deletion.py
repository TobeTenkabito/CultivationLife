import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import pytest

from cultivation_life import server
from cultivation_life.storage import SaveStore


def test_deletion_is_scoped_and_validated(tmp_path):
    store = SaveStore(tmp_path / 'saves')
    chosen = store.directory / 'chosen.json'
    survivor = store.directory / 'survivor.json'
    achievement = tmp_path / 'achievements.json'
    for file in (chosen, survivor, achievement):
        file.write_text('{}')
    for invalid in ('../achievements', '', 'chosen.json', 'a/b', 'a\\b'):
        with pytest.raises(ValueError):
            store.delete(invalid)
    store.delete('chosen')
    assert not chosen.exists()
    assert survivor.read_text() == achievement.read_text() == '{}'
    with pytest.raises(KeyError):
        store.delete('chosen')


def test_delete_http_only_targets_individual_save(tmp_path):
    store = SaveStore(tmp_path)
    (tmp_path / 'chosen.json').write_text('{}')
    with patch.object(server.ENGINE, 'store', store):
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            base = f'http://127.0.0.1:{httpd.server_port}'
            with urlopen(Request(base+'/api/games/chosen', method='DELETE')) as response:
                assert json.load(response) == {'deleted': 'chosen'}
            for path in ('/api/games/chosen', '/api/games', '/api/games/../achievements'):
                with pytest.raises(HTTPError) as error:
                    urlopen(Request(base+path, method='DELETE'))
                assert error.value.code == 404
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join()
