# build 디렉터리를 127.0.0.1 임시 포트로 서빙하는 스레드형 정적 http 서버 (컨텍스트 매니저)
from __future__ import annotations

import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote


class _QuietHandler(SimpleHTTPRequestHandler):
    """요청 로그를 stdout에 찍지 않는 핸들러."""

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass


class StaticServer:
    """root_dir 를 로컬 http로 서빙한다. x-import/폰트 인라인이 fetch 기반이라 file:// 불가.

    사용:
        with StaticServer(build_dir) as srv:
            url = srv.url_for("HWAX 소개영상.dc.html")
    """

    def __init__(self, root_dir: str | Path, host: str = "127.0.0.1", port: int = 0):
        self.root_dir = Path(root_dir).resolve()
        if not self.root_dir.is_dir():
            raise NotADirectoryError(f"서빙 루트가 디렉터리가 아님: {self.root_dir}")
        self.host = host
        self.port = port
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "StaticServer":
        handler = partial(_QuietHandler, directory=str(self.root_dir))
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._httpd = None
        self._thread = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def url_for(self, relpath: str | Path) -> str:
        """루트 기준 상대 경로를 퍼센트 인코딩한 절대 URL로 만든다 (한글·공백 파일명 대응)."""
        rel = str(Path(relpath).as_posix()).lstrip("/")
        return f"{self.base_url}/{quote(rel)}"
