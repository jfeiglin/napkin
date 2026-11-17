"""Retrieve a document's raw bytes into the content-addressed evidence cache, and extract their text.

    python -m tools.evidence.fetch URL [--archive-timestamp 20240101000000] [--out retrieval.json]
    python -m tools.evidence.fetch --from-file PATH --url URL --tool tinyfish|manual|archive [--final-url U]
    python -m tools.evidence.fetch --extract .evidence-cache/sha256/ab/<sha>.pdf [--media-type TYPE] [--force]

Bytes are stored unmodified at .evidence-cache/sha256/<aa>/<sha256>.<ext> and a retrieval
record is printed (or written with --out). A web.archive.org capture is always fetched
through its raw `id_` form; the record keeps the original URL as requested_url.

--extract takes plain text from cached document bytes and caches it next to them. PDF text
comes from Ghostscript txtwrite run page by page, HTML from the standard-library parser with
script and style dropped, plain text is decoded as UTF-8. The text is written to
<sha>.extracted.txt with a sidecar <sha>.extracted.json {extractor, sha256}; an existing
extraction is kept unless --force, so a newer extractor never silently replaces the text
a claim was matched against. --extract takes no URL and no other option of a retrieval.
In both modes, --media-type is the media type of the bytes.
"""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from ..catalogue import ROOT
from .cache import evidence_cache

CACHE = evidence_cache()
USER_AGENT = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
)
TOOLS = ('curl', 'archive', 'tinyfish', 'manual')
_ARCHIVE = re.compile(r'^https?://web\.archive\.org/web/(\d{1,14})(?:[a-z]{2}_)?/(.+)$')
_EXTENSIONS = {
    'application/pdf': 'pdf',
    'text/html': 'html',
    'application/xhtml+xml': 'html',
    'text/plain': 'txt',
    'application/json': 'json',
    'application/xml': 'xml',
    'text/xml': 'xml',
    'text/csv': 'csv',
}
# The extension of a file name: one to five letters and digits that are not a number (`.pdf`, not
# the `.001` of `j.cell.2020.01.001`).
_SUFFIX = re.compile(r'.+\.((?![0-9]+$)[A-Za-z0-9]{1,5})')


def archive_id(url, timestamp=None):
    """(original_url, raw id_ capture URL) for an archive.org URL or a URL plus capture timestamp."""
    match = _ARCHIVE.match(url)
    if match:
        timestamp, url = match.groups()
    if not timestamp:
        return url, None
    return url, f'https://web.archive.org/web/{timestamp}id_/{url}'


def sniff(content, media_type='', url=''):
    """(media_type, extension). Magic bytes win over headers, and headers over the name of the last
    segment of the URL's path: a host (`www.cisa.gov`) or a query names no file."""
    head = content[:1024].lstrip().lower()
    if content.startswith(b'%PDF-'):
        return 'application/pdf', 'pdf'
    if head.startswith((b'<!doctype html', b'<html')) or b'<html' in head:
        return media_type if 'html' in media_type.lower() else 'text/html', 'html'
    base = media_type.split(';')[0].strip().lower()
    if base in _EXTENSIONS:
        return media_type, _EXTENSIONS[base]
    suffix = _SUFFIX.fullmatch(urlsplit(url).path.rsplit('/', 1)[-1])
    return media_type or 'application/octet-stream', (suffix.group(1).lower() if suffix else 'bin')


def cache_path(sha256, extension, cache=CACHE):
    return Path(cache) / 'sha256' / sha256[:2] / f'{sha256}.{extension}'


def store(content, extension, cache=CACHE):
    sha = hashlib.sha256(content).hexdigest()
    path = cache_path(sha, extension, cache)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_bytes() != content:
        path.write_bytes(content)
    return sha, path


def record(
    requested_url,
    final_url,
    http_status,
    tool,
    media_type,
    content,
    cache=CACHE,
    archived_url=None,
    retrieved_at=None,
):
    media_type, extension = sniff(content, media_type or '', final_url)
    sha, path = store(content, extension, cache)
    out = {'requested_url': requested_url, 'final_url': final_url}
    if archived_url:
        out['archived_url'] = archived_url
    out.update(
        http_status=http_status,
        retrieved_at=retrieved_at or datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ'),
        tool=tool,
        media_type=media_type,
        bytes=len(content),
        sha256=sha,
        cache_path=relative(path),
    )
    return out


def relative(path):
    """Repository-relative path when inside the checkout, else absolute."""
    path = Path(path).resolve()
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def curl(url, archive_timestamp=None, cache=CACHE, timeout=120):
    original, capture = archive_id(url, archive_timestamp)
    target = capture or original
    with tempfile.TemporaryDirectory() as tmp:
        body = Path(tmp) / 'body'
        done = subprocess.run(
            [
                'curl',
                '-sS',
                '-L',
                '--fail',
                '--max-time',
                str(timeout),
                '-A',
                USER_AGENT,
                '-o',
                str(body),
                '-w',
                '%{http_code}\\n%{url_effective}\\n%{content_type}',
                target,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if done.returncode:
            raise RuntimeError(
                json.dumps(
                    {
                        'url': target,
                        'tool': 'archive' if capture else 'curl',
                        'http_status': _status(done.stdout),
                        'error': done.stderr.strip() or f'curl exit {done.returncode}',
                    }
                )
            )
        status, final, media = ([*done.stdout.split('\n'), '', '', ''])[:3]
        return record(
            original,
            final or target,
            int(status),
            'archive' if capture else 'curl',
            media,
            body.read_bytes(),
            cache,
            archived_url=capture,
        )


def _status(text):
    try:
        return int(text.split('\n', 1)[0]) or None
    except ValueError:
        return None


def from_file(
    path, url, tool, final_url=None, media_type='', http_status=None, cache=CACHE, retrieved_at=None
):
    if tool not in TOOLS or tool == 'curl':
        raise ValueError(f'--from-file needs --tool tinyfish, manual or archive, not {tool!r}')
    original, capture = archive_id(url) if tool == 'archive' else (url, None)
    return record(
        original,
        final_url or capture or url,
        http_status,
        tool,
        media_type,
        Path(path).read_bytes(),
        cache,
        archived_url=capture,
        retrieved_at=retrieved_at,
    )


# Text extraction.

GS = os.environ.get('EVIDENCE_GHOSTSCRIPT') or shutil.which('gs') or 'gs'
_BLOCK = {
    'p',
    'div',
    'br',
    'li',
    'ul',
    'ol',
    'tr',
    'td',
    'th',
    'table',
    'h1',
    'h2',
    'h3',
    'h4',
    'h5',
    'h6',
    'section',
    'article',
    'header',
    'footer',
    'blockquote',
    'pre',
    'dt',
    'dd',
    'figcaption',
    'caption',
    'hr',
    'title',
    'main',
    'nav',
}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1
        elif tag in _BLOCK:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip = max(0, self.skip - 1)
        elif tag in _BLOCK:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def gs_version(gs=GS):
    return subprocess.run([gs, '--version'], capture_output=True, text=True, check=True).stdout.strip()


def _charset(content, media_type=''):
    found = re.search(r'charset=["\']?([A-Za-z0-9._-]+)', media_type, re.I) or re.search(
        rb'<meta[^>]+charset=["\']?([A-Za-z0-9._-]+)', content[:4096], re.I
    )
    name = found.group(1) if found else 'utf-8'
    return name.decode('ascii') if isinstance(name, bytes) else name


def extract_bytes(content, kind, media_type='', gs=GS):
    """(extractor id, text) for raw bytes of kind 'pdf', 'html' or 'txt'.

    Ghostscript runs once per page: in a whole-document run, state carried across pages can
    reorder a page's fragments from one run to the next, while single pages are reproducible and
    concatenate to the clean whole-document text.
    """
    if kind == 'pdf':
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'document.pdf'
            path.write_bytes(content)

            def run(*args):
                return subprocess.run(
                    [gs, '-q', '-dSAFER', f'--permit-file-read={path}', *args],
                    capture_output=True,
                    check=True,
                ).stdout

            count = int(
                run(
                    '-dNODISPLAY',
                    f'-sPDFFile={path}',
                    '-c',
                    'PDFFile (r) file runpdfbegin pdfpagecount = quit',
                )
            )
            pages = [
                run(
                    '-dNOPAUSE',
                    '-dBATCH',
                    f'-dFirstPage={page}',
                    f'-dLastPage={page}',
                    '-sDEVICE=txtwrite',
                    '-sOutputFile=-',
                    str(path),
                )
                for page in range(1, count + 1)
            ]
        return f'gs-{gs_version(gs)} txtwrite-pages', b''.join(pages).decode('utf-8', errors='replace')
    if kind == 'html':
        parser = _Text()
        try:
            decoded = content.decode(_charset(content, media_type), errors='replace')
        except LookupError:
            decoded = content.decode('utf-8', errors='replace')
        parser.feed(decoded)
        parser.close()
        return (
            f'html.parser-py{platform.python_version_tuple()[0]}.{platform.python_version_tuple()[1]} blocks-v1',
            ''.join(parser.parts),
        )
    if kind in ('txt', 'csv', 'json', 'xml'):
        return 'utf8-decode-v1', content.decode('utf-8', errors='replace')
    raise ValueError(f'No text extractor for .{kind} documents')


def text_path(raw_path):
    raw_path = Path(raw_path)
    return raw_path.with_name(raw_path.name.split('.')[0] + '.extracted.txt')


def extract(raw_path, media_type='', force=False, gs=GS):
    """Extract once and cache. Returns {extractor, sha256, cache_path}."""
    raw_path = Path(raw_path)
    target = text_path(raw_path)
    sidecar = target.with_suffix('.json')
    if not force and target.exists() and sidecar.exists():
        meta = json.loads(sidecar.read_text(encoding='utf-8'))
        if hashlib.sha256(target.read_bytes()).hexdigest() == meta['sha256']:
            return {'extractor': meta['extractor'], 'sha256': meta['sha256'], 'cache_path': relative(target)}
    extractor, text = extract_bytes(
        raw_path.read_bytes(), raw_path.suffix.lstrip('.').lower(), media_type, gs
    )
    encoded = text.encode('utf-8')
    sha = hashlib.sha256(encoded).hexdigest()
    target.write_bytes(encoded)
    sidecar.write_text(
        json.dumps({'extractor': extractor, 'sha256': sha}, indent=2) + '\n', encoding='utf-8', newline=''
    )
    return {'extractor': extractor, 'sha256': sha, 'cache_path': relative(target)}


# The options of a retrieval, by their argparse names, as a command line writes them. --extract takes
# none of them, so their argparse defaults are None: a given option is never taken for a default.
RETRIEVAL = {
    'url': 'URL',
    'url_option': '--url',
    'from_file': '--from-file',
    'tool': '--tool',
    'final_url': '--final-url',
    'http_status': '--http-status',
    'archive_timestamp': '--archive-timestamp',
    'cache': '--cache',
    'out': '--out',
}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('url', nargs='?')
    p.add_argument('--url', dest='url_option', help='Requested URL for --from-file')
    p.add_argument(
        '--from-file', help='Bytes obtained another way (TinyFish render, manual download, archive capture)'
    )
    p.add_argument('--tool', choices=TOOLS)
    p.add_argument('--final-url')
    p.add_argument('--media-type', default='', help='The media type of the bytes, in both modes')
    p.add_argument('--http-status', type=int)
    p.add_argument(
        '--archive-timestamp',
        help='Fetch the archive.org id_ capture at this timestamp instead of the live URL',
    )
    p.add_argument('--cache')
    p.add_argument('--out')
    p.add_argument(
        '--extract', metavar='PATH', help='Extract the text of these cached bytes; retrieve nothing'
    )
    p.add_argument('--force', action='store_true', help='With --extract: replace an existing extraction')
    a = p.parse_args(argv)
    if a.extract is not None:
        given = [flag for name, flag in RETRIEVAL.items() if getattr(a, name) is not None]
        if given:
            p.error(f'--extract does not take {", ".join(given)}')
        print(json.dumps(extract(a.extract, a.media_type, a.force), indent=2))
        return 0
    if a.force:
        p.error('--force applies only to --extract')
    url = a.url_option or a.url
    if not url:
        p.error('a URL is required')
    cache = str(CACHE) if a.cache is None else a.cache
    try:
        result = (
            from_file(a.from_file, url, a.tool or 'manual', a.final_url, a.media_type, a.http_status, cache)
            if a.from_file
            else curl(url, a.archive_timestamp, cache)
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    text = json.dumps(result, indent=2, ensure_ascii=True) + '\n'
    if a.out:
        Path(a.out).write_text(text, encoding='utf-8', newline='')
    else:
        sys.stdout.write(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
