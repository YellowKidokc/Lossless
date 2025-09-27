import { App, Notice, Plugin, PluginSettingTab, Setting, requestUrl, TFile } from "obsidian";

interface UQCPSettings {
  endpoint: string;
  showNotice: boolean;
}

const DEFAULT_SETTINGS: UQCPSettings = {
  endpoint: "http://127.0.0.1:42121/compress",
  showNotice: true,
};

interface CompressionResponse {
  status?: string;
  path?: string;
  output?: string;
  checksum?: string;
  error?: string;
}

export default class UQCPCompressorPlugin extends Plugin {
  settings: UQCPSettings = DEFAULT_SETTINGS;

  async onload() {
    await this.loadSettings();

    this.addCommand({
      id: "uqcp-compress-current-note",
      name: "UQCP: Compress current note",
      callback: () => this.compressActiveNote(),
    });

    this.addSettingTab(new UQCPSettingTab(this.app, this));
  }

  async compressActiveNote() {
    const file = this.getActiveMarkdownFile();
    if (!file) {
      new Notice("No Markdown note is active.");
      return;
    }

    const content = await this.app.vault.read(file);
    try {
      const response = await requestUrl({
        url: this.settings.endpoint,
        method: "POST",
        body: JSON.stringify({ path: file.path, content }),
        headers: { "Content-Type": "application/json" },
      });

      const data = response.json as CompressionResponse;
      if (data.error) {
        new Notice(`UQCP compression failed: ${data.error}`);
        return;
      }

      if (this.settings.showNotice) {
        const checksum = data.checksum ?? "unknown";
        const output = data.output ?? "unknown";
        new Notice(`UQCP OK\nChecksum: ${checksum}\nOutput: ${output}`);
      }
    } catch (error) {
      console.error(error);
      new Notice("UQCP request failed. Ensure the server is running.");
    }
  }

  getActiveMarkdownFile(): TFile | null {
    const file = this.app.workspace.getActiveFile();
    if (!file || file.extension !== "md") {
      return null;
    }
    return file;
  }

  async loadSettings() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings() {
    await this.saveData(this.settings);
  }
}

class UQCPSettingTab extends PluginSettingTab {
  constructor(app: App, private plugin: UQCPCompressorPlugin) {
    super(app, plugin);
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    containerEl.createEl("h2", { text: "UQCP Compressor" });

    new Setting(containerEl)
      .setName("Endpoint URL")
      .setDesc("Address of the local compression server")
      .addText((text) =>
        text
          .setPlaceholder(DEFAULT_SETTINGS.endpoint)
          .setValue(this.plugin.settings.endpoint)
          .onChange(async (value) => {
            this.plugin.settings.endpoint = value.trim() || DEFAULT_SETTINGS.endpoint;
            await this.plugin.saveSettings();
          }),
      );

    new Setting(containerEl)
      .setName("Show response notice")
      .setDesc("Display checksum/output after compression")
      .addToggle((toggle) =>
        toggle.setValue(this.plugin.settings.showNotice).onChange(async (value) => {
          this.plugin.settings.showNotice = value;
          await this.plugin.saveSettings();
        }),
      );
  }
}
