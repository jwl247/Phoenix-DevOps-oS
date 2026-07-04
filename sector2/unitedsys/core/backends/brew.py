import shutil, subprocess
from .base import BackendBase

class BrewBackend(BackendBase):
    name     = 'brew'
    platform = 'darwin'

    def available(self):
        return shutil.which('brew') is not None

    def _run(self, args):
        proc = subprocess.run(args, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def install(self, package):
        code, out, err = self._run(['brew', 'install', package])
        return self.result(code == 0, package, 'install', out, err)

    def remove(self, package):
        code, out, err = self._run(['brew', 'uninstall', package])
        return self.result(code == 0, package, 'remove', out, err)

    def upgrade(self, package=None):
        args = ['brew', 'upgrade']
        if package: args.append(package)
        code, out, err = self._run(args)
        return self.result(code == 0, package or 'all', 'upgrade', out, err)

    def search(self, query):
        code, out, err = self._run(['brew', 'search', query])
        return [{'name': l.strip(), 'description': ''} for l in out.splitlines() if l.strip()]

    def info(self, package):
        code, out, err = self._run(['brew', 'info', package])
        info = {'name': package, 'raw': out}
        lines = out.splitlines()
        if lines:
            info['description'] = lines[0]
        return info
