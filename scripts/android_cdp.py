"""Small CDP client compatible with Android 12's original WebView 91."""
import base64
import json
from pathlib import Path
import subprocess
import time
import re
import urllib.request
import websocket


class AndroidPage:
    def __init__(self, serial, package='com.fusheng.wendao.debug', port=9227):
        self.serial, self.package, self.port = serial, package, port
        self.adb = Path('F:/CultivationLife-Android-Tools/sdk/platform-tools/adb.exe')
        self.sequence = 0
        self.errors = []
        self.socket = None
        self.bounds = None

    def command(self, *args):
        return subprocess.check_output([str(self.adb), '-s', self.serial, *args], text=True, encoding='utf-8', timeout=30).strip()

    def connect(self):
        deadline = time.monotonic()+60
        last = None
        while time.monotonic() < deadline:
            try:
                pid=self.command('shell','pidof',self.package).split()[0]
                self.command('forward',f'tcp:{self.port}',f'localabstract:webview_devtools_remote_{pid}')
                with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/json',timeout=3) as r:
                    pages=json.load(r)
                page=next(p for p in pages if p.get('url','').startswith('http://127.0.0.1'))
                self.socket=websocket.create_connection(page['webSocketDebuggerUrl'],suppress_origin=True,timeout=60)
                self.call('Runtime.enable')
                self.wait('typeof configData !== "undefined" && configData && window.AndroidUI')
                return self
            except Exception as error:
                last=error;time.sleep(.5)
        raise RuntimeError(f'Android WebView unavailable: {last}')

    def call(self, method, **params):
        self.sequence+=1
        self.socket.send(json.dumps({'id':self.sequence,'method':method,'params':params}))
        deadline = time.monotonic()+60
        while True:
            if time.monotonic()>deadline: raise TimeoutError(method)
            value=json.loads(self.socket.recv())
            if value.get('method')=='Runtime.exceptionThrown': self.errors.append(value['params'])
            if value.get('id')==self.sequence:
                if 'error' in value: raise RuntimeError(value['error'])
                return value.get('result',{})

    def evaluate(self, expression):
        result=self.call('Runtime.evaluate',expression=expression,returnByValue=True,awaitPromise=True)
        if 'exceptionDetails' in result: raise AssertionError(result['exceptionDetails'])
        return result.get('result',{}).get('value')

    def wait(self, expression, seconds=45):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if self.evaluate(f'Boolean({expression})'): return
            time.sleep(.15)
        raise AssertionError(f'Timed out: {expression}')

    def tap(self, selector):
        target=json.dumps(selector)
        self.evaluate(f'document.querySelector({target}).scrollIntoView({{block:"center"}})')
        time.sleep(.15)
        rect=self.evaluate(f'(()=>{{const e=document.querySelector({target}),r=e.getBoundingClientRect();return {{x:r.x+r.width/2,y:r.y+r.height/2,disabled:!!e.disabled}}}})()')
        assert not rect['disabled'],selector
        # WebView 91 does not reliably acknowledge CDP touchStart. Send a real
        # Android touch through input instead, using the native WebView bounds.
        size=self.evaluate('[innerWidth,innerHeight]')
        if not self.bounds or self.bounds[0]!=size:
            for attempt in range(3):
                try:
                    self.command('shell','uiautomator','dump','/sdcard/wendao-window.xml')
                    break
                except (subprocess.CalledProcessError,subprocess.TimeoutExpired):
                    if attempt==2: raise
                    time.sleep(.5)
            xml=self.command('shell','cat','/sdcard/wendao-window.xml')
            bounds=re.search(r'class="android.webkit.WebView"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',xml)
            assert bounds,xml
            self.bounds=(size,tuple(map(int,bounds.groups())))
        left,top,right,bottom=self.bounds[1]
        scale=(right-left)/size[0]
        self.command('shell','input','tap',str(round(left+rect['x']*scale)),str(round(top+rect['y']*scale)))

    def screenshot(self, path):
        result=self.call('Page.captureScreenshot',format='png')
        Path(path).write_bytes(base64.b64decode(result['data']))

    def close(self):
        if self.socket: self.socket.close()
