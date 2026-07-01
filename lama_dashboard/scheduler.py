import threading
import logging

logger = logging.getLogger(__name__)

_scheduler = None
_lock = threading.Lock()


def _run_signal_detection():
    """Daily 7am signal detection job."""
    try:
        logger.info("Daily signal detection starting")
        import signal_detector
        result = signal_detector.run_all_detectors()
        logger.info(f"Signal detection complete: {result}")
    except Exception as e:
        logger.error(f"Signal detection failed: {e}")


def _run_scrape_job():
    """Job function called by APScheduler — wraps scraper with lock to prevent overlap."""
    with _lock:
        try:
            import staging as st
            data = st.load_staging()
            if data.get("scrape_status") == "running":
                logger.info("Scrape already running — skipping scheduled run")
                return
            logger.info("Scheduled Monday scrape starting")
            from scraper import run_scrape
            run_scrape()
            logger.info("Scheduled scrape complete")
        except Exception as e:
            logger.error(f"Scheduled scrape failed: {e}")


def start_scheduler():
    global _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        _scheduler = BackgroundScheduler(timezone="Asia/Jerusalem")
        _scheduler.add_job(
            _run_scrape_job,
            trigger=CronTrigger(day_of_week="mon", hour=9, minute=0,
                                timezone="Asia/Jerusalem"),
            id="weekly_scrape",
            replace_existing=True,
            max_instances=1,
        )
        _scheduler.add_job(
            _run_signal_detection,
            trigger=CronTrigger(hour=7, minute=0, timezone="Asia/Jerusalem"),
            id="daily_signal_detection",
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=3600,
        )
        _scheduler.start()
        logger.info("APScheduler started — weekly scrape scheduled for Monday 9am Israel time")

        # Update next_scheduled in staging.json
        try:
            from scraper import _next_monday_israel
            import staging as st
            data = st.load_staging()
            if not data.get("next_scheduled"):
                data["next_scheduled"] = _next_monday_israel()
                st.save_staging(data)
        except Exception:
            pass

    except ImportError:
        logger.warning("APScheduler not installed — weekly auto-scrape disabled. Run: pip install apscheduler")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown()
