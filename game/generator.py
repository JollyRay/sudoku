"""Bounded, size-independent generation of uniquely solvable square Sudoku."""
from dataclasses import dataclass
from math import isfinite, isqrt
from random import Random
from time import monotonic


class GenerationBudgetExceeded(Exception):
    """The search did not prove its result within the requested budget."""


@dataclass
class GeneratedPuzzle:
    size: int
    puzzle: list[list[int]]
    solution: list[list[int]]


def block_side(size: int) -> int:
    if type(size) is not int or size < 4 or isqrt(size) ** 2 != size:
        raise ValueError('Size must be a perfect square of at least 4')
    return isqrt(size)


def generate_solution(size: int, rng: Random) -> list[list[int]]:
    base = block_side(size)

    def indices():
        groups = rng.sample(range(base), base)
        return [group * base + i for group in groups for i in rng.sample(range(base), base)]

    rows, columns = indices(), indices()
    symbols = rng.sample(range(1, size + 1), size)
    board = [[symbols[(base * (r % base) + r // base + c) % size]
              for c in columns] for r in rows]
    return [list(row) for row in zip(*board)] if rng.randrange(2) else board


def count_solutions(puzzle: list[list[int]], *, limit: int = 2,
                    node_budget: int = 100000, deadline: float | None = None) -> int:
    size = len(puzzle)
    base = block_side(size)
    if any(len(row) != size for row in puzzle):
        raise ValueError('Puzzle must be square')
    if type(limit) is not int or limit < 1 or type(node_budget) is not int or node_budget < 0:
        raise ValueError('Invalid search budget')
    rows, columns, boxes = [0] * size, [0] * size, [0] * size
    blanks = []
    for r, row in enumerate(puzzle):
        for c, value in enumerate(row):
            if type(value) is not int or not 0 <= value <= size:
                raise ValueError('Invalid cell value')
            box = r // base * base + c // base
            if value == 0:
                blanks.append((r, c, box))
                continue
            bit = 1 << (value - 1)
            if (rows[r] | columns[c] | boxes[box]) & bit:
                return 0
            rows[r] |= bit
            columns[c] |= bit
            boxes[box] |= bit
    all_bits, nodes, found = (1 << size) - 1, 0, 0

    def search(depth: int) -> None:
        nonlocal nodes, found
        if found >= limit:
            return
        if deadline is not None and monotonic() >= deadline:
            raise GenerationBudgetExceeded()
        if depth == len(blanks):
            found += 1
            return
        nodes += 1
        if nodes > node_budget:
            raise GenerationBudgetExceeded()
        best, candidates, minimum = depth, 0, size + 1
        for i in range(depth, len(blanks)):
            r, c, box = blanks[i]
            available = all_bits & ~(rows[r] | columns[c] | boxes[box])
            count = available.bit_count()
            if count == 0:
                return
            if count < minimum:
                best, candidates, minimum = i, available, count
                if count == 1:
                    break
        # When no cell is forced, row/column/box constraints can still force a
        # digit. This is essential for bounded uniqueness checks on 16x16.
        if minimum > 1:
            seen, repeated = [0] * (3 * size), [0] * (3 * size)
            options = []
            for i in range(depth, len(blanks)):
                rr, cc, bb = blanks[i]
                available = all_bits & ~(rows[rr] | columns[cc] | boxes[bb])
                options.append((i, available, (rr, size + cc, 2 * size + bb)))
                for unit in options[-1][2]:
                    repeated[unit] |= seen[unit] & available
                    seen[unit] |= available
            if any((seen[u] | used) != all_bits
                   for u, used in enumerate(rows + columns + boxes)):
                return
            forced = [seen[u] & ~repeated[u] for u in range(3 * size)]
            for i, available, units in options:
                unique = available & (forced[units[0]] | forced[units[1]] | forced[units[2]])
                if unique:
                    best, candidates = i, unique & -unique
                    break
        blanks[depth], blanks[best] = blanks[best], blanks[depth]
        r, c, box = blanks[depth]
        while candidates and found < limit:
            bit = candidates & -candidates
            candidates ^= bit
            rows[r] |= bit
            columns[c] |= bit
            boxes[box] |= bit
            search(depth + 1)
            rows[r] ^= bit
            columns[c] ^= bit
            boxes[box] ^= bit
        blanks[depth], blanks[best] = blanks[best], blanks[depth]

    search(0)
    return found


def generate_puzzle(size: int, min_empty: int, max_empty: int, rng: Random,
                    *, max_seconds: float = 30, max_attempts: int = 10) -> GeneratedPuzzle:
    block_side(size)
    if (type(min_empty) is not int or type(max_empty) is not int
            or not 1 <= min_empty <= max_empty <= size * size
            or not isfinite(max_seconds) or max_seconds <= 0
            or type(max_attempts) is not int or max_attempts < 1):
        raise ValueError('Invalid generation limits')
    deadline = monotonic() + max_seconds
    for attempt in range(max_attempts):
        now = monotonic()
        if now >= deadline:
            break
        attempt_deadline = now + (deadline - now) / (max_attempts - attempt)
        solution = generate_solution(size, rng)
        puzzle = [row[:] for row in solution]
        empty = 0
        # The highest tier has no practical upper target (an empty puzzle is
        # never unique). Stop when its requested lower bound is proven.
        target = min_empty if max_empty == size * size else (min_empty + max_empty) // 2
        indices = rng.sample(range(size * size), size * size)
        if min_empty > size * size // 2:
            # Random greedy deletion gets trapped in large minimal clue sets
            # on Latin-template 16x16 boards. Alternate stripes on the already
            # randomized solution, keeping the same uniqueness proof per clue.
            indices.sort(key=lambda i: (i % size, i // size) if attempt % 2 == 0 else (i // size, i % size))
        for index in indices:
            if monotonic() >= attempt_deadline:
                break
            r, c = divmod(index, size)
            backup, puzzle[r][c] = puzzle[r][c], 0
            try:
                unique = count_solutions(puzzle, deadline=attempt_deadline) == 1
            except GenerationBudgetExceeded:
                unique = False
            if not unique:
                puzzle[r][c] = backup
                continue
            empty += 1
            if empty >= target:
                break
        if empty >= min_empty:
            return GeneratedPuzzle(size, puzzle, solution)
    raise GenerationBudgetExceeded(f'No unique {size}x{size} puzzle with {min_empty}..{max_empty} blanks')
