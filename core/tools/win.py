from __future__ import annotations

import asyncio
import base64
from typing import Optional

_PWSH = ["powershell", "-NoProfile", "-NonInteractive"]

_SENDKEYS_KEYS = {
    "enter": "{ENTER}",
    "return": "{ENTER}",
    "tab": "{TAB}",
    "esc": "{ESC}",
    "escape": "{ESC}",
    "backspace": "{BACKSPACE}",
    "bspace": "{BACKSPACE}",
    "delete": "{DELETE}",
    "del": "{DELETE}",
    "space": " ",
    "spacebar": " ",
    "up": "{UP}",
    "down": "{DOWN}",
    "left": "{LEFT}",
    "right": "{RIGHT}",
    "home": "{HOME}",
    "end": "{END}",
    "pageup": "{PGUP}",
    "pagedown": "{PGDN}",
    "insert": "{INSERT}",
    "capslock": "{CAPSLOCK}",
    "numlock": "{NUMLOCK}",
    "scrolllock": "{SCROLLLOCK}",
    "printscreen": "{PRTSC}",
}

_MODIFIER_TO_SENDKEYS = {"ctrl": "^", "control": "^", "alt": "%", "shift": "+"}

_VK_MODIFIERS = {
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "shift": 0x10,
    "win": 0x5B,
    "windows": 0x5B,
    "super": 0x5B,
    "lwin": 0x5B,
    "rwin": 0x5C,
    "cmd": 0x5B,
}

_VK_KEYS = {
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "backspace": 0x08,
    "bspace": 0x08,
    "delete": 0x2E,
    "del": 0x2E,
    "space": 0x20,
    "spacebar": 0x20,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "insert": 0x2D,
    "capslock": 0x14,
    "numlock": 0x90,
    "scrolllock": 0x91,
    "printscreen": 0x2C,
    "playpause": 0xB3,
    "nexttrack": 0xB0,
    "prevtrack": 0xB1,
    "stop": 0xB2,
    "volumemute": 0xAD,
    "volumeup": 0xAF,
    "volumedown": 0xAE,
}

_VK_PUNCT = {
    ";": 0xBA,
    "=": 0xBB,
    ",": 0xBC,
    "-": 0xBD,
    ".": 0xBE,
    "/": 0xBF,
    "`": 0xC0,
    "[": 0xDB,
    "\\": 0xDC,
    "]": 0xDD,
    "'": 0xDE,
}


async def _run_ps(script: str, stdin: Optional[str] = None, timeout: float = 60) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *_PWSH,
        "-Command",
        script,
        stdin=asyncio.subprocess.PIPE if stdin is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(
        proc.communicate(input=stdin.encode("utf-8") if stdin is not None else None),
        timeout=timeout,
    )
    return proc.returncode, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")


def _ps_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _b64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


async def type_text(text: str, interval: float = 0.0) -> None:
    if interval > 0.1:
        ms = max(1, int(interval * 1000))
        script = (
            "$text = [Console]::In.ReadToEnd()\n"
            "$wshell = New-Object -ComObject WScript.Shell\n"
            "foreach ($c in $text.ToCharArray()) {\n"
            "    $s = $c.ToString()\n"
            "    if ($s -match '^[+^%~(){}]$') { $s = '{' + $s + '}' }\n"
            "    if ($s -match \"`r|`n\") { $s = '{ENTER}' }\n"
            "    $wshell.SendKeys($s)\n"
            f"    Start-Sleep -Milliseconds {ms}\n"
            "}\n"
        )
    else:
        script = (
            "$text = [Console]::In.ReadToEnd()\n"
            "$keys = $text -replace '([+^%~(){}])', '{$1}'\n"
            "$keys = $keys -replace \"`r?`n\", '{ENTER}'\n"
            "$wshell = New-Object -ComObject WScript.Shell\n"
            "$wshell.SendKeys($keys)\n"
        )
    code, _, err = await _run_ps(script, stdin=text)
    if code != 0:
        raise RuntimeError(err.strip() or f"type_text failed with exit code {code}")


def _vk_code(key: str) -> int:
    key = key.lower()
    if key in _VK_KEYS:
        return _VK_KEYS[key]
    if key in _VK_PUNCT:
        return _VK_PUNCT[key]
    if len(key) == 1:
        if key.isalpha():
            return ord(key.upper())
        if key.isdigit():
            return ord(key)
    if key.startswith("f") and key[1:].isdigit():
        n = int(key[1:])
        if 1 <= n <= 24:
            return 0x6F + n
    raise ValueError(f"Unknown key: {key}")


def _sendkeys_combo(parts: list[str]) -> str:
    main = parts[-1].lower()
    prefix = ""
    for mod in parts[:-1]:
        pm = _MODIFIER_TO_SENDKEYS.get(mod)
        if pm is None:
            raise ValueError(f"Unknown modifier: {mod}")
        prefix += pm
    if main in _SENDKEYS_KEYS:
        return prefix + _SENDKEYS_KEYS[main]
    if len(main) == 1 and main.isalpha():
        return prefix + (main.upper() if prefix else main)
    if len(main) == 1 and main.isdigit():
        return prefix + main
    if main.startswith("f") and main[1:].isdigit():
        n = int(main[1:])
        if 1 <= n <= 24:
            return prefix + f"{{F{n}}}"
    raise ValueError(f"Unknown key: {main}")


async def _keybd_event(codes: list[int]) -> None:
    nums = ",".join(str(c) for c in codes)
    script = (
        "Add-Type -Namespace W -Name K -MemberDefinition '[DllImport(\"user32.dll\")] "
        "public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, System.UIntPtr dwExtraInfo);'\n"
        f"$codes = @({nums})\n"
        "foreach ($vk in $codes) { [W.K]::keybd_event([byte]$vk, 0, 0, [System.UIntPtr]::Zero) }\n"
        "for ($i = $codes.Count - 1; $i -ge 0; $i--) { [W.K]::keybd_event([byte]$codes[$i], 0, 2, [System.UIntPtr]::Zero) }\n"
    )
    code, _, err = await _run_ps(script)
    if code != 0:
        raise RuntimeError(err.strip() or f"key event failed with exit code {code}")


async def press_key(key: str) -> None:
    parts = [p.strip().lower() for p in key.split("+") if p.strip()]
    if not parts:
        raise ValueError(f"Empty key: {key}")
    main = parts[-1]
    mods = parts[:-1]

    use_vk = any(m in _VK_MODIFIERS and m in ("win", "windows", "super", "lwin", "rwin", "cmd") for m in mods)
    use_vk = use_vk or main in _VK_KEYS and 0xA0 <= _VK_KEYS[main] <= 0xFF

    if use_vk:
        codes = []
        for mod in mods:
            vk = _VK_MODIFIERS.get(mod)
            if vk is None:
                raise ValueError(f"Unknown modifier: {mod}")
            codes.append(vk)
        codes.append(_vk_code(main))
        await _keybd_event(codes)
        return

    script = (
        "$wshell = New-Object -ComObject WScript.Shell\n"
        f"$wshell.SendKeys({_ps_str(_sendkeys_combo(parts))})\n"
    )
    code, _, err = await _run_ps(script)
    if code != 0:
        raise RuntimeError(err.strip() or f"press_key failed with exit code {code}")


async def click(x: int = -1, y: int = -1, button: str = "left", clicks: int = 1) -> None:
    if button == "right":
        down, up = 8, 16
    elif button == "middle":
        down, up = 32, 64
    else:
        down, up = 2, 4
    script = (
        "Add-Type -AssemblyName System.Windows.Forms\n"
        "Add-Type -AssemblyName System.Drawing\n"
        f"$mx = {x}\n"
        f"$my = {y}\n"
        "if ($mx -ge 0 -and $my -ge 0) { [System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point($mx, $my) }\n"
        "Add-Type -Namespace W -Name M -MemberDefinition '[DllImport(\"user32.dll\")] "
        "public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, System.UIntPtr dwExtraInfo);'\n"
        f"$down = {down}\n"
        f"$up = {up}\n"
        f"$times = {clicks}\n"
        "for ($i = 0; $i -lt $times; $i++) {\n"
        "    [W.M]::mouse_event($down, 0, 0, 0, [System.UIntPtr]::Zero)\n"
        "    [W.M]::mouse_event($up, 0, 0, 0, [System.UIntPtr]::Zero)\n"
        "    if ($i -lt $times - 1) { Start-Sleep -Milliseconds 100 }\n"
        "}\n"
    )
    code, _, err = await _run_ps(script)
    if code != 0:
        raise RuntimeError(err.strip() or f"click failed with exit code {code}")


async def screenshot(save_path: str) -> None:
    script = (
        "Add-Type -AssemblyName System.Windows.Forms\n"
        "Add-Type -AssemblyName System.Drawing\n"
        "$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds\n"
        "$bmp = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)\n"
        "$g = [System.Drawing.Graphics]::FromImage($bmp)\n"
        "$g.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)\n"
        f"$bmp.Save({_ps_str(save_path)}, [System.Drawing.Imaging.ImageFormat]::Png)\n"
        "$g.Dispose()\n"
        "$bmp.Dispose()\n"
    )
    code, _, err = await _run_ps(script)
    if code != 0:
        raise RuntimeError(err.strip() or f"screenshot failed with exit code {code}")


async def media_key(key: str) -> None:
    vk = _VK_KEYS.get(key.lower())
    if vk is None or not (0xB0 <= vk <= 0xBF):
        raise ValueError(f"Unknown media key: {key}")
    await _keybd_event([vk])


async def focus_window(title: str) -> bool:
    script = (
        "$wshell = New-Object -ComObject WScript.Shell\n"
        f"$ok = $wshell.AppActivate({_ps_str(title)})\n"
        "if ($ok) { Write-Output 'focused' } else { Write-Output 'notfound' }\n"
    )
    code, stdout, err = await _run_ps(script)
    if code != 0:
        raise RuntimeError(err.strip() or f"focus_window failed with exit code {code}")
    return stdout.strip() == "focused"


async def get_clipboard() -> str:
    code, stdout, err = await _run_ps("Get-Clipboard -Raw")
    if code != 0:
        raise RuntimeError(err.strip() or f"get_clipboard failed with exit code {code}")
    return stdout.rstrip("\r\n")


async def set_clipboard(text: str) -> None:
    script = (
        "$text = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('" + _b64(text) + "'))\n"
        "Set-Clipboard -Value $text\n"
    )
    code, _, err = await _run_ps(script)
    if code != 0:
        raise RuntimeError(err.strip() or f"set_clipboard failed with exit code {code}")
