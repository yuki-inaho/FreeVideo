"""The Linux launcher as an AppImage: its own file, and a clean environment for everything it starts.

PyInstaller points LD_LIBRARY_PATH at the libraries it bundles, and the AppImage
runtime adds APPIMAGE, APPDIR, ARGV0 and OWD. Inherited by bash, git, curl, the
ComfyUI Python or the browser, the bundled libraries replace the system's and
those programs fail in ways that look unrelated (an OpenSSL symbol missing in
git, a browser that will not start). The dynamic linker reads LD_LIBRARY_PATH
once, when a process starts, so the launcher restores the original value for
itself as soon as it runs, and every child inherits a clean environment.
"""
import os
from pathlib import Path
import sys

APPIMAGE_VARIABLES = ('APPIMAGE', 'APPDIR', 'ARGV0', 'OWD', 'APPIMAGE_UUID')
# Set by PyInstaller's bootloader and its Qt runtime hook for the bundle only.
BUNDLE_PREFIXES = ('_PYI_', '_MEI')
QT_VARIABLES = ('QT_PLUGIN_PATH', 'QML2_IMPORT_PATH', 'QML_IMPORT_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH')
_captured = {}


def frozen_linux():
    return getattr(sys, 'frozen', False) and sys.platform.startswith('linux')


def bundle_directory():
    return Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent)).resolve()


def inside_bundle(value):
    """Whether a path-list variable points into this launcher's own files."""
    roots = [bundle_directory()]
    if _captured.get('APPDIR'):
        roots.append(Path(_captured['APPDIR']).resolve())
    for entry in str(value).split(os.pathsep):
        if not entry:
            continue
        try:
            path = Path(entry).resolve()
        except (OSError, RuntimeError):
            continue
        if any(path == root or root in path.parents for root in roots):
            return True
    return False


def child_environment(environ=None):
    """The environment for a program this launcher starts, as if started from the desktop."""
    env = dict(os.environ if environ is None else environ)
    if not frozen_linux():
        return env
    original = env.pop('LD_LIBRARY_PATH_ORIG', None)
    if original is not None:
        env['LD_LIBRARY_PATH'] = original
    elif 'LD_LIBRARY_PATH' in env and inside_bundle(env['LD_LIBRARY_PATH']):
        env.pop('LD_LIBRARY_PATH')
    if not env.get('LD_LIBRARY_PATH', 'x'):
        env.pop('LD_LIBRARY_PATH')
    for name in list(env):
        if name in APPIMAGE_VARIABLES or name.startswith(BUNDLE_PREFIXES):
            env.pop(name)
        elif name in QT_VARIABLES and inside_bundle(env[name]):
            env.pop(name)
    # Setup also runs through bash and a managed, non-frozen Python. Carry the
    # selected fallback on PATH so those workers use system.curl_executable()
    # just like the GUI. Append it: existing system tools keep priority.
    from .system import curl_executable, curl_ca_arguments
    bundled = bundle_directory() / 'curl/curl'
    curl = curl_executable(env) if bundled.is_file() else None
    if curl is not None and Path(curl) == bundled:
        folder = str(Path(curl).parent)
        path = env.get('PATH', os.defpath)
        if folder not in path.split(os.pathsep):
            env['PATH'] = path + os.pathsep + folder if path else folder
        certificates = curl_ca_arguments(curl, env)
        if certificates:
            # curl reads no variable for proxy roots; curl_command and setup pass this one on.
            env['CURL_CA_BUNDLE'] = env['FREEVIDEO_CURL_PROXY_CA'] = certificates[1]
    return env


def prepare():
    """At start: remember the AppImage, then give this process the environment its children need.

    Qt's own paths stay until the window exists; child_environment() leaves them
    out for children in the meantime.
    """
    if not frozen_linux():
        return
    for name in APPIMAGE_VARIABLES:
        if os.environ.get(name):
            _captured[name] = os.environ[name]
    original = os.environ.pop('LD_LIBRARY_PATH_ORIG', None)
    if original is not None:
        os.environ['LD_LIBRARY_PATH'] = original
        if not original:
            os.environ.pop('LD_LIBRARY_PATH')
    elif inside_bundle(os.environ.get('LD_LIBRARY_PATH', '')):
        # PyInstaller saves no original when the person had none: the value is the bundle's alone.
        os.environ.pop('LD_LIBRARY_PATH')
    for name in APPIMAGE_VARIABLES:
        os.environ.pop(name, None)


def appimage():
    """The AppImage file this launcher runs from, or None outside an AppImage."""
    value = _captured.get('APPIMAGE') or (os.environ.get('APPIMAGE') if frozen_linux() else None)
    if not value:
        return None
    path = Path(value)
    return path if path.is_file() else None
