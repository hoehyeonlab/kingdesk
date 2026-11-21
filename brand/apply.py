#!/usr/bin/env python3
"""Apply the brand in brand.json to a pristine upstream tree.

The upstream sources stay untouched in git; CI runs this right after checkout
(submodules included). Every edit is an exact-string replacement with an
expected match count, so an upstream change that moves a branded string fails
the build instead of silently shipping the upstream name.

    python3 brand/apply.py           # apply
    python3 brand/apply.py --check   # verify every pattern still matches, write nothing

Under GitHub Actions it also exports APP_NAME and APP_LOWER to later steps.
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

with open(os.path.join(HERE, "brand.json"), encoding="utf-8") as f:
    BRAND = json.load(f)

NAME = BRAND["name"]
LOWER = NAME.lower()
BUNDLE_ID = BRAND["bundle_id"]
DESCRIPTION = BRAND["description"]
COMPANY = BRAND["company"]

# (file, old, new, expected occurrences)
EDITS = [
    # Runtime app name: window titles, config/log dirs, install dir, service names, URI scheme.
    ("libs/hbb_common/src/config.rs",
     'pub static ref APP_NAME: RwLock<String> = RwLock::new("RustDesk".to_owned());',
     f'pub static ref APP_NAME: RwLock<String> = RwLock::new("{NAME}".to_owned());', 1),

    # Windows: version resource of the app exe.
    ("flutter/windows/runner/Runner.rc",
     'VALUE "CompanyName", "Purslane Tech Pte. Ltd." "\\0"',
     f'VALUE "CompanyName", "{COMPANY}" "\\0"', 1),
    ("flutter/windows/runner/Runner.rc",
     'VALUE "FileDescription", "RustDesk Remote Desktop" "\\0"',
     f'VALUE "FileDescription", "{DESCRIPTION}" "\\0"', 1),
    ("flutter/windows/runner/Runner.rc",
     'VALUE "InternalName", "rustdesk" "\\0"',
     f'VALUE "InternalName", "{LOWER}" "\\0"', 1),
    ("flutter/windows/runner/Runner.rc",
     'VALUE "OriginalFilename", "rustdesk.exe" "\\0"',
     f'VALUE "OriginalFilename", "{NAME}.exe" "\\0"', 1),
    ("flutter/windows/runner/Runner.rc",
     'VALUE "ProductName", "RustDesk" "\\0"',
     f'VALUE "ProductName", "{NAME}" "\\0"', 1),
    ("flutter/windows/runner/main.cpp",
     'std::wstring app_name = L"RustDesk";',
     f'std::wstring app_name = L"{NAME}";', 1),

    # Windows: version resource of librustdesk.dll and of the single-file launcher.
    ("Cargo.toml", 'ProductName = "RustDesk"', f'ProductName = "{NAME}"', 1),
    ("Cargo.toml", 'FileDescription = "RustDesk Remote Desktop"', f'FileDescription = "{DESCRIPTION}"', 1),
    ("libs/portable/Cargo.toml", 'description = "RustDesk Remote Desktop"', f'description = "{DESCRIPTION}"', 1),
    ("libs/portable/Cargo.toml", 'ProductName = "RustDesk"', f'ProductName = "{NAME}"', 1),
    ("libs/portable/Cargo.toml", 'OriginalFilename = "rustdesk.exe"', f'OriginalFilename = "{NAME}.exe"', 1),
    ("libs/portable/Cargo.toml", 'FileDescription = "RustDesk Remote Desktop"', f'FileDescription = "{DESCRIPTION}"', 1),

    # macOS: bundle name, executable name, bundle id, URL scheme.
    ("flutter/macos/Runner/Configs/AppInfo.xcconfig", "PRODUCT_NAME = RustDesk", f"PRODUCT_NAME = {NAME}", 1),
    ("flutter/macos/Runner/Configs/AppInfo.xcconfig",
     "PRODUCT_BUNDLE_IDENTIFIER = com.carriez.flutterHbb", f"PRODUCT_BUNDLE_IDENTIFIER = {BUNDLE_ID}", 1),
    ("flutter/macos/Runner.xcodeproj/project.pbxproj",
     "PRODUCT_BUNDLE_IDENTIFIER = com.carriez.rustdesk;", f"PRODUCT_BUNDLE_IDENTIFIER = {BUNDLE_ID};", 3),
    ("flutter/macos/Runner.xcodeproj/project.pbxproj", "RustDesk.app", f"{NAME}.app", 4),
    ("flutter/macos/Runner.xcodeproj/xcshareddata/xcschemes/Runner.xcscheme", "RustDesk.app", f"{NAME}.app", 4),
    ("flutter/macos/Runner/Info.plist", "<string>com.carriez.rustdesk</string>", f"<string>{BUNDLE_ID}</string>", 1),
    ("flutter/macos/Runner/Info.plist", "<string>rustdesk</string>", f"<string>{LOWER}</string>", 1),
    ("build.py",
     "./build/macos/Build/Products/Release/RustDesk.app/Contents/MacOS/')",
     f"./build/macos/Build/Products/Release/{NAME}.app/Contents/MacOS/')", 1),

    # UI: title bar text on Windows/Linux.
    ("flutter/lib/desktop/widgets/tabbar_widget.dart",
     '"RustDesk",\n                              style: TextStyle(fontSize: 13),',
     f'"{NAME}",\n                              style: TextStyle(fontSize: 13),', 1),
    # UI: drop the "set up your own server" hint next to the ready status.
    ("flutter/lib/desktop/pages/connection_page.dart",
     "            offstage: !(!_svcStopped.value &&\n"
     "                stateGlobal.svcStatus.value == SvcStatus.ready &&\n"
     "                _svcIsUsingPublicServer.value),",
     "            offstage: true,", 1),
]

# brand/icons/<src> -> destinations in the tree
ICONS = {
    "icon.ico": ["res/icon.ico", "flutter/windows/runner/resources/app_icon.ico"],
    "tray.ico": ["res/tray-icon.ico"],
    "AppIcon.icns": ["flutter/macos/Runner/AppIcon.icns"],
    "mac-tray-dark-x2.png": ["res/mac-tray-dark-x2.png"],
    "mac-tray-light-x2.png": ["res/mac-tray-light-x2.png"],
    "icon.svg": ["flutter/assets/icon.svg", "res/logo.svg", "res/scalable.svg"],
    "icon-256.png": ["flutter/assets/icon.png", "res/128x128@2x.png"],
    "icon-128.png": ["res/128x128.png"],
    "icon-64.png": ["res/64x64.png"],
    "icon-32.png": ["res/32x32.png"],
    "icon-1024.png": ["res/icon.png"],
    "mac-icon-1024.png": ["res/mac-icon.png"],
}


def main():
    check_only = "--check" in sys.argv[1:]
    errors = []
    pending = {}
    for path, old, new, expected in EDITS:
        full = os.path.join(ROOT, path)
        if path not in pending:
            with open(full, encoding="utf-8", newline="") as f:
                pending[path] = f.read()
        text = pending[path]
        # Windows checkouts turn LF into CRLF (.gitattributes: text=auto); follow the file.
        if "\r\n" in text:
            old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
        found = text.count(old)
        if found == expected:
            pending[path] = text.replace(old, new)
        elif found == 0 and old != new and text.count(new) >= expected:
            pass  # already applied
        else:
            errors.append(f"{path}: expected {expected} x {old!r}, found {found}")
    for src, dests in ICONS.items():
        if not os.path.isfile(os.path.join(HERE, "icons", src)):
            errors.append(f"brand/icons/{src}: missing")
        for dest in dests:
            if not os.path.isdir(os.path.dirname(os.path.join(ROOT, dest))):
                errors.append(f"{dest}: destination directory missing")
    if errors:
        print("brand: upstream no longer matches:\n  " + "\n  ".join(errors), file=sys.stderr)
        return 1
    if check_only:
        print(f"brand: {len(EDITS)} edits and {len(ICONS)} icons match ({NAME})")
        return 0
    for path, text in pending.items():
        with open(os.path.join(ROOT, path), "w", encoding="utf-8", newline="") as f:
            f.write(text)
    for src, dests in ICONS.items():
        for dest in dests:
            shutil.copyfile(os.path.join(HERE, "icons", src), os.path.join(ROOT, dest))
    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a", encoding="utf-8", newline="\n") as f:
            f.write(f"APP_NAME={NAME}\nAPP_LOWER={LOWER}\n")
    print(f"brand: applied {NAME} ({BUNDLE_ID})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
