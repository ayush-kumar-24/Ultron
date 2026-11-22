#!/usr/bin/env python3
"""Zero-dependency dev server for the ULTRON frontend.

    python serve.py                 # http://127.0.0.1:5173
    python serve.py --port 8080
    python serve.py --api http://127.0.0.1:8000

--api proxies /api/* to your backend so the browser sees one origin (no CORS setup needed).
This is a development convenience only. In production, serve this folder from your backend
or any static host and point config.js at the API.
"""
import argparse, functools, http.server, json, os, socketserver, sys, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))


class Handler(http.server.SimpleHTTPRequestHandler):
    api_target = None

    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        '.js': 'application/javascript; charset=utf-8',
        '.mjs': 'application/javascript; charset=utf-8',
        '.css': 'text/css; charset=utf-8',
        '.html': 'text/html; charset=utf-8',
        '.json': 'application/json; charset=utf-8',
        '.svg': 'image/svg+xml',
        '.webmanifest': 'application/manifest+json',
    }

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):
        if '/api/' in (self.path or '') or self.command != 'GET':
            sys.stderr.write('%s %s\n' % (self.command, self.path))

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    # ---- API proxy ----
    def _proxy(self):
        url = self.api_target.rstrip('/') + self.path
        length = int(self.headers.get('content-length') or 0)
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in ('host', 'connection', 'content-length', 'accept-encoding')}
        req = urllib.request.Request(url, data=body, headers=headers, method=self.command)
        try:
            with urllib.request.urlopen(req, timeout=300) as up:
                self.send_response(up.status)
                for k, v in up.headers.items():
                    if k.lower() not in ('transfer-encoding', 'connection', 'content-encoding', 'content-length'):
                        self.send_header(k, v)
                self.end_headers()
                # stream (works for SSE and chunked LLM responses)
                while True:
                    chunk = up.read(1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except urllib.error.HTTPError as e:
            payload = e.read()
            self.send_response(e.code)
            self.send_header('content-type', e.headers.get('content-type', 'application/json'))
            self.end_headers()
            self.wfile.write(payload)
        except Exception as e:                                    # backend down
            self.send_response(502)
            self.send_header('content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'detail': f'Backend unreachable: {e}'}).encode())

    def _is_api(self):
        return self.path.startswith('/api/')

    def _no_backend(self):
        """No --api proxy configured: answer API calls honestly so the app falls back to its
        built-in demo backend. Never serve index.html here - the client would parse HTML as JSON."""
        self.send_response(404)
        self.send_header('content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'detail': 'No backend configured. Start serve.py --api <url>, or set mode to mock/live in config.js.'}).encode())

    def _api(self):
        return self._proxy() if self.api_target else self._no_backend()

    def do_GET(self):
        if self._is_api():
            return self._api()
        # SPA: the app is hash-routed, so only bare/unknown paths need the shell
        path = self.path.split('?')[0]
        if path == '/' or (not os.path.splitext(path)[1] and not os.path.exists(os.path.join(ROOT, path.lstrip('/')))):
            self.path = '/index.html'
        return super().do_GET()

    def do_POST(self):
        return self._api() if self._is_api() else self.send_error(405)

    def do_PATCH(self):
        return self._api() if self._is_api() else self.send_error(405)

    def do_PUT(self):
        return self._api() if self._is_api() else self.send_error(405)

    def do_DELETE(self):
        return self._api() if self._is_api() else self.send_error(405)


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=5173)
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--api', default=None, help='Proxy /api/* to this backend, e.g. http://127.0.0.1:8000')
    args = ap.parse_args()
    Handler.api_target = args.api
    with Server((args.host, args.port), Handler) as httpd:
        print(f'ULTRON frontend  ->  http://{args.host}:{args.port}')
        print(f'  serving  {ROOT}')
        print(f'  api      {"proxy -> " + args.api if args.api else "not proxied (config.js decides: auto/mock/live)"}')
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\nstopped')


if __name__ == '__main__':
    main()
