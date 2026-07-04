import shutil, subprocess
from .base import BackendBase

class ZypperBackend(BackendBase):
    name     = 'zypper'
    platform = 'linux'

    def available(self):
        return shutil.which('zypper') is not None

    def _run(self, args):
        proc = subprocess.run(args, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def install(self, package):
        code, out, err = self._run(['sudo', 'zypper', 'install', '-y', package])
        return self.result(code == 0, package, 'install', out, err)

    def remove(self, package):
        code, out, err = self._run(['sudo', 'zypper', 'remove', '-y', package])
        return self.result(code == 0, package, 'remove', out, err)

    def upgrade(self, package=None):
        args = ['sudo', 'zypper', 'update', '-y']
        if package: args.append(package)
        code, out, err = self._run(args)
        return self.result(code == 0, package or 'all', 'upgrade', out, err)

    def search(self, query):
        code, out, err = self._run(['zypper', 'search', query])
        results = []
        for line in out.splitlines()[2:]:
            parts = line.split('|')
            if len(parts) >= 4:
                results.append({'name': parts[1].strip(), 'description': parts[3].strip()})
        return results

    def info(self, package):
        code, out, err = self._run(['zypper', 'info', package])
        info = {'name': package, 'raw': out}
        for line in out.splitlines():
            if line.startswith('Version'):
                info['version'] = line.split(':', 1)[1].strip()
            if line.startswith('Summary'):
                info['description'] = line.split(':', 1)[1].strip()
        return info
