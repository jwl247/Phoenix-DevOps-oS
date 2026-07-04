import shutil, subprocess
from .base import BackendBase

class PacmanBackend(BackendBase):
    name     = 'pacman'
    platform = 'linux'

    def available(self):
        return shutil.which('pacman') is not None

    def _run(self, args):
        proc = subprocess.run(args, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def install(self, package):
        code, out, err = self._run(['sudo', 'pacman', '-S', '--noconfirm', package])
        return self.result(code == 0, package, 'install', out, err)

    def remove(self, package):
        code, out, err = self._run(['sudo', 'pacman', '-R', '--noconfirm', package])
        return self.result(code == 0, package, 'remove', out, err)

    def upgrade(self, package=None):
        code, out, err = self._run(['sudo', 'pacman', '-Syu', '--noconfirm'])
        return self.result(code == 0, package or 'all', 'upgrade', out, err)

    def search(self, query):
        code, out, err = self._run(['pacman', '-Ss', query])
        results = []
        lines = out.splitlines()
        for i in range(0, len(lines) - 1, 2):
            parts = lines[i].split('/')
            if len(parts) > 1:
                name = parts[1].split()[0]
                desc = lines[i+1].strip()
                results.append({'name': name, 'description': desc})
        return results

    def info(self, package):
        code, out, err = self._run(['pacman', '-Si', package])
        info = {'name': package, 'raw': out}
        for line in out.splitlines():
            if line.startswith('Version'):
                info['version'] = line.split(':', 1)[1].strip()
            if line.startswith('Description'):
                info['description'] = line.split(':', 1)[1].strip()
        return info
