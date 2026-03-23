from .apt     import AptBackend
from .dnf     import DnfBackend
from .pacman  import PacmanBackend
from .zypper  import ZypperBackend
from .brew    import BrewBackend
from .winget  import WingetBackend
from .choco   import ChocoBackend
from .scoop   import ScoopBackend
from .pip       import PipBackend
from .clonepool import ClonepoolBackend

ALL = [
    AptBackend,
    DnfBackend,
    PacmanBackend,
    ZypperBackend,
    BrewBackend,
    WingetBackend,
    ChocoBackend,
    ScoopBackend,
    PipBackend,
    ClonepoolBackend,
]
