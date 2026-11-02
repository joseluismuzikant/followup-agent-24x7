from .property import Problem


class PropertiesError(Exception):
    """Base error of the properties context."""


class PropertyNotFoundError(PropertiesError):
    pass


class PropertyInvalidError(PropertiesError):
    def __init__(self, problems: list[Problem]) -> None:
        super().__init__(", ".join(problems))
        self.problems = problems


class PropertyLinkTakenError(PropertiesError):
    """Another property of the same tenant already uses this link."""


class ImportFileInvalidError(PropertiesError):
    """Not a readable CSV/XLSX, or the required columns are missing."""


class ImportTooLargeError(PropertiesError):
    """Over the size or row limit."""


class ImportNotFoundError(PropertiesError):
    pass
