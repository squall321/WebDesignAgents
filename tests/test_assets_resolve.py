# wdpipeline.assets 테스트 — 로컬/매핑/REST 해결·미해결 사유 기록·이미지 메타·리사이즈·빌드 복사
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from wdpipeline.assets import DEFAULT_MAX_EDGE, copy_assets_to_build, resolve_assets

RA_ENV = ("WDA_RA_BASE_URL", "WDA_RA_TOKEN", "WDA_RA_EMAIL", "WDA_RA_PASSWORD", "WDA_RA_WORKSPACE")


@pytest.fixture(autouse=True)
def no_rest_env(monkeypatch: pytest.MonkeyPatch):
    """실행 환경의 WDA_RA_* 가 테스트를 네트워크로 끌고 가지 않게 격리한다."""
    for key in RA_ENV:
        monkeypatch.delenv(key, raising=False)


def _img(path: Path, size: tuple[int, int], color=(20, 80, 160)) -> Path:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


def test_resolve_by_glob(tmp_path: Path):
    _img(tmp_path / "f-1.png", (400, 200))
    (rec,) = resolve_assets(["f-1"], assets_dir=tmp_path)
    assert rec["status"] == "resolved"
    assert rec["source"] == "assets_dir"
    assert rec["local_path"] == str(tmp_path / "f-1.png")
    assert (rec["width"], rec["height"]) == (400, 200)
    assert rec["aspect"] == 2.0
    assert rec["media_type"] == "image"
    assert rec["format"] == "PNG"
    assert rec["reason"] is None


def test_resolve_by_mapping_file(tmp_path: Path):
    _img(tmp_path / "photos" / "hero-final.png", (300, 300))
    (tmp_path / "assets.json").write_text(
        json.dumps({"f-hero": "photos/hero-final.png"}), encoding="utf-8"
    )
    (rec,) = resolve_assets(["f-hero"], assets_dir=tmp_path)
    assert rec["source"] == "assets_json"
    assert rec["local_path"] == str(tmp_path / "photos" / "hero-final.png")


def test_unresolved_records_reason(tmp_path: Path):
    """조용한 누락 금지 — 미해결도 한 줄 남고 사유에 로컬·REST 양쪽이 적힌다."""
    (rec,) = resolve_assets(["f-nope"], assets_dir=tmp_path)
    assert rec["status"] == "unresolved"
    assert rec["local_path"] is None
    assert "로컬 미발견" in rec["reason"]
    assert "WDA_RA" in rec["reason"]


def test_unresolved_without_assets_dir():
    (rec,) = resolve_assets(["f-nope"])
    assert rec["status"] == "unresolved"
    assert "assets_dir 미지정" in rec["reason"]


def test_non_image_resolved_with_meta_error(tmp_path: Path):
    (tmp_path / "f-doc.bin").write_bytes(b"not an image")
    (rec,) = resolve_assets(["f-doc"], assets_dir=tmp_path)
    assert rec["status"] == "resolved"
    assert rec["media_type"] == "other"
    assert rec["width"] is None
    assert "이미지 메타를 읽지 못했다" in rec["meta_error"]


def test_run_dir_collects_and_resizes(tmp_path: Path):
    src = _img(tmp_path / "src" / "f-big.png", (2400, 1200))
    run_dir = tmp_path / "run"
    (rec,) = resolve_assets(["f-big"], assets_dir=tmp_path / "src", run_dir=run_dir)

    assert rec["local_path"] == str(run_dir / "assets" / "f-big.png")
    assert (rec["width"], rec["height"]) == (DEFAULT_MAX_EDGE, 960)
    assert rec["resized"] is True
    assert Path(rec["original_path"]).is_file()
    # 사용자 원본은 절대 건드리지 않는다
    from PIL import Image

    with Image.open(src) as im:
        assert im.size == (2400, 1200)


def test_small_image_not_resized(tmp_path: Path):
    _img(tmp_path / "f-s.png", (1200, 800))
    (rec,) = resolve_assets(["f-s"], assets_dir=tmp_path, run_dir=tmp_path / "run")
    assert rec["resized"] is False
    assert rec["original_path"] is None
    assert (rec["width"], rec["height"]) == (1200, 800)


def test_copy_assets_to_build_excludes_originals(tmp_path: Path):
    _img(tmp_path / "src" / "f-big.png", (2400, 1200))
    run_dir, build_dir = tmp_path / "run", tmp_path / "build"
    resolve_assets(["f-big"], assets_dir=tmp_path / "src", run_dir=run_dir)

    copied = copy_assets_to_build(run_dir, build_dir)
    assert [c["rel_path"] for c in copied] == ["assets/f-big.png"]
    assert (build_dir / "assets" / "f-big.png").is_file()
    assert not (build_dir / "assets" / "f-big.orig.png").exists()


def test_copy_assets_to_build_no_assets(tmp_path: Path):
    assert copy_assets_to_build(tmp_path / "empty_run", tmp_path / "build") == []


def test_empty_input_returns_empty():
    assert resolve_assets([]) == []
    assert resolve_assets(["", "  "]) == []


# --- ② REST 모드 (로컬 스텁 서버로 실검증) ---------------------------------


class _FilesHandler(BaseHTTPRequestHandler):
    payload = b""

    def do_GET(self):  # noqa: N802 (BaseHTTPRequestHandler 계약)
        if self.path.startswith("/api/files/f-ok"):
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(self.payload)))
            self.end_headers()
            self.wfile.write(self.payload)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):  # 테스트 로그 소음 제거
        pass


@pytest.fixture
def files_server(tmp_path: Path):
    png = _img(tmp_path / "seed.png", (2400, 600)).read_bytes()
    _FilesHandler.payload = png
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FilesHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_rest_download_and_normalize(files_server: str, tmp_path: Path):
    run_dir = tmp_path / "run"
    (rec,) = resolve_assets(["f-ok"], base_url=files_server, token="dummy", run_dir=run_dir)
    assert rec["status"] == "resolved"
    assert rec["source"] == "rest"
    assert rec["local_path"] == str(run_dir / "assets" / "f-ok.png")
    assert rec["width"] == DEFAULT_MAX_EDGE  # 2400 → 1920 리사이즈
    assert rec["resized"] is True


def test_rest_http_error_recorded(files_server: str, tmp_path: Path):
    (rec,) = resolve_assets(["f-missing"], base_url=files_server, token="dummy",
                            run_dir=tmp_path / "run")
    assert rec["status"] == "unresolved"
    assert "HTTP 404" in rec["reason"]


def test_rest_skipped_without_credentials(files_server: str, tmp_path: Path):
    """base_url 만 있고 토큰·계정이 없으면 네트워크를 치지 않고 사유만 남긴다."""
    (rec,) = resolve_assets(["f-ok"], base_url=files_server, run_dir=tmp_path / "run")
    assert rec["status"] == "unresolved"
    assert "WDA_RA_TOKEN" in rec["reason"]


def test_local_wins_over_rest(files_server: str, tmp_path: Path):
    _img(tmp_path / "f-ok.png", (100, 100))
    (rec,) = resolve_assets(["f-ok"], assets_dir=tmp_path, base_url=files_server, token="dummy")
    assert rec["source"] == "assets_dir"
    assert (rec["width"], rec["height"]) == (100, 100)
