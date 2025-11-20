const path = require('path');
const fs = require('fs-extra');

class ConfigStore {
  constructor(app) {
    this.configPath = path.join(app.getPath('userData'), 'config.json');
    this.data = {};
  }

  async load() {
    try {
      const exists = await fs.pathExists(this.configPath);
      if (!exists) {
        this.data = {};
        return this.data;
      }

      this.data = await fs.readJson(this.configPath);
      return this.data;
    } catch (error) {
      this.data = {};
      return this.data;
    }
  }

  async save(patch) {
    this.data = {
      ...this.data,
      ...patch
    };

    await fs.outputJson(this.configPath, this.data, { spaces: 2 });
    return this.data;
  }

  get(key, fallback = null) {
    return this.data[key] ?? fallback;
  }
}

module.exports = ConfigStore;

