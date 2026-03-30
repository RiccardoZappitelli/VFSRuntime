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
BUNDLE_PATH = None # None = auto-detect (appended to exe)
BUNDLE_NAME = "assets.bin"
FROZEN = getattr(sys, "frozen", False)

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
    vfs_log("extract_temp", f"path={path_in_bundle}", f"extracted to {tmp.name}")
    return tmp.name

def cleanup_temp_files():
    for f in _temp_files:
        try:
            os.unlink(f)
            vfs_log("cleanup_temp_files", f"file={f}", "deleted temp file")
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

def vfs_log(func_name, params, action):
    print(f"[VFS]({func_name}, {params}) {action}")

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

    # DEBUG
    for c in candidates:
        print(f"[resolve_bundle_path] Candidate: {c}")

    for path in candidates:
        if not os.path.exists(path):
            continue

        try:
            with open(path, "rb") as f:
                f.seek(-4096, 2)
                if VFS.MAGIC in f.read():
                    print(f"[resolve_bundle_path] FOUND: {path}")
                    return path
        except:
            continue

    print("[resolve_bundle_path] No bundle found")
    return None

# =========================
# VFS CORE
# =========================
class VFS:
    MAGIC = b"RCPT"

    def __init__(self, decryption_function: Callable|None=None):
        self.index = {}
        self.fp = None
        self._load_bundle()
        self.decryption_function = decryption_function

    def _load_bundle(self):
        path = resolve_bundle_path()
        if not path:
            vfs_log("_load_bundle", "", "no bundle detected")
            return
        print(f"{BUNDLE_PATH=}")
        vfs_log("_load_bundle", f"path={path}", "loading bundle")
        with open(path, "rb") as f:
            data = f.read()

        if self.decryption_function:
            try:
                data = self.decryption_function(data)
            except Exception as e:
                vfs_log("_load_bundle", f"path={path}", f"error while decryptiing bundle\n{e}")
                return

        pos = data.rfind(self.MAGIC)
        if pos == -1:
            vfs_log("_load_bundle", f"path={path}", "no bundle found")
            return

        self.fp = data
        offset = pos + len(self.MAGIC)
        count = struct.unpack_from("<I", data, offset)[0]
        offset += 4

        for _ in range(count):
            path_len = struct.unpack_from("<H", data, offset)[0]
            offset += 2

            path_bytes = data[offset:offset + path_len]
            offset += path_len
            path_str = path_bytes.decode()

            file_offset, file_size = struct.unpack_from("<II", data, offset)
            offset += 8

            self.index[path_str] = (file_offset, file_size)
        vfs_log("_load_bundle", f"loaded {len(self.index)} files", "bundle loaded")

    def exists(self, path: str) -> bool:
        path = _norm(path)
        if path in self.index:
            vfs_log("exists", f"path={path}", "file exists")
            return True

        # check if any file starts with this path + "/"
        for p in self.index:
            if p.startswith(path + "/"):
                vfs_log("exists", f"path={path}", "directory exists")
                return True

        vfs_log("exists", f"path={path}", "does not exist")
        return False

    def read(self, path: str) -> bytes:
        path = _norm(path)
        if path not in self.index:
            vfs_log("read", f"path={path}", "file not found")
            raise FileNotFoundError(path)

        off, size = self.index[path]
        raw = self.fp[off:off + size]

        try:
            data = zlib.decompress(raw)
            vfs_log("read", f"path={path}", f"read {len(data)} bytes (decompressed)")
            return data
        except:
            vfs_log("read", f"path={path}", f"read {len(raw)} bytes (raw)")
            return raw

    def open_file(self, path: str):
        path = _norm(path)
        vfs_log("open_file", f"path={path}", "returning BytesIO")
        return BytesIO(self.read(path))

    def listdir(self, path: str):
        # map "." to root
        path = _norm(path)
        if path == ".":
            path = ""
        out = set()

        for p in self.index:
            if path:
                if not p.startswith(path + "/"):
                    continue
                rest = p[len(path)+1:]  # skip prefix + /
            else:
                rest = p

            if rest:
                out.add(rest.split("/")[0])

        vfs_log("listdir", f"path={path}", f"found {len(out)} entries")
        return list(out)


vfs = VFS()

# =========================
# PATCH OPEN / OS
# =========================
_real_open = builtins.open
_real_exists = os.path.exists
_real_listdir = os.listdir
_real_imread = cv2.imread

def vfs_tree(path: str = ".", prefix: str = "") -> None:
    path = _norm(path)
    if path == ".":
        path = ""

    def _build(path: str, prefix: str) -> str:
        if not vfs.exists(path):
            return f"{prefix}{path or '.'} [not found]\n"

        entries = vfs.listdir(path)
        entries.sort()

        tree_str = ""

        for i, entry in enumerate(entries):
            full_path = f"{path}/{entry}" if path else entry
            connector = "└── " if i == len(entries) - 1 else "├── "
            tree_str += f"{prefix}{connector}{entry}\n"

            if vfs.exists(full_path) and vfs.listdir(full_path):
                extension = "    " if i == len(entries) - 1 else "│   "
                tree_str += _build(full_path, prefix + extension)

        return tree_str

    final_tree = _build(path, prefix)
    print(final_tree, end="")

def vfs_open(path, *args, **kwargs):
    path = _norm(path)
    if isinstance(path, str) and vfs.exists(path):
        vfs_log("vfs_open", f"path={path}", "serving from VFS")
        return vfs.open_file(path)
    vfs_log("vfs_open", f"path={path}", "fallback to real open")
    return _real_open(path, *args, **kwargs)

def vfs_exists(path):
    path = _norm(path)
    exists = vfs.exists(path) or _real_exists(path)
    vfs_log("vfs_exists", f"path={path}", f"exists={exists}")
    return exists

def vfs_listdir(path):
    path = _norm(path)
    if vfs.exists(path):
        vfs_log("vfs_listdir", f"path={path}", "listing VFS directory")
        return vfs.listdir(path)
    vfs_log("vfs_listdir", f"path={path}", "fallback to real listdir")
    return _real_listdir(path)

def vfs_imread(path, *args, **kwargs):
    if vfs.exists(path):
        tmp_path = extract_temp(path)
        vfs_log("cv2.imread", f"path={path}", f"reading via temp {tmp_path}")
        return _real_imread(tmp_path, *args, **kwargs)
    vfs_log("cv2.imread", f"path={path}", "reading from real path")
    return _real_imread(path, *args, **kwargs)

builtins.open = vfs_open

exists = vfs_exists
listdir = vfs_listdir
imread = vfs_imread

# =========================
# IMPORT HOOK
# =========================
class VFSLoader(importlib.abc.Loader):
    def create_module(self, spec):
        vfs_log("VFSLoader.create_module", f"module={spec.name}", "creating module")
        return None

    def exec_module(self, module):
        vfs_log("VFSLoader.exec_module", f"module={module.__name__}", "executing module")
        code = vfs.read(module.__spec__.origin)
        exec(compile(code, module.__spec__.origin, "exec"), module.__dict__)

class VFSFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        rel = fullname.replace(".", "/") + ".py"

        if vfs.exists(rel):
            vfs_log("VFSFinder.find_spec", f"module={fullname}", "found module in VFS")
            return importlib.util.spec_from_loader(
                fullname,
                VFSLoader(),
                origin=rel
            )

        # package (__init__.py)
        rel_init = fullname.replace(".", "/") + "/__init__.py"
        if vfs.exists(rel_init):
            vfs_log("VFSFinder.find_spec", f"module={fullname}", "found package in VFS")
            return importlib.util.spec_from_loader(
                fullname,
                VFSLoader(),
                origin=rel_init,
                is_package=True
            )

        vfs_log("VFSFinder.find_spec", f"module={fullname}", "not found in VFS")
        return None

sys.meta_path.insert(0, VFSFinder())
atexit.register(cleanup_temp_files)
