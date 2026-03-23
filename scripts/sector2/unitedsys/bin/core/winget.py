import shutil, subprocess
from .base import BackendBase

class WingetBackend(BackendBase):
    name     = 'winget'
    platform = 'windows'

    def available(self):
        return shutil.which('winget') is not None

    def _run(self, args):
        proc = subprocess.run(args, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def install(self, package):
        code, out, err = self._run(['winget', 'install', '--silent', '--accept-package-agreements',
                                    '--accept-source-agreements', package])
        return self.result(code == 0, package, 'install', out, err)

    def remove(self, package):
        code, out, err = self._run(['winget', 'uninstall', '--silent', package])
        return self.result(code == 0, package, 'remove', out, err)

    def upgrade(self, package=None):
        args = ['winget', 'upgrade', '--silent', '--accept-package-agreements']
        if package: args.append(package)
        else: args.append('--all')
        code, out, err = self._run(args)
        return self.result(code == 0, package or 'all', 'upgrade', out, err)

    def search(self, query):
        code, out, err = self._run(['winget', 'search', query])
        results = []
        for line in out.splitlines()[2:]:
            parts = line.split()
            if parts:
                results.append({'name': parts[0], 'description': ' '.join(parts[1:])})
        return results

    def info(self, package):
        code, out, err = self._run(['winget', 'show', package])
        info = {'name': package, 'raw': out}
        for line in out.splitlines():
            if line.strip().startswith('Version:'):
                info['version'] = line.split(':', 1)[1].strip()
            if line.strip().startswith('Description:'):
                info['description'] = line.split(':', 1)[1].strip()
        return info
