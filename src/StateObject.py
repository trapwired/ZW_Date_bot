from PlayerState import PlayerState


class StateObject(object):
    def __init__(self, player_state: PlayerState):
        self.state = PlayerState(player_state)
        self.game_number = -1
        # ADD game fields
        # ADD TK fields

