from PlayerState import PlayerState


class StateObject(object):
    def __init__(self, player_state: PlayerState, _retired: bool = False):
        self.state = PlayerState(player_state)
        self.game_number = -1
        self.spectator_id = -1
        self.retired = _retired
        # ADD game fields

