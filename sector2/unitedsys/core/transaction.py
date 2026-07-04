import time
from core.catalog import log_transaction, record_install, record_remove
from core.detect  import get_platform

class TransactionError(Exception):
    pass

class Operation:
    def __init__(self, action, package, backend):
        self.action   = action
        self.package  = package
        self.backend  = backend
        self.result   = None
        self.duration = 0

    def run(self):
        start = time.time()
        if self.action == 'install':
            self.result = self.backend.install(self.package)
        elif self.action == 'remove':
            self.result = self.backend.remove(self.package)
        elif self.action == 'upgrade':
            self.result = self.backend.upgrade(self.package)
        self.duration = int((time.time() - start) * 1000)
        if not self.result['success']:
            raise TransactionError(self.result['error'])

    def undo(self):
        try:
            if self.action == 'install':
                self.backend.remove(self.package)
            elif self.action == 'remove':
                self.backend.install(self.package)
        except Exception:
            pass

class Transaction:
    def __init__(self, backend):
        self.backend        = backend
        self.ops            = []
        self.rollback_stack = []
        self.platform       = get_platform()

    def plan(self, action, packages):
        if isinstance(packages, str):
            packages = [packages]
        for pkg in packages:
            self.ops.append(Operation(action, pkg, self.backend))
        return self

    def execute(self):
        if not self.ops:
            raise TransactionError('No operations planned')

        results = []
        for op in self.ops:
            try:
                print(f'  --> {op.action} {op.package} via {self.backend.name}...')
                op.run()
                self.rollback_stack.append(op)

                if op.action in ('install', 'upgrade'):
                    record_install(
                        name     = op.package,
                        version  = op.result.get('version', ''),
                        backend  = self.backend.name,
                        platform = self.platform,
                    )
                elif op.action == 'remove':
                    record_remove(op.package)

                log_transaction(
                    action      = op.action,
                    package     = op.package,
                    status      = 'success',
                    backend     = self.backend.name,
                    duration_ms = op.duration,
                )
                results.append(op.result)
                print(f'  [OK] {op.package}')

            except TransactionError as e:
                print(f'  [FAIL] {op.package}: {e}')
                print(f'  Rolling back {len(self.rollback_stack)} operation(s)...')
                self._rollback()
                log_transaction(
                    action  = op.action,
                    package = op.package,
                    status  = 'failed',
                    backend = self.backend.name,
                    error   = str(e),
                )
                raise TransactionError(f'Transaction failed on {op.package}: {e}')

        return results

    def _rollback(self):
        for op in reversed(self.rollback_stack):
            print(f'  <-- rolling back {op.action} {op.package}')
            op.undo()
            log_transaction(
                action  = op.action,
                package = op.package,
                status  = 'rolled_back',
                backend = self.backend.name,
            )
        self.rollback_stack.clear()

    def dry_run(self):
        print(f'\nDry run — {len(self.ops)} operation(s) planned:')
        for op in self.ops:
            print(f'  {op.action:10} {op.package:30} via {self.backend.name}')
        print()
