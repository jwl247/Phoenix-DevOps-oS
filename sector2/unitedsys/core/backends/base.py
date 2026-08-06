from abc import ABC, abstractmethod

class BackendBase(ABC):

    name     : str = 'base'
    platform : str = 'linux'

    @abstractmethod
    def available(self) -> bool:
        """Check if this backend is present on the system"""
        pass

    @abstractmethod
    def install(self, package: str) -> dict:
        """Install a package. Returns result dict."""
        pass

    @abstractmethod
    def remove(self, package: str) -> dict:
        """Remove a package. Returns result dict."""
        pass

    @abstractmethod
    def upgrade(self, package: str = None) -> dict:
        """Upgrade one or all packages."""
        pass

    @abstractmethod
    def search(self, query: str) -> list:
        """Search for packages. Returns list of dicts."""
        pass

    @abstractmethod
    def info(self, package: str) -> dict:
        """Get package details."""
        pass

    def result(self, success: bool, package: str, action: str,
               output: str = '', error: str = '', version: str = '') -> dict:
        """Standard result envelope all backends return"""
        return {
            'success' : success,
            'package' : package,
            'action'  : action,
            'backend' : self.name,
            'version' : version,
            'output'  : output,
            'error'   : error,
        }
