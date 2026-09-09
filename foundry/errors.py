class DomainError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422, details=None):
        super().__init__(message)
        self.code, self.message, self.status_code, self.details = code, message, status_code, details

    def as_dict(self):
        return {"code": self.code, "message": self.message, **({"details": self.details} if self.details else {})}
