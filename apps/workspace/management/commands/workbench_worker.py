"""SQLite-safe workbench worker.

One short transaction claims a queued run, then all parsing/retrieval happens
outside the write transaction. A lease prevents a second worker from taking the
same run; stale runs are requeued or failed explicitly.
"""

import os
import socket
import time
import uuid

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.workspace.services.executor import execute_run
from apps.workspace.services.tasks import (
    claim_next, recover_stale_runs, touch_heartbeat, worker_status,
)


class Command(BaseCommand):
    help = 'Run the AlgoMentor workbench task worker.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Process at most one queued task.')
        parser.add_argument('--poll', type=float, default=2.0, help='Idle poll interval in seconds.')
        parser.add_argument('--worker-id', default='', help='Stable worker id.')
        parser.add_argument('--max-tasks', type=int, default=0, help='Stop after N tasks (0 = unlimited).')

    def handle(self, *args, **options):
        worker_id = options['worker_id'] or f'{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}'
        once = options['once']
        poll = max(0.2, float(options['poll']))
        max_tasks = max(0, int(options['max_tasks']))
        recovery = recover_stale_runs()
        if recovery['requeued'] or recovery['failed']:
            self.stdout.write(self.style.WARNING(
                f"stale runs: requeued={recovery['requeued']} failed={recovery['failed']}"
            ))
        self.stdout.write(self.style.SUCCESS(f'workbench worker ready: {worker_id}'))
        processed = 0
        try:
            while True:
                close_old_connections()
                run = claim_next(worker_id)
                if run is None:
                    touch_heartbeat(worker_id)
                    if once:
                        self.stdout.write('no queued task')
                        return
                    time.sleep(poll)
                    continue
                self.stdout.write(f'run={run.run_id} type={run.task_type} attempt={run.attempts}')
                touch_heartbeat(worker_id, run.run_id)
                execute_run(run.run_id, worker_id=worker_id)
                touch_heartbeat(worker_id)
                processed += 1
                if once or (max_tasks and processed >= max_tasks):
                    self.stdout.write(self.style.SUCCESS(f'processed={processed}'))
                    return
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('worker stopped by user'))
        finally:
            close_old_connections()
            status = worker_status()
            self.stdout.write(f"worker state: {status['state']}")
