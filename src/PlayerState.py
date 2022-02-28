from enum import Enum, auto


class PlayerState(Enum):
    INIT = -1

    DEFAULT = 0

    GET_STATS = 1

    ADD = 100
    ADD_HB_1 = 110
    ADD_HB_2 = 111
    ADD_HB_3 = 112
    ADD_TK_1 = 120
    ADD_TK_2 = 121
    ADD_TK_3 = 122
    ADD_CONFIRM = 199

    EDIT_CHOOSE_GAME = 200
    EDIT_GAME = 201

    GROUP_CHAT = -42

    SPECTATOR_CHOOSE_PENDING = 300
    SPECTATOR_APP_OR_REF = 301
