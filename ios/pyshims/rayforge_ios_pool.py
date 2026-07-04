"""Thread-based drop-in replacement for Rayforge's WorkerPoolManager.

iOS forbids fork() and provides no way to spawn a second Python
interpreter process, so multiprocessing is unavailable. This class
speaks the exact same protocol as rayforge.shared.tasker.pool.
WorkerPoolManager — same constructor kwargs, same public methods
(submit / cancel / shutdown / get_shared_state), same six blinker
signals with identical signatures — but executes tasks on worker
THREADS in-process.

It deliberately reuses Rayforge's own ExecutionContextProxy and
_TaggedQueue, so task functions see an identical context object
(progress, messages, events, cooperative is_cancelled()) and the
message stream ((key, task_id, msg_type, value)) is bit-identical to
the multiprocessing implementation. Only the transport changed:
queue.Queue and plain dicts instead of multiprocessing primitives.

Caveat vs processes: CPU-bound tasks share the GIL and a crashed task
cannot take down "a worker process" (there is none) — worker_died is
therefore never emitted. Cancellation remains cooperative, exactly as
upstream (workers check is_cancelled()).
"""

import logging
import queue
import threading
import traceback
from typing import Any, Callable, Optional, Tuple

from blinker import Signal

from rayforge.shared.tasker.pool import _TaggedQueue
from rayforge.shared.tasker.proxy import ExecutionContextProxy

logger = logging.getLogger(__name__)

_POISON = object()
_SENTINEL = object()


class ThreadPoolManager:
    def __init__(
        self,
        num_workers: int = 2,
        initializer: Optional[Callable[..., None]] = None,
        initargs: Tuple[Any, ...] = (),
        shared_state: Any = None,
        log_level: Optional[int] = None,
    ) -> None:
        self._log_level = (
            log_level
            if log_level is not None
            else logging.getLogger().getEffectiveLevel()
        )
        self._shared_state = shared_state if shared_state is not None else {}
        self._adoption_signals: dict = {}
        self._initializer = initializer
        self._initargs = initargs

        self.task_event_received = Signal()
        self.task_completed = Signal()
        self.task_failed = Signal()
        self.task_progress_updated = Signal()
        self.task_message_updated = Signal()
        self.worker_died = Signal()  # never fired in-process; kept for API

        self._lock = threading.RLock()
        self._cancelled_task_ids: set = set()
        self._task_queue: "queue.Queue" = queue.Queue()
        self._result_queue: "queue.Queue" = queue.Queue()

        self._workers = []
        for i in range(num_workers):
            t = threading.Thread(
                target=self._worker_loop,
                name=f"rayforge-ios-worker-{i}",
                daemon=True,
            )
            t.start()
            self._workers.append(t)

        self._listener = threading.Thread(
            target=self._listener_loop,
            name="rayforge-ios-pool-listener",
            daemon=True,
        )
        self._listener.start()

    # ------------------------------------------------------------ public
    def get_shared_state(self) -> Any:
        return self._shared_state

    def submit(
        self,
        key: Any,
        task_id: int,
        target: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        logger.debug(
            "ThreadPool: submitting task '%s' (id: %s)", key, task_id
        )
        self._task_queue.put((key, task_id, target, args, kwargs))

    def cancel(self, key: Any, task_id: int) -> None:
        with self._lock:
            self._cancelled_task_ids.add(task_id)
        # Cooperative flag, read by ExecutionContextProxy.is_cancelled()
        self._adoption_signals[f"cancel:{task_id}"] = True

    def shutdown(self, timeout: float = 2.0) -> None:
        for _ in self._workers:
            self._task_queue.put(_POISON)
        for t in self._workers:
            t.join(timeout=timeout)
        self._result_queue.put(_SENTINEL)
        self._listener.join(timeout=timeout)

    # ----------------------------------------------------------- workers
    def _worker_loop(self) -> None:
        if self._initializer is not None:
            try:
                self._initializer(self._shared_state, *self._initargs)
            except Exception:
                logger.critical(
                    "ThreadPool worker failed during initialization:\n%s",
                    traceback.format_exc(),
                )
                return
        while True:
            job = self._task_queue.get()
            if job is _POISON:
                return
            key, task_id, target, args, kwargs = job

            if f"cancel:{task_id}" in self._adoption_signals:
                self._result_queue.put((key, task_id, "done", None))
                self._adoption_signals.pop(f"cancel:{task_id}", None)
                continue

            tagged = _TaggedQueue(self._result_queue, key, task_id)
            proxy = ExecutionContextProxy(
                tagged,  # type: ignore[arg-type]
                parent_log_level=self._log_level,
                adoption_signals=self._adoption_signals,
                task_id=task_id,
            )
            try:
                result = target(proxy, *args, **kwargs)
                proxy.flush()
                self._result_queue.put((key, task_id, "done", result))
            except Exception:
                error_info = traceback.format_exc()
                logger.error(
                    "ThreadPool task '%s' failed:\n%s", key, error_info
                )
                proxy.flush()
                self._result_queue.put((key, task_id, "error", error_info))

    # ---------------------------------------------------------- listener
    def _listener_loop(self) -> None:
        while True:
            message = self._result_queue.get()
            if message is _SENTINEL:
                return
            key, task_id, msg_type, value = message

            if msg_type == "event":
                event_name, data = value
                self.task_event_received.send(
                    self,
                    key=key,
                    task_id=task_id,
                    event_name=event_name,
                    data=data,
                    adoption_signals=self._adoption_signals,
                )
                continue

            with self._lock:
                if task_id in self._cancelled_task_ids:
                    if msg_type in ("done", "error"):
                        self._cancelled_task_ids.discard(task_id)
                        self._adoption_signals.pop(f"cancel:{task_id}", None)
                    else:
                        continue

            if msg_type == "done":
                self._adoption_signals.pop(f"cancel:{task_id}", None)
                self.task_completed.send(
                    self, key=key, task_id=task_id, result=value
                )
            elif msg_type == "error":
                self._adoption_signals.pop(f"cancel:{task_id}", None)
                self.task_failed.send(
                    self, key=key, task_id=task_id, error=value
                )
            elif msg_type == "progress":
                self.task_progress_updated.send(
                    self, key=key, task_id=task_id, progress=value
                )
            elif msg_type == "message":
                self.task_message_updated.send(
                    self, key=key, task_id=task_id, message=value
                )
