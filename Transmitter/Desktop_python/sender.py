
"""Desktop-screen sender with both a small Windows GUI and CLI support."""

import asyncio
import contextlib
import queue
import sys
import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

from discovery import discover_receivers
from log_writer import LogWriter
from webrtc_sender import stream_desktop


class SenderApp(tk.Tk):
    """Run the async WebRTC sender without blocking the Tkinter interface."""

    def __init__(self) -> None:
        super().__init__()
        self.title("TV Desktop Sender")
        self.resizable(False, False)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[None] | None = None
        self._log_queue: queue.Queue[str] = queue.Queue()
        self._ui_queue: queue.Queue[Callable[[], None]] = queue.Queue()

        frame = ttk.Frame(self, padding=16)
        frame.grid()
        ttk.Label(frame, text="TV address").grid(row=0, column=0, sticky="w")
        self.address = tk.StringVar()
        self.address_entry = ttk.Combobox(
            frame, textvariable=self.address, width=30, values=(), state="normal"
        )
        self.address_entry.grid(row=1, column=0, pady=(4, 12), sticky="ew")
        self.address_entry.focus()
        self.discovery_button = ttk.Button(
            frame, text="Discover", command=self.discover
        )
        self.discovery_button.grid(row=1, column=1, padx=(8, 0), pady=(4, 12), sticky="ew")

        self.start_button = ttk.Button(frame, text="Start sharing", command=self.start)
        self.start_button.grid(row=2, column=0, sticky="ew")
        self.stop_button = ttk.Button(frame, text="Stop", command=self.stop, state="disabled")
        self.stop_button.grid(row=2, column=1, padx=(8, 0), sticky="ew")

        self.status = tk.StringVar(value="Ready")
        ttk.Label(frame, textvariable=self.status).grid(
            row=3, column=0, columnspan=2, pady=(12, 0), sticky="w"
        )
        ttk.Label(frame, text="Connection log").grid(
            row=4, column=0, columnspan=2, pady=(12, 4), sticky="w"
        )
        log_frame = ttk.Frame(frame)
        log_frame.grid(row=5, column=0, columnspan=2, sticky="nsew")
        self.log = tk.Text(log_frame, width=72, height=16, wrap="word", state="disabled")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(100, self._flush_log)

    def discover(self) -> None:
        """Search for compatible TV receiver endpoints without blocking the UI."""
        self.discovery_button.configure(state="disabled")
        self.start_button.configure(state="disabled")
        self.status.set("Looking for TV receivers on the local network...")
        self._append_log("Searching the local network for TV receivers...\n")
        threading.Thread(target=self._run_discovery, daemon=True).start()

    def _run_discovery(self) -> None:
        try:
            receivers = discover_receivers()
        except OSError as error:
            self._log_queue.put(f"Discovery error: {error}\n")
            self._ui_queue.put(lambda error=error: self._discovery_failed(error))
            return
        self._ui_queue.put(lambda: self._show_discovery_results(receivers))

    def _discovery_failed(self, error: OSError) -> None:
        self.discovery_button.configure(state="normal")
        self.start_button.configure(state="normal")
        self.status.set("Discovery failed")
        messagebox.showerror("Discovery failed", str(error))

    def _show_discovery_results(self, receivers: list[str]) -> None:
        self.discovery_button.configure(state="normal")
        self.start_button.configure(state="normal")
        self.address_entry.configure(values=receivers)
        if not receivers:
            self.status.set("No TV receiver found. You can still enter an address manually.")
            self._append_log("No compatible receiver found.\n")
            return

        self.address.set(receivers[0])
        self.status.set(f"Found {len(receivers)} TV receiver(s). Select one to connect.")
        self._append_log("Found: " + ", ".join(receivers) + "\n")
        self.address_entry.focus()
        self.address_entry.event_generate("<Down>")

    def start(self) -> None:
        address = self.address.get().strip()
        if not address:
            messagebox.showerror("TV address required", "Enter the TV's IP address or host name.")
            self.address_entry.focus()
            return

        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.address_entry.configure(state="disabled")
        self.discovery_button.configure(state="disabled")
        self.status.set(f"Connecting to {address}…")
        self._append_log(f"Connecting to {address}...\n")
        threading.Thread(target=self._run_sender, args=(address,), daemon=True).start()

    def _run_sender(self, address: str) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._task = loop.create_task(stream_desktop(address))
        try:
            with contextlib.redirect_stdout(LogWriter(self._log_queue)), contextlib.redirect_stderr(LogWriter(self._log_queue)):
                loop.run_until_complete(self._task)
        except asyncio.CancelledError:
            self._log_queue.put("Streaming task cancelled.\n")
        except Exception as error:
            self._log_queue.put(f"Connection error: {error}\n")
            self._ui_queue.put(
                lambda error=error: messagebox.showerror("Connection error", str(error))
            )
        finally:
            self._log_queue.put("Streaming worker stopped.\n")
            self._task = None
            self._loop = None
            loop.close()
            self._ui_queue.put(self._set_ready)

    def stop(self) -> None:
        if self._loop and self._task:
            self.status.set("Stopping…")
            self.stop_button.configure(state="disabled")
            self._append_log("Stopping sharing...\n")
            self._loop.call_soon_threadsafe(self._task.cancel)

    def _set_ready(self) -> None:
        self.address_entry.configure(state="normal")
        self.discovery_button.configure(state="normal")
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.status.set("Ready")

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _flush_log(self) -> None:
        try:
            while True:
                self._append_log(self._log_queue.get_nowait())
        except queue.Empty:
            pass
        try:
            while True:
                self._ui_queue.get_nowait()()
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(100, self._flush_log)

    def close(self) -> None:
        self.stop()
        self.destroy()


async def run_from_command_line(address: str) -> None:
    """Keep the original CLI entry point for scripted use."""
    await stream_desktop(address)


def main() -> None:
    if len(sys.argv) > 1:
        try:
            asyncio.run(run_from_command_line(sys.argv[1]))
        except KeyboardInterrupt:
            print("\nSender stopped.")
        return
    SenderApp().mainloop()


if __name__ == "__main__":
    main()
