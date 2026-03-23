import shutil, subprocess
from .base import BackendBase

class ScoopBackend(BackendBase):
    name     = 'scoop'
    platform = 'windows'

    def available(self):
        return shutil.which('scoop') is not None

    def _run(self, args):
        proc = subprocess.run(args, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def install(self, package):
        code, out, err = self._run(['scoop', 'install', package])
        return self.result(code == 0, package, 'install', out, err)

    def remove(self, package):
        code, out, err = self._run(['scoop', 'uninstall', package])
        return self.result(code == 0, package, 'remove', out, err)

    def upgrade(self, package=None):
        args = ['scoop', 'update', package or '*']
        code, out, err = self._run(args)
        return self.result(code == 0, package or 'all', 'upgrade', out, err)

    def search(self, query):
        code, out, err = self._run(['scoop', 'search', query])
        return [{'name': l.strip(), 'description': ''} for l in out.splitlines() if l.strip()]

    def info(self, package):
        code, out, err = self._run(['scoop', 'info', package])
        info = {'name': package, 'raw': out}
        for line in out.splitlines():
            if line.startswith('Version'):
                info['version'] = line.split(':', 1)[1].strip()
        return info
