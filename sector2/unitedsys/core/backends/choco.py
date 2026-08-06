import shutil, subprocess
from .base import BackendBase

class ChocoBackend(BackendBase):
    name     = 'choco'
    platform = 'windows'

    def available(self):
        return shutil.which('choco') is not None

    def _run(self, args):
        proc = subprocess.run(args, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def install(self, package):
        code, out, err = self._run(['choco', 'install', '-y', package])
        return self.result(code == 0, package, 'install', out, err)

    def remove(self, package):
        code, out, err = self._run(['choco', 'uninstall', '-y', package])
        return self.result(code == 0, package, 'remove', out, err)

    def upgrade(self, package=None):
        args = ['choco', 'upgrade', '-y', package or 'all']
        code, out, err = self._run(args)
        return self.result(code == 0, package or 'all', 'upgrade', out, err)

    def search(self, query):
        code, out, err = self._run(['choco', 'search', query])
        results = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                results.append({'name': parts[0], 'description': ' '.join(parts[2:])})
        return results

    def info(self, package):
        code, out, err = self._run(['choco', 'info', package])
        info = {'name': package, 'raw': out}
        for line in out.splitlines():
            if 'Version:' in line:
                info['version'] = line.split(':', 1)[1].strip()
        return info
