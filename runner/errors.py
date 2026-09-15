class RunnerError(Exception):
    """A command failed in a way the caller should see: bad input, busy, not found.

    `status` is passed through the backend to the UI as the HTTP status.
    """

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail
