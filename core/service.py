"""Unplugin 서비스 데몬 — 수신→처리→큐→발신→대시보드 사이클을 반복한다.

실행: python3 -m core serve [--interval 60] [--once]

사이클 구성:
  ① mail_io.fetch_new()   — IMAP 실수신 (v0.5, 모듈/설정 없으면 skip)
  ② mailbox.process_inbox() — data/inbox/ 파이프라인 처리
  ③ queue.run_tick()        — 슬롯 승격·실행·타임아웃 점검
  ④ mail_io.send_pending()  — SMTP 실발신 (없으면 skip — outbox 파일은
                              그대로 남아 시뮬레이션 모드로 동작)
  ⑤ dashboard.generate()    — 대표용 Unified View 갱신

`mail_io`(IMAP/SMTP)와 `executor`(실 브라우저)는 다른 부문이 병행 개발 중이므로
반드시 지연 임포트하고 ImportError/AttributeError 를 허용한다 — 없으면 해당
단계만 건너뛰고("준비 중" 로그) 나머지는 정상 동작한다.
사이클 내 단계 예외는 잡아서 로그 후 다음 단계로 진행한다 (데몬이 죽지 않게).
"""
from __future__ import annotations

import time
from datetime import datetime
from importlib import import_module

from . import common


# ── 로그 ─────────────────────────────────────────────────

def _log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _once_log(warned: set[str], msg: str) -> None:
    """같은 안내는 서비스 수명 동안 1회만 출력 (데몬 로그 스팸 방지)."""
    if msg not in warned:
        warned.add(msg)
        _log(msg)


# ── mail_io 느슨한 연동 ──────────────────────────────────

def _load_mail_io():
    """core.mail_io 지연 로드. (module | None, config | None) 반환."""
    try:
        mod = import_module(".mail_io", package=__package__)
    except ImportError:
        return None, None
    cfg = None
    loader = getattr(mod, "load_config", None)
    if callable(loader):
        try:
            cfg = loader()
        except Exception:
            cfg = None
    return mod, cfg


def _mail_step(mod, cfg, func: str, label: str, warned: set[str], **kwargs) -> int:
    """mail_io.<func>() 1단계 실행. 모듈/설정/함수 없으면 skip 로그 후 0."""
    if mod is None:
        _once_log(warned, f"mail {label} skip — core/mail_io.py 준비 중 "
                          f"(시뮬레이션 모드: data/inbox·outbox 파일 사용)")
        return 0
    fn = getattr(mod, func, None)
    if not callable(fn):
        _once_log(warned, f"mail {label} skip — core.mail_io.{func}() 준비 중")
        return 0
    if cfg is None and callable(getattr(mod, "load_config", None)):
        _once_log(warned, f"mail {label} skip — 설정 없음(secrets/mail.json). "
                          f"시뮬레이션 모드로 계속합니다.")
        return 0
    try:
        n = fn(**kwargs)
        return int(n or 0)
    except (ImportError, AttributeError) as e:
        _once_log(warned, f"mail {label} skip — mail_io 준비 중 ({e})")
        return 0
    except Exception as e:
        _log(f"[오류] mail {label} 실패: {e} — 다음 단계 진행")
        return 0


# ── 사이클 ───────────────────────────────────────────────

def run_cycle(warned: set[str] | None = None) -> dict:
    """1사이클 실행. 단계별 예외는 잡아서 로그 후 진행. 통계 dict 반환."""
    warned = warned if warned is not None else set()
    common.ensure_dirs()
    stats = {"fetched": 0, "processed": 0,
             "promoted": 0, "executed": 0, "waiting": 0, "sent": 0}

    mod, cfg = _load_mail_io()

    # ① IMAP 수신
    stats["fetched"] = _mail_step(mod, cfg, "fetch_new", "수신", warned)

    # ② inbox 파이프라인
    try:
        from . import mailbox
        stats["processed"] = len(mailbox.process_inbox() or [])
    except (ImportError, AttributeError):
        _once_log(warned, "inbox 처리 skip — core/mailbox.py 준비 중")
    except Exception as e:
        _log(f"[오류] inbox 처리 실패: {e} — 다음 단계 진행")

    # ③ 큐 1틱
    try:
        from . import queue
        tick = queue.run_tick() or {}
        for k in ("promoted", "executed", "waiting"):
            stats[k] = int(tick.get(k, 0))
    except (ImportError, AttributeError):
        _once_log(warned, "큐 처리 skip — core/queue.py 준비 중")
    except Exception as e:
        _log(f"[오류] 큐 처리 실패: {e} — 다음 단계 진행")

    # ④ SMTP 발신 (skip 시 outbox 파일이 그대로 남음 = 시뮬레이션 모드)
    stats["sent"] = _mail_step(mod, cfg, "send_pending", "발신", warned)

    # ⑤ 대시보드 갱신
    try:
        from . import dashboard
        dashboard.generate()
    except Exception as e:
        _log(f"[오류] 대시보드 생성 실패: {e} — 다음 단계 진행")

    return stats


def run(interval: int = 60, once: bool = False) -> int:
    """서비스 데몬 루프. once=True면 1사이클 후 종료. Ctrl-C로 깨끗이 종료."""
    mode = "1회" if once else f"{interval}초 간격"
    _log(f"Unplugin 서비스 시작 ({mode}) — 중지: Ctrl-C")
    warned: set[str] = set()
    try:
        while True:
            s = run_cycle(warned)
            _log(f"mail↓{s['fetched']} 처리{s['processed']} "
                 f"큐({s['promoted']}/{s['executed']}/{s['waiting']}) "
                 f"mail↑{s['sent']}")
            if once:
                return 0
            time.sleep(interval)
    except KeyboardInterrupt:
        print("서비스 종료")
        return 0
