"""Writer that forwards redirected output to a thread-safe queue."""

import queue


class LogWriter:
    """Send output written by the streaming thread to the Tkinter log queue."""

    def __init__(self, output: queue.Queue[str]) -> None:
        self.output = output

    def write(self, message: str) -> int:
        if message:
            self.output.put(message)
        return len(message)

    def flush(self) -> None:
        pass