# VFS Runtime (Plug & Play)

Lightweight virtual file system for embedding Python + assets into a
single binary.\
Designed for **Nuitka onefile** but works in dev and standalone too.

------------------------------------------------------------------------

## Features

-   No code refactor required
-   Transparent file access (`open`, `listdir`, `exists`)
-   Supports compressed assets (zlib)
-   Import Python modules directly from bundle
-   Auto-detects bundle (external or appended)
-   OpenCV `imread` support via temp extraction
-   Debug logging built-in

------------------------------------------------------------------------

## Structure

    vfs_runtime/
    ├── __init__.py
    ├── vfs_runtime.py
    ├── conf.py
    └── create_bundle.py

------------------------------------------------------------------------

## Usage

### 1. Create bundle

``` bash
python create_bundle.py
```

Default:

    assets/ → assets.bin

------------------------------------------------------------------------

### 2. Import VFS (that's it)

``` python
from vfs_runtime import *
```

------------------------------------------------------------------------

### 3. Use normally

``` python
open("vfx/smoke.png", "rb")
listdir("vfx")
exists("vfx")
```

------------------------------------------------------------------------

## Nuitka Onefile

### Build

``` bash
python -m nuitka --onefile your_script.py
```

### Append bundle

``` bash
--include-data-file=assets.bin=assets.bin
```

------------------------------------------------------------------------

## Dev / Standalone

Works automatically if `assets.bin` is in: - current working dir - same
dir as script - same dir as executable

------------------------------------------------------------------------

## OpenCV Support

``` python
img = imread("vfx/image.png")
```

------------------------------------------------------------------------

## Debug

    [VFS](read, path=vfx/smoke.png) read 1234 bytes

------------------------------------------------------------------------

## Limitations

-   Some libraries (like winsound) require real file paths
-   Large bundles are fully loaded in memory

------------------------------------------------------------------------

## Base Example

``` python
from vfs_runtime import *

print(listdir("vfx"))

with open("vfx/smoke.png", "rb") as f:
    data = f.read()
```

## CONFIGURATION & ENCRYPTION
```python
import vfs_runtime.conf as conf
from vfs_runtime.create_bundle import make_bundle
from vfs_runtime import *

def xor_encrypt(data: str, key: int) -> str:
    return bytes(b ^ key for b in data)

def xor_decrypt(encrypted_text: str, key: int) -> str:
    return xor_encrypt(encrypted_text, key)

conf.encryption_function = lambda x:xor_encrypt(x, 46) #46 is the key
conf.decryption_function = lambda x:xor_decrypt(x, 46)
"""Bundle creation
make_bundle("test_directory", "assets.bin")
"""

init_vfs()
```

------------------------------------------------------------------------

## Summary

-   Drop-in module
-   Works with Nuitka onefile
-   Assets + Python fully embedded
