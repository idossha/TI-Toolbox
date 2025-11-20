let execaInstance = null;

async function getExeca() {
  if (!execaInstance) {
    const mod = await import('execa');
    execaInstance = mod.execa ?? mod.default ?? mod;
  }
  return execaInstance;
}

module.exports = {
  getExeca
};

