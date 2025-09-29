# Lossless

This repository now includes tools for compressing Obsidian vault content into
UQCP artifacts and an optional Obsidian plugin for triggering compression from
within the editor.

## Contents
- `obsidian_uqcp/` – Python toolkit that scans a vault, runs the Ollama-powered
  compression prompt, writes results to `_compressed`, and can expose a local
  HTTP API for other clients.
- `obsidian-plugin/` – Obsidian community plugin source code that calls the
  local compressor server for the active note.
