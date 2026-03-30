# intelligence/guide/guide_state.py

class GuideState:
    """
    Holds GUIDE mode state.
    No logic here. Pure state.
    """

    def __init__(self):
        self.active = False
        self.topic = None
        self.step_index = 0

    def reset(self):
        self.active = False
        self.topic = None
        self.step_index = 0
