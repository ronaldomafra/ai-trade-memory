"""Read one TOTP from the local desktop only after an explicit paste action."""

import asyncio
import sys

from poc.domain.primitives import DomainError

# Isolate Tk's display connection/event loop from Textual. Never output other clipboard content.
_READ_TOTP = """
import sys
try:
    import tkinter
    root = tkinter.Tk()
    root.withdraw()
except Exception:
    sys.exit(2)
try:
    text = root.clipboard_get()
    code = ''.join(text.split()) if len(text) <= 256 else ''
    if len(code) != 6 or not code.isascii() or not code.isdecimal():
        sys.exit(3)
    sys.stdout.write(code)
except Exception:
    sys.exit(2)
finally:
    root.destroy()
"""


async def read_totp_clipboard() -> str:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        _READ_TOTP,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout=2)
    except (TimeoutError, asyncio.CancelledError):
        if process.returncode is None:
            process.kill()
        await process.communicate()
        raise
    if process.returncode == 3:
        raise DomainError("Copie somente o código de seis números do autenticador e tente colar.")
    if process.returncode != 0:
        raise DomainError(
            "Área de transferência local indisponível. Use Ctrl+Shift+V no campo do código."
        )
    code = output.decode("ascii")
    if len(code) != 6 or not code.isdecimal():
        raise DomainError("Não foi recebido um código de seis números.")
    return code
