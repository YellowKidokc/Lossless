# Obsidian → UQCP Compressor Toolkit

This toolkit provides a repeatable pipeline for converting Markdown notes in an
Obsidian vault into **UQCP (Ultra-Quick Compression Protocol)** artifacts using
a local Ollama model. Outputs are written to a parallel `_compressed` folder
inside your vault, and a manifest is generated for downstream tooling.

## Features
- Walk an Obsidian vault, filter Markdown notes, and compress each note with a
  structured prompt.
- Optional cache so previously processed notes are skipped unless content
  changes.
- Folder-level aggregation that merges note artifacts into `_folder_aggregate`
  files for high-level review.
- Optional HTTP server so other tools (for example, the included Obsidian
  plugin) can request on-demand compression of the active note.

## Requirements
- Python 3.9+
- [Ollama](https://ollama.com/) running locally
- Python dependencies listed in `requirements.txt`

## Quick start
1. Install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Update `config.yaml` so that `vault_path` points to your Obsidian vault.
3. Run the compressor:
   ```bash
   python compressor.py run --full
   ```

### Incremental updates
```bash
python compressor.py run --changed-only
```

### Serve HTTP endpoint
Start a local server that other apps can call:
```bash
python compressor.py serve --host 127.0.0.1 --port 42121
```

### Configuration
See `config.yaml` for model, prompt, and filtering options. Prompt text is
stored in `prompts/uqcp_prompt.txt` so it can be customised without editing the
code.

## Outputs
- Per-note artifacts saved as `<note>.uqcp.md` in `_compressed` mirror folders.
- `_index.json` manifest summarising operations.
- `_folder_aggregate.uqcp.md` files when aggregation is enabled.

## Integrations
The `/obsidian-plugin` directory contains a companion Obsidian plugin that can
send the currently active note to the HTTP server for compression without
leaving Obsidian.
