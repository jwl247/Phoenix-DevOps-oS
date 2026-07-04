import shutil
import subprocess
from .base import BackendBase

class AptBackend(BackendBase):

    name     = 'apt'
    platform = 'linux'

    def available(self) -> bool:
        return shutil.which('apt') is not None

    def _run(self, args: list) -> tuple:
        env = {'DEBIAN_FRONTEND': 'noninteractive'}
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            env={**__import__('os').environ, **env}
        )
        return proc.returncode, proc.stdout, proc.stderr

    def install(self, package: str) -> dict:
        code, out, err = self._run(['sudo', 'apt', 'install', '-y', package])
        return self.result(code == 0, package, 'install', out, err)

    def remove(self, package: str) -> dict:
        code, out, err = self._run(['sudo', 'apt', 'remove', '-y', package])
        return self.result(code == 0, package, 'remove', out, err)

    def upgrade(self, package: str = None) -> dict:
        if package:
            code, out, err = self._run(['sudo', 'apt', 'install', '--only-upgrade', '-y', package])
        else:
            self._run(['sudo', 'apt', 'update'])
            code, out, err = self._run(['sudo', 'apt', 'upgrade', '-y'])
        return self.result(code == 0, package or 'all', 'upgrade', out, err)

    def search(self, query: str) -> list:
        code, out, err = self._run(['apt-cache', 'search', query])
        results = []
        for line in out.splitlines():
            if ' - ' in line:
                name, desc = line.split(' - ', 1)
                results.append({'name': name.strip(), 'description': desc.strip()})
        return results

    def info(self, package: str) -> dict:
        code, out, err = self._run(['apt-cache', 'show', package])
        info = {'name': package, 'raw': out}
        for line in out.splitlines():
            if line.startswith('Version:'):
                info['version'] = line.split(':', 1)[1].strip()
            if line.startswith('Description:'):
                info['description'] = line.split(':', 1)[1].strip()
        return info
