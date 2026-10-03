"""Package the desktop resources unchanged, with Android-only presentation additions."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile
from android_css import compile_css

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.android_provenance import build_record


def main(destination, staged_python=None):
    destination.mkdir(parents=True, exist_ok=True)
    mobile = ROOT / 'android/app/src/main/mobile'
    archive = destination / 'game-assets.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for directory in ('content', 'web', 'dlc'):
            for source in sorted((ROOT / directory).rglob('*')):
                if not source.is_file() or '__pycache__' in source.parts or source.suffix in ('.pyc', '.pyo'):
                    continue
                data = source.read_bytes()
                if source.suffix == '.css':
                    data = compile_css(data.decode('utf-8')).encode('utf-8')
                if source == ROOT / 'web/index.html':
                    data = data.decode('utf-8').replace('</head>',
                        '<link rel="stylesheet" href="/android/mobile.css"></head>').replace('</body>',
                        '<script src="/android/mobile.js"></script></body>').encode('utf-8')
                bundle.writestr(source.relative_to(ROOT).as_posix(), data)
        for source in sorted(mobile.rglob('*')):
            if source.is_file():
                bundle.write(source, 'web/android/' + source.relative_to(mobile).as_posix())
    (destination / 'game-assets.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest(), encoding='ascii')
    if staged_python is not None:
        record = build_record(ROOT, staged_python)
        (destination / 'game-build.json').write_text(json.dumps(record, sort_keys=True), encoding='utf-8')
    else:
        # Standalone UI fixture bundles are not evidence of an APK build.
        (destination / 'game-build.json').unlink(missing_ok=True)
    print(f'Android game bundle: {archive.stat().st_size:,} bytes; six themes and all installed DLC')


if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None)
