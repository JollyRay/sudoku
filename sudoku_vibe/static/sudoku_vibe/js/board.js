import { config } from "./config.js";


const BOARD_SIDE = 9;
const BOARD_CELL_COUNT = BOARD_SIDE * BOARD_SIDE;

function getBoard(boardName) {
    const board = [...document.querySelectorAll(".sudoku-board")].find(
        (candidate) => candidate.dataset.boardName === boardName,
    );

    if (board === undefined) {
        throw new ReferenceError(`Unknown board: ${boardName}`);
    }

    return board;
}

function validateIndex(index, upperBound, indexName) {
    if (!Number.isInteger(index) || index < 0 || index >= upperBound) {
        throw new RangeError(
            `${indexName} must be an integer from 0 to ${upperBound - 1}`,
        );
    }
}

function getIndexedElement(container, selector, datasetKey, index) {
    const element = [...container.querySelectorAll(selector)].find(
        (candidate) => Number(candidate.dataset[datasetKey]) === index,
    );

    if (element === undefined) {
        throw new ReferenceError(`Element with ${datasetKey}=${index} not found`);
    }

    return element;
}

function swapElements(first, second) {
    if (first === second) {
        return;
    }
    if (first.parentNode !== second.parentNode) {
        throw new ReferenceError("Elements must have the same parent");
    }

    const parent = first.parentNode;
    const marker = document.createComment("swap");

    parent.insertBefore(marker, first);
    parent.insertBefore(first, second);
    parent.insertBefore(second, marker);
    marker.remove();
}

export function setCellValue(boardName, cellIndex, value) {
    if (!config.allowedValues.includes(value)) {
        throw new RangeError(`Board value is not allowed: ${String(value)}`);
    }
    validateIndex(cellIndex, BOARD_CELL_COUNT, "cellIndex");

    const board = getBoard(boardName);
    const cell = getIndexedElement(
        board,
        "[data-cell-index]",
        "cellIndex",
        cellIndex,
    );

    cell.textContent = String(value);
}

export function swapRows(boardName, firstRow, secondRow) {
    validateIndex(firstRow, BOARD_SIDE, "firstRow");
    validateIndex(secondRow, BOARD_SIDE, "secondRow");

    const board = getBoard(boardName);
    const first = getIndexedElement(
        board,
        "[data-row-index]",
        "rowIndex",
        firstRow,
    );
    const second = getIndexedElement(
        board,
        "[data-row-index]",
        "rowIndex",
        secondRow,
    );

    swapElements(first, second);
}

export function swapColumns(boardName, firstColumn, secondColumn) {
    validateIndex(firstColumn, BOARD_SIDE, "firstColumn");
    validateIndex(secondColumn, BOARD_SIDE, "secondColumn");

    const board = getBoard(boardName);
    const rows = board.querySelectorAll("[data-row-index]");

    for (const row of rows) {
        const first = getIndexedElement(
            row,
            "[data-column-index]",
            "columnIndex",
            firstColumn,
        );
        const second = getIndexedElement(
            row,
            "[data-column-index]",
            "columnIndex",
            secondColumn,
        );

        swapElements(first, second);
    }
}
