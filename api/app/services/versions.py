"""Which version of a policy is the current one.

A document (for example "Travel Policy") can have many versions. Only the current one is scanned
for conflicts. Older ones are kept, with an end date, so "what did the rule say on March 3rd" can
still be answered. This runs when a version finishes processing and is `ready`, so a version that
fails to ingest never retires the one that works.
"""

from datetime import date


def plan_supersede(new, others: list, today: date) -> list[tuple[object, date]]:
    """Returns [(version, effective_to)] for the versions that stop being current.

    Normally the new version replaces the older ones. If the new version has an effective date
    earlier than a version already in the library, it is a back-filled history upload: the new one
    is the one that is superseded, and the newer version stays current.
    """
    ready = [o for o in others if o.status == "ready"]
    newer = [
        o.effective_from
        for o in others
        if o.status in ("ready", "superseded")  # a retired version still marks where history is
        if new.effective_from and o.effective_from and o.effective_from > new.effective_from
    ]
    if newer:
        return [(new, min(newer))]
    end = new.effective_from or today
    return [(o, end) for o in ready]
