from core.catalog  import get_conn
from core.manifest import load as load_manifest

class CycleError(Exception):
    pass

class Resolver:
    def __init__(self):
        self.visited = set()
        self.stack   = set()

    def resolve(self, package, backend_name=None):
        self.visited.clear()
        self.stack.clear()
        order = []
        self._visit(package, backend_name, order)
        return order

    def _visit(self, package, backend_name, order):
        if package in self.stack:
            raise CycleError(f'Circular dependency detected: {package}')
        if package in self.visited:
            return

        self.stack.add(package)

        deps = self._get_deps(package, backend_name)
        for dep in deps:
            self._visit(dep, backend_name, order)

        self.stack.discard(package)
        self.visited.add(package)
        order.append(package)

    def _get_deps(self, package, backend_name):
        deps = []

        # check manifest first
        try:
            m = load_manifest(package)
            deps = m.get('dependencies', [])
        except Exception:
            pass

        # also check catalog db
        conn = get_conn()
        rows = conn.execute(
            'SELECT depends_on FROM deps WHERE package=?', (package,)
        ).fetchall()
        conn.close()
        for row in rows:
            if row['depends_on'] not in deps:
                deps.append(row['depends_on'])

        return deps

    def add_dep(self, package, depends_on):
        conn = get_conn()
        conn.execute(
            'INSERT OR IGNORE INTO deps (package, depends_on) VALUES (?,?)',
            (package, depends_on)
        )
        conn.commit()
        conn.close()

    def remove_dep(self, package, depends_on):
        conn = get_conn()
        conn.execute(
            'DELETE FROM deps WHERE package=? AND depends_on=?',
            (package, depends_on)
        )
        conn.commit()
        conn.close()

    def get_deps(self, package):
        conn = get_conn()
        rows = conn.execute(
            'SELECT depends_on FROM deps WHERE package=?', (package,)
        ).fetchall()
        conn.close()
        return [r['depends_on'] for r in rows]
