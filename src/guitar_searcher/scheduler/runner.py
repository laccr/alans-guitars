"""APScheduler daemon that runs each active watch on its cadence.

Cadences map to APScheduler cron triggers:
- hourly  → every hour at :05
- daily   → every day at 07:15 local
- weekly  → Mondays at 07:15 local
"""
from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from guitar_searcher.db.session import get_session
from guitar_searcher.models.listing import SearchRow
from guitar_searcher.utils.logging import configure_logging, get_logger
from guitar_searcher.watch_runner import list_watches, run_watch

log = get_logger(__name__)


_TRIGGERS: dict[str, CronTrigger] = {
    "hourly": CronTrigger(minute=5),
    "daily": CronTrigger(hour=7, minute=15),
    "weekly": CronTrigger(day_of_week="mon", hour=7, minute=15),
}


def _run_one(watch_id: int) -> None:
    with get_session() as session:
        watch = session.get(SearchRow, watch_id)
        if watch is None or not watch.is_watch or not watch.watch_active:
            log.info("scheduler.skip", watch_id=watch_id, reason="inactive_or_gone")
            return
        try:
            all_matches, new_matches = run_watch(session, watch)
            log.info(
                "scheduler.ran",
                watch_id=watch_id,
                total=len(all_matches),
                new=len(new_matches),
            )
        except Exception as exc:
            log.error("scheduler.failed", watch_id=watch_id, error=str(exc))


def build_scheduler() -> BlockingScheduler:
    sched = BlockingScheduler(timezone="UTC")
    with get_session() as session:
        watches = list_watches(session, only_active=True)
    for w in watches:
        trigger = _TRIGGERS.get(w.watch_cadence or "daily")
        if trigger is None:
            log.warning("scheduler.unknown_cadence", watch_id=w.id, cadence=w.watch_cadence)
            continue
        sched.add_job(
            _run_one,
            trigger=trigger,
            args=[w.id],
            id=f"watch-{w.id}",
            replace_existing=True,
            misfire_grace_time=600,
        )
        log.info("scheduler.scheduled", watch_id=w.id, cadence=w.watch_cadence)
    return sched


def run_forever() -> None:
    configure_logging()
    sched = build_scheduler()
    if not sched.get_jobs():
        log.warning("scheduler.no_jobs", message="No active watches; nothing to schedule.")
        return
    log.info("scheduler.start", jobs=len(sched.get_jobs()))
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("scheduler.stop")
