"""Pure bonus rules; all coordinates refer to display positions."""
from copy import deepcopy
from dataclasses import dataclass
from math import isqrt
from random import Random
from .constants import BONUS_DEFINITIONS, EFFECT_DEFAULTS
from .storage import StoredBoard


@dataclass(frozen=True)
class BonusRequest:
    kind: str
    target_names: list[str]
    params: dict


def normalize_bonus_params(kind: str, raw: dict, sizes: list[int], rng: Random) -> dict:
    if kind not in {item[0] for item in BONUS_DEFINITIONS} or not sizes:
        raise ValueError('Unknown bonus or empty target set')
    if kind == 'SWAP':
        pairs = [(a, b) for a in range(min(sizes)) for b in range(a+1, min(sizes))
                 if all(a//isqrt(size) == b//isqrt(size) for size in sizes)]
        first, second = raw.get('first'), raw.get('second')
        if type(first) is not int or type(second) is not int or tuple(sorted((first, second))) not in pairs:
            first, second = rng.choice(pairs)
        axis = raw.get('axis')
        return {'axis': axis if axis in ('row', 'col') else rng.choice(('row', 'col')), 'first': first, 'second': second}
    box = raw.get('box')
    return {**EFFECT_DEFAULTS[kind], 'box': box if type(box) is int and 0 <= box < min(sizes) else rng.randrange(min(sizes))}


def apply_bonus(board: StoredBoard, kind: str, params: dict, *, effect_id: str,
                now_ms: int, duration_ms: int) -> StoredBoard:
    updated = deepcopy(board)
    public = updated['public']
    public['activeEffects'] = [e for e in public.get('activeEffects', []) if e['expiresAt'] > now_ms]
    if kind == 'SWAP':
        key = 'rowOrder' if params['axis'] == 'row' else 'columnOrder'
        order = public.setdefault(key, list(range(public['size'])))
        a, b = params['first'], params['second']
        order[a], order[b] = order[b], order[a]
    else:
        public['activeEffects'].append({'id': effect_id, 'kind': kind, 'params': deepcopy(params),
                                        'startsAt': now_ms, 'expiresAt': now_ms + duration_ms})
    public['revision'] += 1
    return updated
