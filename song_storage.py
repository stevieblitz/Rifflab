"""Deterministic per-song .riff paths; never reuse another track's identity."""
import hashlib
import json
import re
from pathlib import Path


def song_basename(metadata, fallback):
    artist = str((metadata or {}).get('artist') or '').strip()
    title = str((metadata or {}).get('title') or '').strip()
    label = f'{artist} - {title}' if artist and title else title or fallback
    return re.sub(r'[^a-zA-Z0-9._ -]+', '_', label).strip(' .') or 'Untitled'


def manifest_for_song(folder, metadata, source_audio, stem_folder, fallback):
    """Return safe target manifest. Existing files only match same source."""
    target_dir = Path(folder)
    label = song_basename(metadata, fallback)
    primary = target_dir / (label + '.riff')
    source_id = str((metadata or {}).get('source_id') or '').strip()
    identity = source_id or str(source_audio or stem_folder or '').strip()
    if not identity:
        raise ValueError('Cannot identify a song without an audio source.')
    candidates = [primary]
    digest = hashlib.sha256(identity.encode('utf-8')).hexdigest()[:12]
    candidates.append(target_dir / f'{label}-{digest}.riff')
    for candidate in candidates:
        if not candidate.exists():
            return candidate
        try:
            existing = json.loads(candidate.read_text(encoding='utf-8'))
            previous_meta = existing.get('metadata') or {}
            previous_id = str(previous_meta.get('source_id') or '').strip()
            if source_id and previous_id == source_id:
                return candidate
            if (not source_id and
                    (existing.get('source_audio') == source_audio or
                     existing.get('stem_folder') == stem_folder)):
                return candidate
        except (OSError, ValueError, TypeError):
            pass
    raise FileExistsError(f'Song identity collision: {label}')
