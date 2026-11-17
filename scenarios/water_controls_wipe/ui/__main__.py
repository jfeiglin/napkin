"""The helper of the package's live view (ui/README.md). Run it from the root of the checkout:

    python -B -m scenarios.water_controls_wipe.ui setup    # install the page's own packages (Node.js and npm)
    python -B -m scenarios.water_controls_wipe.ui serve    # build the page if it changed, and serve it
    python -B -m scenarios.water_controls_wipe.ui dev      # serve the engine, and the page with live reload
    python -B -m scenarios.water_controls_wipe.ui test     # the page's own tests

The page's packages go in ui/web/node_modules, beside the page: nothing of them goes into the repository's
own environment."""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent / 'web'
NODE = 20  # the oldest major version of Node.js that the page's build tools support


def tool(name):
    found = shutil.which(name)
    if found is None:
        sys.exit(
            f'The live view needs Node.js {NODE} or later, with npm. Install it from https://nodejs.org.'
        )
    return found


def npm(*args, **options):
    return subprocess.run([tool('npm'), *args], cwd=WEB, check=True, **options)


def setup():
    version = subprocess.run([tool('node'), '--version'], capture_output=True, text=True, check=True).stdout
    major = int(re.match(r'v(\d+)', version.strip()).group(1))
    if major < NODE:
        sys.exit(f'The live view needs Node.js {NODE} or later; this computer has {version.strip()}.')
    npm('ci', '--no-audit', '--no-fund')


def installed():
    if not (WEB / 'node_modules').is_dir():
        sys.exit(
            'The page has no packages yet: run `python -B -m scenarios.water_controls_wipe.ui setup` first.'
        )


def stale():
    """The built page is missing, or older than a file that it is built from."""
    built = WEB / 'dist' / 'index.html'
    if not built.exists():
        return True
    sources = [
        *(WEB / 'src').rglob('*'),
        *(WEB / name for name in ('index.html', 'package-lock.json', 'vite.config.ts')),
    ]
    return any(path.is_file() and path.stat().st_mtime > built.stat().st_mtime for path in sources)


def serve(port, jobs, hosts):
    from scenarios.water_controls_wipe.ui import server, view

    installed()
    if stale():
        npm('run', 'build', '--', '--logLevel', 'warn')
    engine = server.Engine(view.places(), jobs)
    found = server.server(engine, port, hosts=hosts)
    print(f'The live view of {len(engine.names)} places: http://localhost:{found.server_address[1]}/')
    try:
        found.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        found.server_close()
        engine.close()


def dev(port, jobs, hosts):
    """The engine's server on `port`, and Vite's server of the page beside it, which sends /api to it."""
    from scenarios.water_controls_wipe.ui import server, view

    installed()
    engine = server.Engine(view.places(), jobs)
    found = server.server(engine, port, hosts=hosts)
    page = subprocess.Popen(
        [tool('npm'), 'run', 'dev'], cwd=WEB, env={**os.environ, 'VIEW_API': f'http://127.0.0.1:{port}'}
    )
    try:
        found.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        page.terminate()
        found.server_close()
        engine.close()


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='python -B -m scenarios.water_controls_wipe.ui', description=__doc__
    )
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('setup', help="install the page's own packages")
    for name in ('serve', 'dev'):
        command = commands.add_parser(
            name, help='serve the live view' if name == 'serve' else 'serve it with live reload'
        )
        command.add_argument('--port', type=int, default=8765)
        command.add_argument('--jobs', type=int, default=4, help='worker processes of the engine')
        command.add_argument(
            '--host',
            action='append',
            default=[],
            help='another name of this computer that the server answers to',
        )
    commands.add_parser('test', help="the page's own tests")
    args = parser.parse_args(argv)
    if args.command == 'setup':
        setup()
    elif args.command == 'test':
        installed()
        npm('test')
    else:
        hosts = ('localhost', '127.0.0.1', *args.host)
        (serve if args.command == 'serve' else dev)(args.port, args.jobs, hosts)


if __name__ == '__main__':
    main()
