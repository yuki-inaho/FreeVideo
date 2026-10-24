"""Children of an offline runtime start from its short root.

Where Windows limits path length, runtime_alias gives the runtime folder a short
junction. The launcher marks a child's environment with that view, and
processes.popen then spells the command, the environment and the working folder
through it, for that child and for every process it starts in turn. Nothing
else changes: settings, receipts and everything on screen keep the real paths.
"""
from collections import namedtuple
import json
import os
from pathlib import Path
import re
import sys

from .long_paths import io_path, plain

VIEW_ENV = 'FREEVIDEO_RUNTIME_VIEW'
ONLINE_ENGINE = 'freevideo-engine'  # the folder an online installation is made in


class View(namedtuple('View', 'real root rules', defaults=(os.path,))):
    """real: the runtime folder; root: what children see; rules: os.path or ntpath."""
    __slots__ = ()

    @property
    def used(self):
        return _key(self.real, self.rules) != _key(self.root, self.rules)


def _key(path, rules):
    return rules.normcase(rules.normpath(os.fspath(path)))


def _within(path, root, rules):
    path, root = _key(path, rules), _key(root, rules)
    if not rules.isabs(path):
        return False
    try:
        return rules.commonpath((path, root)) == root
    except ValueError:  # Another drive.
        return False


def _moved(path, source, target, rules):
    relative = rules.relpath(rules.normpath(os.fspath(path)), os.fspath(source))
    return rules.normpath(rules.join(os.fspath(target), relative))


def value(item, view):
    """A path inside the runtime, spelled under the view; anything else as given."""
    if not isinstance(item, (str, os.PathLike)):
        return item
    # What resolving a deep file returns on Windows names the same file.
    path = plain(item, windows=view.rules.__name__ == 'ntpath')
    if not _within(path, view.real, view.rules):
        return item
    return _moved(path, view.real, view.root, view.rules)


def view_for(real_root) -> View:
    """May create the junction; AliasUnavailable when one is needed and cannot be made."""
    from . import runtime_alias
    real = Path(plain(real_root))
    return View(real, runtime_alias.runtime_view(real))


def for_engine(engine_root) -> View:
    """The view of the offline runtime around this engine folder, if it needs one.

    An installation made online is its engine folder: it gets a view only where the system
    code page cannot spell its folder or its deepest library is beyond the loader's limit,
    and one that cannot be made is not an error.
    """
    from . import runtime_alias
    engine = Path(plain(engine_root))
    root = engine.parent
    # The first two tests read nothing from disk wherever no junction is needed.
    # The third asks by the extended path: where a junction is needed, the plain
    # one is not found beyond 259 characters.
    if (engine.name.casefold() == 'engine' and runtime_alias.needs_view(root)
            and io_path(root / 'portable.json').is_file()):
        return view_for(root)
    if engine.name.casefold() == 'engine':
        return View(engine, engine)
    try:
        # An installation made online is its engine folder. It gets a view where the system code
        # page cannot spell the folder or the loader cannot open its deepest library; one that
        # cannot be made is not an error.
        if runtime_alias.needs_view(engine, spelling_only=True) or runtime_alias.online_loaded_too_long(engine):
            return view_for(engine)
    except OSError:  # Includes a junction that cannot be made: the checks after it name what fails.
        pass
    return View(engine, engine)


def restart_arguments(arguments, prefix=None, environ=None):
    """The command line and environment that run this command again from the engine's short folder.

    None where the process is not an engine's own Python on Windows, already runs from a
    short folder, or its folder needs none. A command-line run reaches the libraries
    (torch\\lib\\c10.dll) by the interpreter's own path, so only a restart can shorten it.
    """
    from . import runtime_alias
    environ = os.environ if environ is None else environ
    if not runtime_alias._backend.windows() or current(environ) is not None:
        return None
    prefix = Path(plain(sys.prefix if prefix is None else prefix))
    if prefix.parent.name.casefold() != 'envs':
        return None
    try:
        view = for_engine(prefix.parent.parent)
    except OSError:
        return None
    if not view.used:
        return None
    command, child, _ = execution([sys.executable, '-m', 'freevideo_engine', *arguments], environ, None, view)
    return command, child


def for_file(path):
    """The view of the offline runtime that holds this file, or None.

    The file belongs to the nearest folder above it that has a runtime's
    manifest, whichever installation the launcher itself runs from or shows.
    """
    from . import runtime_alias
    path = Path(plain(path))
    for root in path.parents:
        try:
            if runtime_alias.needs_view(root) and io_path(root / 'portable.json').is_file():
                return view_for(root)
        except OSError:  # Includes a junction that cannot be made: opened as it is.
            return None
    return None


def entry_lines(view):
    """For the node's entry file, which runs before any module of ours can be
    imported: the source its receipt names, taken from the view the process has."""
    if not view.used:
        return ''
    return ("import os as _os\n"
            "_view = _os.environ.get(%r, '').split('|')\n"
            "if len(_view) == 2 and _source.is_relative_to(_view[1]):\n"
            "    _source = _Path(_view[0]) / _source.relative_to(_view[1])\n") % VIEW_ENV


def current(environ=None):
    parts = (os.environ if environ is None else environ).get(VIEW_ENV, '').split('|')
    if len(parts) != 2 or not all(os.path.isabs(part) for part in parts):
        return None
    return View(Path(parts[1]), Path(parts[0]))


def environment_view(env, view):
    """Mark a child's environment; processes.popen does the rest."""
    return dict(env, **{VIEW_ENV: '%s|%s' % (view.root, view.real)}) if view.used else env


def execution(command, env, cwd, view):
    """One child's command, environment and folder, spelled through the view."""
    separator = ';' if view.rules.__name__ == 'ntpath' else ':'

    def argument(item):
        if isinstance(item, str) and item.startswith('--') and '=' in item:
            flag, path = item.split('=', 1)
            return flag + '=' + value(path, view)
        return value(item, view)

    def variable(text):
        if separator not in text:
            return value(text, view)
        return separator.join(value(part, view) for part in text.split(separator))

    environment = {key: variable(text) for key, text in (os.environ if env is None else env).items()}
    environment[VIEW_ENV] = '%s|%s' % (view.root, view.real)
    return [argument(item) for item in command], environment, value(cwd, view)


def text_back(text, view):
    """What a child printed, with the real folder in place of the view."""
    if not view.used:
        return text
    windows = view.rules.__name__ == 'ntpath'
    # A JSON string doubles each backslash; the replacement keeps that form.
    pattern = r'[/\\]+'.join(re.escape(part) for part in re.split(r'[/\\]+', str(view.root)))
    real = str(view.real)

    def replace(match):
        return real.replace('\\', '\\\\') if '\\\\' in match.group(0) else real

    return re.sub(r'(?<![\w/\\:.-])' + pattern + r'(?![\w.-])', replace, text, flags=re.IGNORECASE if windows else 0)


def line_back(line, view):
    """One line of a child's output; a JSON row stays a JSON row."""
    if not view.used:
        return line
    if line.startswith('{'):
        try:
            row = json.loads(line)
        except ValueError:
            return text_back(line, view)

        def back(item):
            if isinstance(item, dict):
                return {key: back(inner) for key, inner in item.items()}
            if isinstance(item, list):
                return [back(inner) for inner in item]
            return text_back(item, view) if isinstance(item, str) else item

        changed = back(row)
        return line if changed == row else json.dumps(changed, ensure_ascii=False) + ('\n' if line.endswith('\n') else '')
    return text_back(line, view)
