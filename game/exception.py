from abc import ABC, abstractmethod

class SudokuException(Exception, ABC):
    @property
    @abstractmethod
    def MESSAGE(self): ...
    
    def __init__(self, code_room, nick) -> None:
        message = self.MESSAGE % (nick, code_room)
        super().__init__(message)

class UserDisconnect(SudokuException):
    MESSAGE = 'User "%s" not exist in room "%s"'

class BoardNotReqest(SudokuException):
    MESSAGE = 'User "%s" from "%s" room does not have board'