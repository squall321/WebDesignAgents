# P0 자산 파이프라인 — file_id 를 로컬 디렉터리/REST 로 해결하고 이미지를 run 디렉터리에 정규화해 모은다
from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
from pathlib import Path
from typing import Any, Iterable

# 렌더 성능 상한 — 긴 변이 이보다 크면 리사이즈(원본은 .orig 로 보존)
DEFAULT_MAX_EDGE = 1920

# assets_dir 안의 선택적 매핑 파일 — {file_id: 상대경로} 또는 {"assets": {...}} 봉투
MAPPING_FILE = "assets.json"

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".avif"}
_SAFE_RE = re.compile(r"[^\w.\-]")


# ---------------------------------------------------------------------------
# 레코드 — 해결 실패도 reason 과 함께 반드시 한 줄 남긴다(조용한 누락 금지)
# ---------------------------------------------------------------------------


def _record(file_id: str, **kw: Any) -> dict:
    rec: dict[str, Any] = {
        "file_id": file_id,
        "local_path": None,      # 해결된 경로(run_dir 지정 시 정규화 사본 경로)
        "status": "unresolved",  # resolved | unresolved
        "source": None,          # assets_json | assets_dir | rest
        "reason": None,          # 미해결 사유 — status=unresolved 일 때만 채움
        "media_type": None,      # image | other
        "format": None,          # PNG/JPEG/... (Pillow format)
        "width": None,
        "height": None,
        "aspect": None,          # width/height (소수 4자리)
        "bytes": None,
        "original_path": None,   # 리사이즈했을 때 원본 사본
        "resized": False,
        "meta_error": None,      # 해결은 됐으나 이미지 메타를 못 읽은 사유
    }
    rec.update(kw)
    return rec


def _safe_name(file_id: str) -> str:
    return _SAFE_RE.sub("_", str(file_id)) or "asset"


# ---------------------------------------------------------------------------
# ① 로컬 디렉터리 모드
# ---------------------------------------------------------------------------


def _load_mapping(assets_dir: Path) -> dict[str, str]:
    """assets_dir/assets.json 의 {file_id: 상대경로} 매핑을 읽는다. 없거나 깨지면 빈 매핑."""
    path = assets_dir / MAPPING_FILE
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(data, dict) and isinstance(data.get("assets"), dict):
        data = data["assets"]
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, (str, Path))}


def _resolve_local(assets_dir: Path, mapping: dict[str, str], file_id: str) -> tuple[Path | None, str | None]:
    """(경로, source) 를 반환. 못 찾으면 (None, None)."""
    mapped = mapping.get(file_id)
    if mapped:
        cand = Path(mapped)
        if not cand.is_absolute():
            cand = assets_dir / cand
        if cand.is_file():
            return cand, "assets_json"
    exact = assets_dir / file_id
    if exact.is_file():
        return exact, "assets_dir"
    matches = sorted(p for p in assets_dir.glob(f"{file_id}.*") if p.is_file())
    if matches:
        return matches[0], "assets_dir"
    return None, None


# ---------------------------------------------------------------------------
# ② REST 모드 — WDA_RA_* 자격증명이 있을 때만 동작(없으면 reason 남기고 스킵)
# ---------------------------------------------------------------------------


def _rest_context(base_url: str | None, token: str | None) -> tuple[dict | None, str]:
    """({base, headers}, "") 또는 (None, 스킵 사유)."""
    base = (base_url or os.environ.get("WDA_RA_BASE_URL") or "").strip().rstrip("/")
    if not base:
        return None, "REST 미설정 — base_url 인자나 WDA_RA_BASE_URL 이 없다."
    tok = (token or os.environ.get("WDA_RA_TOKEN") or "").strip()
    if not tok:
        email = os.environ.get("WDA_RA_EMAIL") or ""
        password = os.environ.get("WDA_RA_PASSWORD") or ""
        if not (email and password):
            return None, "REST 자격증명 미설정 — WDA_RA_TOKEN 또는 WDA_RA_EMAIL/WDA_RA_PASSWORD 를 채워라."
        try:
            import httpx

            with httpx.Client(base_url=base, timeout=30) as client:
                resp = client.post("/api/auth/login", json={"email": email, "password": password})
                body = resp.json()
            if resp.status_code >= 400 or not body.get("success", True):
                return None, f"REST 로그인 실패 (HTTP {resp.status_code})."
            tok = str((body.get("data") or body).get("access_token") or "")
        except Exception as exc:  # 네트워크·형식 문제는 스킵 사유로만 남긴다
            return None, f"REST 로그인 예외 — {type(exc).__name__}: {exc}"
        if not tok:
            return None, "REST 로그인 응답에 access_token 이 없다."
    headers = {"Authorization": f"Bearer {tok}"}
    workspace = os.environ.get("WDA_RA_WORKSPACE")
    if workspace:
        headers["X-Workspace-Slug"] = workspace
    return {"base": base, "headers": headers}, ""


def _download(ctx: dict, file_id: str, dest_dir: Path) -> tuple[Path | None, str | None]:
    """GET /api/files/{file_id} 로 바이트를 받아 dest_dir 에 저장한다."""
    try:
        import httpx

        with httpx.Client(base_url=ctx["base"], timeout=60) as client:
            resp = client.get(f"/api/files/{file_id}", headers=ctx["headers"])
    except Exception as exc:
        return None, f"REST 다운로드 예외 — {type(exc).__name__}: {exc}"
    if resp.status_code >= 400:
        return None, f"REST 다운로드 실패 (HTTP {resp.status_code})."
    ctype = (resp.headers.get("content-type") or "").split(";")[0].strip()
    if ctype == "application/json":
        return None, "REST 응답이 파일 바이트가 아니라 JSON 이다 — file_id 가 유효한지 확인하라."
    ext = mimetypes.guess_extension(ctype) or ""
    if ext == ".jpe":
        ext = ".jpg"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{_safe_name(file_id)}{ext}"
    dest.write_bytes(resp.content)
    return dest, None


def _default_cache_dir() -> Path:
    """run_dir 없이 REST 로 받은 바이트를 둘 공용 캐시 — data/assets_cache/."""
    try:
        from wdcore.config import get_settings

        data_dir = get_settings().data_dir
    except Exception:
        data_dir = Path("data")
    if not data_dir.is_absolute():
        data_dir = Path(__file__).resolve().parents[2] / data_dir
    return data_dir / "assets_cache"


# ---------------------------------------------------------------------------
# 이미지 정규화 — 메타 추출 + (사본일 때만) 긴 변 리사이즈
# ---------------------------------------------------------------------------


def _read_image_meta(path: Path) -> tuple[dict, str | None]:
    try:
        from PIL import Image

        with Image.open(path) as im:
            width, height = im.size
            fmt = im.format
    except Exception as exc:
        return {}, f"{type(exc).__name__}: {exc}"
    aspect = round(width / height, 4) if height else None
    return {"width": width, "height": height, "aspect": aspect, "format": fmt}, None


def _resize_in_place(path: Path, max_edge: int) -> tuple[Path | None, dict]:
    """긴 변을 max_edge 로 줄인다. 원본은 {stem}.orig{suffix} 로 보존. (원본경로, 새 메타)."""
    from PIL import Image

    original = path.with_name(f"{path.stem}.orig{path.suffix}")
    shutil.copy2(path, original)
    with Image.open(path) as im:
        width, height = im.size
        scale = max_edge / float(max(width, height))
        new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        fmt = im.format or "PNG"
        resized = im.resize(new_size, Image.LANCZOS)
        if fmt in ("JPEG", "JPG") and resized.mode in ("RGBA", "P", "LA"):
            resized = resized.convert("RGB")
        resized.save(path, format=fmt)
    meta, _ = _read_image_meta(path)
    return original, meta


def _apply_media_meta(rec: dict, path: Path, *, owned: bool, max_edge: int) -> None:
    """레코드에 크기·포맷·바이트를 채우고, 사본(owned)일 때만 리사이즈한다."""
    rec["bytes"] = path.stat().st_size
    meta, err = _read_image_meta(path)
    if err:
        rec["media_type"] = "other"
        rec["meta_error"] = f"이미지 메타를 읽지 못했다 — {err}"
        return
    rec["media_type"] = "image"
    rec.update(meta)
    if owned and max_edge and max(meta["width"], meta["height"]) > max_edge:
        try:
            original, new_meta = _resize_in_place(path, max_edge)
        except Exception as exc:
            rec["meta_error"] = f"리사이즈 실패 — {type(exc).__name__}: {exc}"
            return
        rec["original_path"] = str(original)
        rec["resized"] = True
        rec.update(new_meta)
        rec["bytes"] = path.stat().st_size


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------


def resolve_assets(
    file_ids: Iterable[str],
    *,
    assets_dir: Path | str | None = None,
    base_url: str | None = None,
    token: str | None = None,
    run_dir: Path | str | None = None,
    max_edge: int = DEFAULT_MAX_EDGE,
) -> list[dict]:
    """file_id 목록을 로컬/REST 로 해결해 자산 레코드 목록을 만든다.

    ① assets_dir 이 있으면 매핑 파일(assets.json) → {file_id}.* 순으로 찾는다.
    ② 로컬에서 못 찾고 REST 자격증명(base_url/WDA_RA_*)이 있으면 GET /api/files/{file_id} 로 받는다.
    ③ 어느 쪽으로도 못 찾으면 status=unresolved 와 reason 을 남긴다.

    run_dir 을 주면 해결된 파일을 run_dir/assets/ 로 모으고(그 사본에 한해) 긴 변이
    max_edge 를 넘으면 리사이즈한다. run_dir 이 없으면 원본 위치를 그대로 가리키고
    사용자 파일은 절대 건드리지 않는다.
    """
    ids = [str(f) for f in file_ids if str(f).strip()]
    if not ids:
        return []

    adir = Path(assets_dir) if assets_dir else None
    mapping = _load_mapping(adir) if adir and adir.is_dir() else {}
    run_assets = Path(run_dir) / "assets" if run_dir else None

    ctx: dict | None = None
    rest_skip = ""
    rest_tried = False

    records: list[dict] = []
    for fid in ids:
        rec = _record(fid)
        src_path: Path | None = None
        source: str | None = None
        reasons: list[str] = []

        if adir is None:
            reasons.append("assets_dir 미지정.")
        elif not adir.is_dir():
            reasons.append(f"assets_dir 없음 — {adir}")
        else:
            src_path, source = _resolve_local(adir, mapping, fid)
            if src_path is None:
                reasons.append(f"로컬 미발견 — {adir}/{fid}.* 및 {MAPPING_FILE} 매핑에 없다.")

        if src_path is None:
            if not rest_tried:
                ctx, rest_skip = _rest_context(base_url, token)
                rest_tried = True
            if ctx is None:
                reasons.append(rest_skip)
            else:
                dest = run_assets or (adir if adir and adir.is_dir() else _default_cache_dir())
                got, err = _download(ctx, fid, dest)
                if got is None:
                    reasons.append(err or "REST 다운로드 실패.")
                else:
                    src_path, source = got, "rest"

        if src_path is None:
            rec["reason"] = " ".join(r for r in reasons if r)
            records.append(rec)
            continue

        # 우리가 만든 사본(REST 다운로드분·run_dir 수집분)만 리사이즈 대상이다.
        owned = source == "rest"
        final = src_path
        if run_assets is not None and src_path.parent != run_assets:
            run_assets.mkdir(parents=True, exist_ok=True)
            final = run_assets / f"{_safe_name(fid)}{src_path.suffix}"
            shutil.copy2(src_path, final)
            owned = True

        rec["status"] = "resolved"
        rec["source"] = source
        rec["local_path"] = str(final)
        _apply_media_meta(rec, final, owned=owned, max_edge=max_edge)
        records.append(rec)

    return records


def copy_assets_to_build(run_dir: Path | str, build_dir: Path | str) -> list[dict]:
    """run_dir/assets/ 의 렌더용 자산을 build_dir/assets/ 로 복사한다.

    .orig 사본(리사이즈 전 원본)은 렌더에 필요 없으므로 제외한다.
    반환은 [{file_name, rel_path, bytes}] — rel_path 는 빌드 엔트리 기준 상대 경로.
    """
    src = Path(run_dir) / "assets"
    if not src.is_dir():
        return []
    dest = Path(build_dir) / "assets"
    dest.mkdir(parents=True, exist_ok=True)
    out: list[dict] = []
    for path in sorted(p for p in src.iterdir() if p.is_file()):
        if ".orig" in path.suffixes or path.stem.endswith(".orig"):
            continue
        target = dest / path.name
        shutil.copy2(path, target)
        out.append({
            "file_name": path.name,
            "rel_path": f"assets/{path.name}",
            "bytes": target.stat().st_size,
        })
    return out


def asset_index(records: list[dict]) -> dict[str, dict]:
    """file_id → 레코드 조회 인덱스 (씬 조립에서 블록의 file_id 로 자산을 찾을 때)."""
    return {r["file_id"]: r for r in records if r.get("file_id")}
