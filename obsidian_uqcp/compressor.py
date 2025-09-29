"""Obsidian → UQCP compressor.

Scan an Obsidian vault, push Markdown files through an Ollama prompt, and write
compressed artifacts. Can also run a lightweight HTTP server so external tools
can request compression for a single note on demand.
"""

from __future__ import annotations

import argparse
import dataclasses
import http.server
import json
import logging
import os
import socketserver
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import requests
import yaml
from tqdm import tqdm

CONFIG_PATH = Path(__file__).with_name("config.yaml")
PROMPT_PATH = Path(__file__).parent / "prompts" / "uqcp_prompt.txt"
CACHE_FILE = "_cache.json"
INDEX_FILE = "_index.json"
AGGREGATE_FILE = "_folder_aggregate.uqcp.md"

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("uqcp")


@dataclass
class Config:
    vault_path: Path
    output_folder_name: str
    ollama_host: str
    ollama_model: str
    ollama_temperature: float
    ollama_num_ctx: int
    changed_only: bool
    max_section_chars: int
    aggregate_by_folder: bool
    include_extensions: List[str]
    exclude_folders: List[str]
    server_host: str
    server_port: int

    @staticmethod
    def from_dict(data: Dict) -> "Config":
        return Config(
            vault_path=Path(data["vault_path"]).expanduser(),
            output_folder_name=data.get("output_folder_name", "_compressed"),
            ollama_host=data["ollama"]["host"],
            ollama_model=data["ollama"]["model"],
            ollama_temperature=float(data["ollama"].get("temperature", 0.2)),
            ollama_num_ctx=int(data["ollama"].get("num_ctx", 120000)),
            changed_only=bool(data.get("processing", {}).get("changed_only", False)),
            max_section_chars=int(data.get("processing", {}).get("max_section_chars", 18000)),
            aggregate_by_folder=bool(data.get("processing", {}).get("aggregate_by_folder", True)),
            include_extensions=[ext.lower() for ext in data.get("filters", {}).get("include_extensions", [".md"])],
            exclude_folders=[fld for fld in data.get("filters", {}).get("exclude_folders", [])],
            server_host=data.get("server", {}).get("host", "127.0.0.1"),
            server_port=int(data.get("server", {}).get("port", 42121)),
        )


def load_config() -> Config:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config file not found: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return Config.from_dict(data)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def split_frontmatter(text: str) -> Tuple[str, str]:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[1].strip(), parts[2].lstrip()
    return "", text


def chunk_text(text: str, max_chars: int) -> List[str]:
    if len(text) <= max_chars:
        return [text]
    chunks: List[str] = []
    cursor = 0
    while cursor < len(text):
        chunks.append(text[cursor : cursor + max_chars])
        cursor += max_chars
    return chunks


def build_prompt(template: str, *, title: str, path: Path, frontmatter: str, body: str) -> str:
    prompt = template
    prompt = prompt.replace("{{title}}", title)
    prompt = prompt.replace("{{path}}", str(path))
    prompt = prompt.replace("{{frontmatter}}", frontmatter if frontmatter else "(none)")
    prompt = prompt.replace("{{body}}", body)
    return prompt


def sha1(text: str) -> str:
    import hashlib

    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def sha256(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def call_ollama(host: str, model: str, prompt: str, *, temperature: float, num_ctx: int) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": num_ctx},
    }
    response = requests.post(f"{host.rstrip('/')}/api/generate", json=payload, timeout=1200)
    response.raise_for_status()
    data = response.json()
    return data.get("response", "")


def discover_files(root: Path, *, include_exts: Iterable[str], exclude_folders: Iterable[str]) -> List[Path]:
    include = tuple(include_exts)
    exclude = set(exclude_folders)
    files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in exclude]
        for filename in filenames:
            if filename.lower().endswith(include):
                files.append(Path(dirpath) / filename)
    return files


def load_prompt_template() -> str:
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"Prompt template not found: {PROMPT_PATH}")
    return read_text(PROMPT_PATH)


def load_cache(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    try:
        return json.loads(read_text(path))
    except Exception:
        logger.warning("Cache file is corrupted, rebuilding")
        return {}


def save_cache(path: Path, data: Dict[str, str]) -> None:
    write_text(path, json.dumps(data, indent=2))


def compress_markdown(path: Path, *, cfg: Config, prompt_template: str, cache: Dict[str, str], out_dir: Path) -> Dict[str, str]:
    raw = read_text(path)
    frontmatter, body = split_frontmatter(raw)
    sections = chunk_text(body, cfg.max_section_chars)
    prepared_body = []
    for idx, chunk in enumerate(sections, start=1):
        prepared_body.append(f"[SECTION {idx}/{len(sections)}]\n{chunk.strip()}\n")
    full_body = "\n".join(prepared_body)
    prompt = build_prompt(
        prompt_template,
        title=path.stem,
        path=path,
        frontmatter=frontmatter,
        body=full_body,
    )
    cache_key = sha1(prompt)
    rel_key = str(path)
    if cfg.changed_only and cache.get(rel_key) == cache_key:
        return {"path": rel_key, "status": "skipped"}

    response = call_ollama(
        cfg.ollama_host,
        cfg.ollama_model,
        prompt,
        temperature=cfg.ollama_temperature,
        num_ctx=cfg.ollama_num_ctx,
    )
    checksum = sha256(response)
    response = response.replace(
        "Checksum_Placeholder: \"TO_BE_FILLED_BY_TOOL\"",
        f"Checksum: {checksum}",
    )
    relative_dir = path.parent.relative_to(cfg.vault_path)
    destination = out_dir / relative_dir
    destination.mkdir(parents=True, exist_ok=True)
    out_file = destination / f"{path.stem}.uqcp.md"
    write_text(out_file, response)
    cache[rel_key] = cache_key
    return {
        "path": rel_key,
        "status": "ok",
        "output": str(out_file),
        "checksum": checksum,
    }


def aggregate_folder(folder: Path) -> Optional[Path]:
    parts: List[str] = []
    for child in sorted(folder.glob("*.uqcp.md")):
        if child.name == AGGREGATE_FILE:
            continue
        parts.append(f"\n\n---\n# {child.stem}\n\n{read_text(child)}")
    if not parts:
        return None
    aggregate = "".join(parts)
    out_path = folder / AGGREGATE_FILE
    write_text(out_path, aggregate)
    return out_path


def run_pipeline(cfg: Config, *, full: bool, changed_only: bool, target_folder: Optional[str]) -> None:
    prompt_template = load_prompt_template()
    vault = cfg.vault_path
    if not vault.exists():
        raise FileNotFoundError(f"Vault path does not exist: {vault}")

    working_cfg = cfg
    if full:
        working_cfg = dataclasses.replace(cfg, changed_only=False)
    elif changed_only:
        working_cfg = dataclasses.replace(cfg, changed_only=True)

    if target_folder:
        root = vault / target_folder
    else:
        root = vault

    out_dir = vault / cfg.output_folder_name
    out_dir.mkdir(parents=True, exist_ok=True)

    cache_path = out_dir / CACHE_FILE
    cache = load_cache(cache_path)

    files = discover_files(root, include_exts=working_cfg.include_extensions, exclude_folders=working_cfg.exclude_folders + [cfg.output_folder_name])
    results: List[Dict[str, str]] = []
    for path in tqdm(files, desc="Compressing"):
        try:
            results.append(
                compress_markdown(
                    path,
                    cfg=working_cfg,
                    prompt_template=prompt_template,
                    cache=cache,
                    out_dir=out_dir,
                )
            )
        except Exception as exc:  # log and continue
            logger.exception("Failed to process %s", path)
            results.append({"path": str(path), "status": "error", "error": str(exc)})

    save_cache(cache_path, cache)

    if working_cfg.aggregate_by_folder:
        for dirpath, _, filenames in os.walk(out_dir):
            if any(name.endswith(".uqcp.md") for name in filenames):
                aggregate_folder(Path(dirpath))

    write_text(out_dir / INDEX_FILE, json.dumps(results, indent=2))
    logger.info("Processed %d files", len(results))


class CompressionHandler(http.server.BaseHTTPRequestHandler):
    cfg: Config = load_config()
    prompt_template: str = load_prompt_template()

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/compress":
            self.send_error(404, "Not found")
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length)) if length else {}
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON payload")
            return

        note_path = payload.get("path")
        content = payload.get("content")
        if not note_path or content is None:
            self.send_error(400, "Missing 'path' or 'content'")
            return

        note_path = str(note_path)
        target = self.cfg.vault_path / note_path
        target.parent.mkdir(parents=True, exist_ok=True)
        write_text(target, content)
        out_dir = self.cfg.vault_path / self.cfg.output_folder_name
        cache_path = out_dir / CACHE_FILE
        cache = load_cache(cache_path)
        # Always reprocess direct requests to ensure fresh output.
        local_cfg = dataclasses.replace(self.cfg, changed_only=False)
        result = compress_markdown(
            target,
            cfg=local_cfg,
            prompt_template=self.prompt_template,
            cache=cache,
            out_dir=out_dir,
        )
        # Refresh aggregate for this folder when enabled.
        if local_cfg.aggregate_by_folder:
            try:
                relative_parent = target.parent.relative_to(local_cfg.vault_path)
            except ValueError:
                relative_parent = Path(".")
            note_output_dir = out_dir / relative_parent
            if note_output_dir.exists():
                aggregate_folder(note_output_dir)
        save_cache(cache_path, cache)
        response = json.dumps(result).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        logger.info("Server: " + format, *args)


def serve(cfg: Config, *, host: str, port: int) -> None:
    handler = CompressionHandler
    handler.cfg = cfg
    handler.prompt_template = load_prompt_template()
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer((host, port), handler) as httpd:
        logger.info("Serving compression API on http://%s:%s", host, port)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("Shutting down")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Obsidian → UQCP compressor")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run compression pipeline")
    run_parser.add_argument("--full", action="store_true", help="Rebuild everything")
    run_parser.add_argument("--changed-only", action="store_true", help="Only process changed files")
    run_parser.add_argument("--folder", type=str, help="Process a specific folder relative to the vault")

    serve_parser = sub.add_parser("serve", help="Start HTTP server")
    serve_parser.add_argument("--host", type=str, help="Listen host")
    serve_parser.add_argument("--port", type=int, help="Listen port")

    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    cfg = load_config()

    if args.command == "run":
        run_pipeline(cfg, full=args.full, changed_only=args.changed_only, target_folder=args.folder)
    elif args.command == "serve":
        host = args.host or cfg.server_host
        port = args.port or cfg.server_port
        serve(cfg, host=host, port=port)
    else:
        raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
