import sys
import cv2
import os
import builtins
import importlib.abc
import importlib.util
from io import BytesIO
import struct
import zlib
import tempfile
import atexit
from collections.abc import Callable

# =========================
# CONFIG
# =========================
BUNDLE_PATH = None
BUNDLE_NAME = "assets.bin"
BUNDLE_MAGIC_BYTES = b"RCPTB"

FROZEN = getattr(sys, "frozen", False)

# =========================
# DECRYPTION
# =========================
_decyption_function = lambda x: x


# =========================
# TEMP FILE HANDLER
# =========================
_temp_files = []

def extract_temp(path_in_bundle):
    fp = vfs.read(path_in_bundle)
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.write(fp)
    tmp.close()
    _temp_files.append(tmp.name)
    return tmp.name

def cleanup_temp_files():
    for f in _temp_files:
        try:
            os.unlink(f)
        except:
            pass

def _norm(path: str) -> str:
    if not isinstance(path, str):
        return path
    path = path.replace("\\", "/").strip()
    if path == ".":
        return ""
    return path.strip("/")

# =========================
# HELPERS
# =========================
def resolve_bundle_path():
    candidates = []

    if BUNDLE_PATH:
        candidates.append(BUNDLE_PATH)

    candidates.append(os.path.abspath("assets.bin"))

    if hasattr(sys, "argv") and sys.argv[0]:
        main_path = os.path.abspath(sys.argv[0])
        candidates.append(os.path.join(os.path.dirname(main_path), "assets.bin"))

    exe_dir = os.path.dirname(sys.executable)
    candidates.append(os.path.join(exe_dir, "assets.bin"))

    candidates.append(sys.executable)

    for path in candidates:
        if not os.path.exists(path):
            continue

        try:
            with open(path, "rb") as f:
                f.seek(-4096, 2)
                if BUNDLE_MAGIC_BYTES in f.read():
                    return path
        except:
            continue

    return None

# =========================
# VFS CORE
# =========================
class VFS:
    MAGIC = BUNDLE_MAGIC_BYTES

    def __init__(self, decryption_function: Callable | None = None):
        self.index = {}
        self.fp = None
        self.decryption_function = decryption_function
        self._load_bundle()

    def _load_bundle(self):
        path = resolve_bundle_path()
        if not path:
            return

        with open(path, "rb") as f:
            data = f.read()

        if self.decryption_function:
            data = self.decryption_function(data)

        pos = data.rfind(self.MAGIC)
        if pos == -1:
            return

        self.fp = data
        offset = pos + len(self.MAGIC)
        count = struct.unpack_from("<I", data, offset)[0]
        offset += 4

        for _ in range(count):
            path_len = struct.unpack_from("<H", data, offset)[0]
            offset += 2

            path_str = data[offset:offset + path_len].decode()
            offset += path_len

            file_offset, file_size = struct.unpack_from("<II", data, offset)
            offset += 8

            self.index[path_str] = (file_offset, file_size)

    def exists(self, path: str) -> bool:
        path = _norm(path)
        if path in self.index:
            return True
        return any(p.startswith(path + "/") for p in self.index)

    def read(self, path: str) -> bytes:
        path = _norm(path)
        off, size = self.index[path]
        raw = self.fp[off:off + size]
        try:
            return zlib.decompress(raw)
        except:
            return raw

    def open_file(self, path: str):
        return BytesIO(self.read(path))

    def listdir(self, path: str):
        path = _norm(path)
        out = set()

        for p in self.index:
            if path and not p.startswith(path + "/"):
                continue
            rest = p[len(path)+1:] if path else p
            if rest:
                out.add(rest.split("/")[0])

        return list(out)

vfs = VFS(decryption_function=_decyption_function)

# =========================
# PATCH
# =========================
_real_open = builtins.open
_real_exists = os.path.exists
_real_listdir = os.listdir
_real_imread = cv2.imread

def vfs_open(path, *args, **kwargs):
    path = _norm(path)
    if isinstance(path, str) and vfs.exists(path):
        return vfs.open_file(path)
    return _real_open(path, *args, **kwargs)

def vfs_exists(path):
    return vfs.exists(path) or _real_exists(path)

def vfs_listdir(path):
    if vfs.exists(path):
        return vfs.listdir(path)
    return _real_listdir(path)

def vfs_imread(path, *args, **kwargs):
    if vfs.exists(path):
        return _real_imread(extract_temp(path), *args, **kwargs)
    return _real_imread(path, *args, **kwargs)

builtins.open = vfs_open

exists = vfs_exists
listdir = vfs_listdir
imread = vfs_imread

# =========================
# IMPORT HOOK
# =========================
class VFSLoader(importlib.abc.Loader):
    def exec_module(self, module):
        code = vfs.read(module.__spec__.origin)
        exec(compile(code, module.__spec__.origin, "exec"), module.__dict__)

class VFSFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        rel = fullname.replace(".", "/") + ".py"
        if vfs.exists(rel):
            return importlib.util.spec_from_loader(fullname, VFSLoader(), origin=rel)

        rel_init = fullname.replace(".", "/") + "/__init__.py"
        if vfs.exists(rel_init):
            return importlib.util.spec_from_loader(fullname, VFSLoader(), origin=rel_init, is_package=True)

        return None

sys.meta_path.insert(0, VFSFinder())
atexit.register(cleanup_temp_files)