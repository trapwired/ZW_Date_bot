from enum import Enum


class SpectatorState(Enum):
    REFUSED = -999

    AWAIT_APPROVE = -1

    DEFAULT = 0

    CHOOSE_GAME = 10
