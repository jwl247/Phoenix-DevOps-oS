import shutil, subprocess, sys
from .base import BackendBase

class PipBackend(BackendBase):
    name     = 'pip'
    platform = 'any'

    def available(self):
        return shutil.which('pip3') is not None or shutil.which('pip') is not None

    def _run(self, args):
        proc = subprocess.run(args, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def install(self, package):
        code, out, err = self._run([sys.executable, '-m', 'pip', 'install', package])
        return self.result(code == 0, package, 'install', out, err)

    def remove(self, package):
        code, out, err = self._run([sys.executable, '-m', 'pip', 'uninstall', '-y', package])
        return self.result(code == 0, package, 'remove', out, err)

    def upgrade(self, package=None):
        if package:
            code, out, err = self._run([sys.executable, '-m', 'pip', 'install', '--upgrade', package])
        else:
            code, out, err = 0, 'Use: us upgrade <package> for pip', ''
        return self.result(code == 0, package or 'all', 'upgrade', out, err)

    def search(self, query):
        import urllib.request, json
        try:
            url = f'https://pypi.org/pypi/{query}/json'
            with urllib.request.urlopen(url, timeout=5) as r:
                data = json.loads(r.read())
                info = data['info']
                return [{'name': info['name'], 'description': info['summary']}]
        except:
            return []

    def info(self, package):
        code, out, err = self._run([sys.executable, '-m', 'pip', 'show', package])
        info = {'name': package, 'raw': out}
        for line in out.splitlines():
            if line.startswith('Version:'):
                info['version'] = line.split(':', 1)[1].strip()
            if line.startswith('Summary:'):
                info['description'] = line.split(':', 1)[1].strip()
        return info
