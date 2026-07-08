# domain/execution_mode.py

from enum import Enum


class ExecutionMode(Enum):
    SINGLE = "single"
    SUITE = "suite"
    REPROCESS = "reprocess"