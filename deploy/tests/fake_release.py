#!/usr/bin/env python3
"""テスト用の偽の GitHub リリースサーバー (127.0.0.1 のみ)。

使い方: fake_release.py <ルートディレクトリ>
  /latest            -> ルートの LATEST ファイルの版へ 302 (/tag/v<版>)。LATEST がなければ 404
  /download/...      -> ルート以下のファイル
  /health            -> ルートに healthy ファイルがあれば 200、なければ 503
ポート番号は、起動後にルートの port ファイルに書く。
"""

import http.server
import os
import sys

root = os.path.realpath(sys.argv[1])


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/latest":
            latest = os.path.join(root, "LATEST")
            if not os.path.exists(latest):
                return self.send_error(404)
            with open(latest) as handle:
                version = handle.read().strip()
            self.send_response(302)
            self.send_header("Location", f"/tag/v{version}")
            self.end_headers()
            return
        if self.path == "/health":
            healthy = os.path.exists(os.path.join(root, "healthy"))
            self.send_response(200 if healthy else 503)
            self.end_headers()
            return
        if self.path.startswith("/download/"):
            target = os.path.realpath(os.path.join(root, self.path.lstrip("/")))
            if target.startswith(root + os.sep) and os.path.isfile(target):
                with open(target, "rb") as handle:
                    data = handle.read()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
        self.send_error(404)


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
with open(os.path.join(root, "port"), "w") as handle:
    handle.write(str(server.server_address[1]))
server.serve_forever()
