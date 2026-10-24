"""Explicit, resumable installation through FreeVideo's download routing."""
import json
from pathlib import Path
import shutil
import sys
import threading
from .. import disk_space

FAMILY = 'image-models'


def catalog():
    """The model list shipped beside this file.

    A frozen launcher also carries the engine source; its copy answers when the
    unpacked one is gone (a cleaned temporary folder, antivirus, an interrupted
    unpack). Nothing is remembered, so a restored file is used at once."""
    name = 'model.json'
    paths = [Path(__file__).with_name(name)]
    bundle = getattr(sys, '_MEIPASS', None)
    if bundle:
        paths.append(Path(bundle) / 'engine-source' / 'freevideo_engine' / 'prompt_vlm' / name)
    for path in paths:
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            missing = error
    raise missing


def available():
    """False while the model list cannot be read; nothing can be described or offered then."""
    try:
        catalog()
    except (OSError, ValueError):
        return False
    return True


def directory(root):
    spec = catalog()
    return Path(root) / 'models' / 'prompt-vlm' / spec['revision']


def ready(root):
    """Cheap, safe on the launcher's UI thread: version, sizes and modified times only.

    Files whose modified time moved are checked by content once, in the
    background; this returns False until that check has accepted them."""
    return _state(root, wait=False)


def settle(root):
    """Same answer, but a moved modified time is checked by content in the
    calling thread. For request handlers, never for a UI thread or under a lock."""
    return ready(root) or _state(root, wait=True)


_RECHECK = threading.Lock()
_BOOKKEEPING = threading.Lock()
_OUTCOME = {}
_RUNNING = set()


def _state(root, wait):
    try:
        spec, folder = catalog(), directory(root)
        receipt = json.loads((folder / 'verified.json').read_text(encoding='utf-8'))
        if receipt.get('revision') != spec['revision']:
            return False
        stats = {row['file']: (folder / row['file']).stat() for row in spec['files']}
        if any(stats[row['file']].st_size != row['bytes'] for row in spec['files']):
            return False
        moved = [row for row in spec['files']
                 if receipt['files'].get(row['file']) != stats[row['file']].st_mtime_ns]
        if not moved:
            return True
        key = (str(folder), spec['revision'],
               tuple((row['file'], stats[row['file']].st_size, stats[row['file']].st_mtime_ns) for row in moved))
        known = _OUTCOME.get(key)
        if known is not None:
            return known
        if wait:
            return _recheck(folder, spec, moved, key)
        with _BOOKKEEPING:
            if key in _RUNNING:
                return False
            _RUNNING.add(key)
        threading.Thread(target=_recheck, args=(folder, spec, moved, key), daemon=True,
                         name='prompt-model-recheck').start()
        return False
    except (OSError, ValueError, KeyError, TypeError):
        return False


def checking(root):
    """True while the files' content is being checked after a modified time moved.

    A cheap look at the same file identity ready() uses, for a page that must not
    call the model missing, or offer its download, in the meantime."""
    try:
        spec, folder = catalog(), directory(root)
        receipt = json.loads((folder / 'verified.json').read_text(encoding='utf-8'))
        if receipt.get('revision') != spec['revision']:
            return False
        stats = {row['file']: (folder / row['file']).stat() for row in spec['files']}
        if any(stats[row['file']].st_size != row['bytes'] for row in spec['files']):
            return False
        key = (str(folder), spec['revision'], tuple(
            (row['file'], stats[row['file']].st_size, stats[row['file']].st_mtime_ns)
            for row in spec['files'] if receipt['files'].get(row['file']) != stats[row['file']].st_mtime_ns))
    except (OSError, ValueError, KeyError, TypeError):
        return False
    with _BOOKKEEPING:
        return key in _RUNNING and key not in _OUTCOME


def _recheck(folder, spec, moved, key):
    """Accept files whose modified time changed (copied folder, unpacked archive,
    antivirus) when their content still matches the catalog, then refresh the
    receipt. The outcome is remembered per file identity, so one set of files is
    hashed once whatever the answer."""
    from .. import provision
    from ..monitoring import save
    ledger_path = folder / 'download-verified.json'
    try:
        with _RECHECK:
            if key in _OUTCOME:
                return _OUTCOME[key]
            try:
                ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                ledger = {}
            ok = all(provision.verified(folder / row['file'], row, ledger) for row in moved)
            if ok:
                save(ledger_path, ledger)
                save(folder / 'verified.json', dict(revision=spec['revision'], files={
                    row['file']: (folder / row['file']).stat().st_mtime_ns for row in spec['files']}))
            _OUTCOME[key] = ok
            return ok
    except Exception:
        _OUTCOME[key] = False
        return False
    finally:
        with _BOOKKEEPING:
            _RUNNING.discard(key)


def remote(spec, row):
    """One catalog file with every source FreeVideo may fetch it from.

    Hugging Face hosts are pinned to the catalog revision. ModelScope has no
    matching commit, so its copy is accepted only when the size and SHA-256 in
    the catalog match, as for the image model.
    """
    from ..network import source_url
    hf = '/%s/resolve/%s/%s' % (spec['repo'], spec['revision'], row['file'])
    mirror = spec['modelscope']
    return dict(repo=spec['repo'], revision=spec['revision'], file=row['file'], family='image', sources=[
        dict(id='official', url=source_url('models', 'official') + hf),
        dict(id='hf-mirror', url=source_url('models', 'hf-mirror') + hf),
        dict(id='modelscope', url=source_url(FAMILY, 'modelscope') + '/models/%s/resolve/%s/%s' % (
            mirror['repo'], mirror['revision'], row['file']))])


def install(root, progress, check):
    from .. import network, provision
    from ..adaln_assets import _download_plan
    from ..monitoring import save
    if ready(root):
        return
    folder, spec = directory(root), catalog()
    folder.mkdir(parents=True, exist_ok=True)
    ledger_path = folder / 'download-verified.json'
    try:
        ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        ledger = {}
    missing = [row for row in spec['files'] if not provision.verified(folder / row['file'], row, ledger)]
    total = sum(row['bytes'] for row in missing)
    retained = 0
    for row in missing:
        path = folder / row['file']
        partial = path.with_suffix(path.suffix + '.partial')
        if partial.is_file():
            size = partial.stat().st_size
            if size < row['bytes']:
                retained += size
    if disk_space.free_bytes(folder) < total - retained + 256 * 2**20:
        raise ValueError('disk_space')
    plan = _download_plan(root)
    # Same three hosts as the image model, so the same ordering, measured
    # routes and Download source choice apply. Installs whose plan predates
    # that family keep their Hugging Face order, with ModelScope after it.
    sources = plan['sources'] = dict(plan.get('sources', {}))
    if not sources.get(FAMILY):
        sources[FAMILY] = [dict(row) for row in sources.get('models', [])
                           if row['id'] in ('official', 'hf-mirror')] or [{'id': 'official'}, {'id': 'hf-mirror'}]
        sources[FAMILY].append({'id': 'modelscope'})
    plan.update(quiet=True, resource_check=check)
    done = 0
    for row in missing:
        check()
        path = folder / row['file']
        def moved(current, size, speed, **kwargs):
            progress(dict(phase='download', done=done + current, total=total))
        network.download(network.model_urls(plan, remote(spec, row)), path, row['sha256'], moved,
                         network=plan, size=row['bytes'], category=FAMILY, keep_partial=True, stall_seconds=30,
                             slow_seconds=15, low_speed_limit=64 * 1024)
        ledger[str(path)] = provision.file_identity(path, row)
        save(ledger_path, ledger)
        done += row['bytes']
    save(folder / 'verified.json', dict(revision=spec['revision'], files={
        row['file']: (folder / row['file']).stat().st_mtime_ns for row in spec['files']}))
