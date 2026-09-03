"""Container sniffing and duration bounds for uploaded recordings.

The browser tells us the MIME type and the elapsed seconds, and a candidate can
say anything they like in either. So we sniff the container's magic bytes the
way :mod:`jobs.validators` does for résumés, and clamp the reported duration to
what the question actually allowed (plus a little slack for the recorder's own
lag) before it is billed as video minutes.
"""

import logging
import os
import struct

logger = logging.getLogger(__name__)

#: Leading magic bytes for the containers we accept.
WEBM_MAGIC = b"\x1a\x45\xdf\xa3"  # Matroska/WebM EBML header
MP4_FTYP = b"ftyp"  # at offset 4 in an ISO base media file

#: Slack allowed over ``question.answer_seconds`` for recorder/upload lag.
DURATION_SLACK_SECONDS = 5

#: Bytes of header we read to sniff a container.
SNIFF_BYTES = 16


class UnsupportedContainer(Exception):
    """The upload's bytes are not a WebM or MP4 container."""


def _head(uploaded, size=SNIFF_BYTES):
    """Read the first ``size`` bytes of a file-like object without consuming it."""
    try:
        position = uploaded.tell()
    except (AttributeError, OSError):
        position = None
    try:
        uploaded.seek(0)
        head = uploaded.read(size) or b""
    except (AttributeError, OSError, ValueError):
        return b""
    finally:
        try:
            uploaded.seek(position or 0)
        except (AttributeError, OSError, ValueError):
            pass
    if isinstance(head, str):  # pragma: no cover - text-mode handles
        head = head.encode("utf-8", "ignore")
    return head


def sniff_container(uploaded):
    """Return ``"webm"``, ``"mp4"`` or ``None`` (unreadable/too short) for a file."""
    head = _head(uploaded)
    if not head:
        return None
    if head.startswith(WEBM_MAGIC):
        return "webm"
    if len(head) >= 8 and head[4:8] == MP4_FTYP:
        return "mp4"
    return ""


def container_for_mime(mime, extension=""):
    """The container name implied by a declared MIME type / filename extension."""
    mime = (mime or "").split(";")[0].strip().lower()
    if mime == "video/webm":
        return "webm"
    if mime == "video/mp4":
        return "mp4"
    extension = (extension or "").lower().lstrip(".")
    return extension if extension in ("webm", "mp4") else ""


def check_container(uploaded, mime, extension=""):
    """Verify the file's bytes match the container it claims to be.

    Raises :class:`UnsupportedContainer` on a mismatch or on bytes that are
    neither WebM nor MP4. An unreadable/empty header is *not* rejected — the
    size and extension checks already cover empty uploads, and some storage
    backends hand us a stream we cannot rewind.
    """
    sniffed = sniff_container(uploaded)
    if sniffed is None:
        return None
    if not sniffed:
        raise UnsupportedContainer(
            "That file is not a WebM or MP4 recording."
        )
    declared = container_for_mime(mime, extension)
    if declared and declared != sniffed:
        raise UnsupportedContainer(
            f"The recording says it is {declared} but its contents are {sniffed}."
        )
    return sniffed


# --- duration ------------------------------------------------------------


def max_duration_for(question):
    """The largest duration we will bill for one answer to ``question``."""
    allowed = int(getattr(question, "answer_seconds", 0) or 0)
    return max(0, allowed) + DURATION_SLACK_SECONDS


def clamp_duration(claimed, question):
    """Clamp a client-reported duration to the question's allowance.

    Video minutes are metered and billed, so a candidate (or a tampered page)
    must not be able to charge a workspace for an hour of video by typing a big
    number into the ``duration`` field.
    """
    try:
        seconds = int(float(claimed or 0))
    except (TypeError, ValueError):
        seconds = 0
    return max(0, min(seconds, max_duration_for(question)))


def probe_duration(uploaded):
    """Best-effort real duration in seconds from the container header.

    Only the cheap cases are handled: an MP4 ``mvhd`` box near the front of the
    file. WebM stores its duration as a float inside the EBML ``Info`` element,
    which is not worth parsing by hand, so WebM returns ``None`` and the caller
    falls back to the clamped client value. Returns ``None`` whenever the
    duration cannot be read cheaply.
    """
    try:
        position = uploaded.tell()
    except (AttributeError, OSError):
        position = None
    try:
        uploaded.seek(0)
        head = uploaded.read(64 * 1024) or b""
    except (AttributeError, OSError, ValueError):
        return None
    finally:
        try:
            uploaded.seek(position or 0)
        except (AttributeError, OSError, ValueError):
            pass
    if isinstance(head, str) or len(head) < 8 or head[4:8] != MP4_FTYP:
        return None
    index = head.find(b"mvhd")
    if index < 0:
        return None
    try:
        version = head[index + 4]
        if version == 0:
            scale, units = struct.unpack(">II", head[index + 16 : index + 24])
        elif version == 1:
            scale, units = struct.unpack(">IQ", head[index + 24 : index + 36])
        else:
            return None
    except (struct.error, IndexError):
        return None
    if not scale or units <= 0:
        return None
    seconds = units / scale
    if seconds <= 0 or seconds > 24 * 60 * 60:
        return None
    return int(round(seconds))


def metered_duration(uploaded, claimed, question):
    """The duration to bill: the real one when cheap to read, else the clamped claim.

    Either way the result never exceeds the question's allowance.
    """
    ceiling = max_duration_for(question)
    probed = probe_duration(uploaded)
    if probed is not None:
        return max(0, min(probed, ceiling))
    return clamp_duration(claimed, question)


def extension_of(name):
    """Lowercase extension of an upload name, without the dot."""
    return os.path.splitext(name or "")[1].lower().lstrip(".")
