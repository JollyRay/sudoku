import hashlib
from channels.layers import get_channel_layer


def room_group_name(lobby: str) -> str:
    return 'sudoku_v2_' + hashlib.sha256(lobby.encode()).hexdigest()


async def publish_bonus(lobby: str, data: dict, *, channel_layer=None) -> None:
    layer = channel_layer or get_channel_layer()
    await layer.group_send(room_group_name(lobby), {
        'type': 'forward_message', 'message': {'kind': 'bonus_applied', 'data': data},
    })
