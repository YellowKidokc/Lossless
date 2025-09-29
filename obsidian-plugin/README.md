# UQCP Compressor Obsidian Plugin

This plugin lets you send the active note in Obsidian to the local UQCP
compression server (provided by `obsidian_uqcp/compressor.py`) with a single
command. The server returns the location of the generated `.uqcp.md` artifact,
and the plugin shows a notice when processing completes.

## Installation
1. Build the plugin bundle:
   ```bash
   npm install
   npm run build
   ```
   The compiled files (`main.js`, `manifest.json`, `styles.css`) will be placed
   in the `dist/` folder.
2. Copy the contents of `dist/` into `<vault>/.obsidian/plugins/uqcp-compressor`.
3. Enable **UQCP Compressor** in Obsidian’s community plugins settings.

## Usage
- Run the "UQCP: Compress current note" command (Command Palette or assign a
  hotkey).
- Ensure the Python compression server is running:
  ```bash
  python obsidian_uqcp/compressor.py serve
  ```
- Successful compression shows the checksum and destination path in a notice.

## Settings
- **Endpoint URL** – defaults to `http://127.0.0.1:42121/compress`.
- **Show response notice** – toggle whether to display the returned checksum and
  output path.

## Development
- `npm run dev` will watch for changes and rebuild automatically.
- Update TypeScript sources in `src/`.
