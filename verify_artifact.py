"""Offline integrity checks for a linux2apk output artifact."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path


def digest_file(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify(apk, source):
    apk = Path(apk)
    source = Path(source)
    build = json.loads(apk.with_suffix('.build.json').read_text(encoding='utf8'))
    with zipfile.ZipFile(apk) as archive:
        names = set(archive.namelist())
        app = json.loads(archive.read('assets/app.json'))
        compiled_icons = sorted(
            name for name in names
            if name.startswith('res/') and name.endswith('/ic_launcher.png')
        )
        image_sha256 = hashlib.file_digest(
            archive.open('assets/application.erofs'), 'sha256'
        ).hexdigest()
        icon_sha256 = hashlib.sha256(
            archive.read('assets/launcher-icon.png')
        ).hexdigest()
        image_bytes = archive.getinfo('assets/application.erofs').file_size

    source_sha256 = digest_file(source)
    apk_sha256 = digest_file(apk)
    required = {
        'assets/application.erofs', 'assets/app.json', 'assets/launch.sh',
        'assets/deploy.sh', 'assets/launcher-icon.png',
    }
    checks = {
        'source_matches': source_sha256 == build['source_sha256'],
        'apk_matches': apk_sha256 == build['apk_sha256'],
        'image_matches': image_sha256 == build['image_sha256'],
        'image_size_matches': image_bytes == build['image_bytes'],
        'icon_matches': icon_sha256 == build['icon']['sha256'],
        'package_matches': app['package'] == build['package'],
        'callback_matches': app['callback_schemes'] == build['callback_schemes'],
        'required_entries_present': required <= names,
        'compiled_icon_present': len(compiled_icons) == 1,
    }
    report = {
        'checks': checks,
        'source_sha256': source_sha256,
        'apk_sha256': apk_sha256,
        'apk_bytes': apk.stat().st_size,
        'embedded_erofs_sha256': image_sha256,
        'embedded_erofs_bytes': image_bytes,
        'icon_sha256': icon_sha256,
        'compiled_icon_entry': compiled_icons[0] if compiled_icons else None,
        'package': app['package'],
        'label': app['label'],
        'entry': app['entry'],
        'callback_schemes': app['callback_schemes'],
    }
    if not all(checks.values()):
        failed = ', '.join(name for name, ok in checks.items() if not ok)
        raise ValueError('Artifact verification failed: ' + failed)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = verify(args.apk, args.source)
    text = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding='utf8')
    print(text, end='')


if __name__ == '__main__':
    main()
