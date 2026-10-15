import asyncio

import pytest

from poc.adapters.outbound import clipboard
from poc.domain.primitives import DomainError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exit_code,output,expected",
    [(0, b"001234", "001234"), (3, b"", "seis números"), (2, b"", "indisponível")],
)
async def test_local_clipboard_preserves_zeros_and_sanitizes_errors(
    monkeypatch, exit_code, output, expected
):
    class Process:
        returncode = exit_code

        async def communicate(self):
            return output, None

    async def create_process(*args, **kwargs):
        assert args[0] == clipboard.sys.executable and args[1] == "-c"
        assert kwargs["stderr"] == asyncio.subprocess.DEVNULL
        return Process()

    monkeypatch.setattr(clipboard.asyncio, "create_subprocess_exec", create_process)
    if exit_code == 0:
        assert await clipboard.read_totp_clipboard() == expected
    else:
        with pytest.raises(DomainError, match=expected):
            await clipboard.read_totp_clipboard()


@pytest.mark.asyncio
async def test_cancel_clipboard_read_terminates_child(monkeypatch):
    started = asyncio.Event()

    class Process:
        returncode = None
        killed = False

        async def communicate(self):
            if self.killed:
                return b"", None
            started.set()
            await asyncio.Event().wait()

        def kill(self):
            self.killed = True
            self.returncode = -9

    process = Process()

    async def create_process(*args, **kwargs):
        return process

    monkeypatch.setattr(clipboard.asyncio, "create_subprocess_exec", create_process)
    task = asyncio.create_task(clipboard.read_totp_clipboard())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.killed
