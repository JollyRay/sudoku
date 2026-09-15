(function () {
    "use strict";

    /** @typedef {{row: number, column: number}} Cell */
    /** @typedef {"first-row" | "column" | "row"} SelectionAxis */
    /**
     * @typedef {Object} GameState
     * @property {number} size
     * @property {string[]} target
     * @property {string[][]} board
     * @property {string[]} buffer
     * @property {Set<string>} selected
     * @property {SelectionAxis} nextAxis
     * @property {number} activeIndex
     * @property {number} timeLeft
     * @property {number | null} timerId
     * @property {boolean} started
     * @property {boolean} finished
     */

    const form = /** @type {HTMLFormElement} */ (document.getElementById("game-settings"));
    const gridSizeInput = /** @type {HTMLInputElement} */ (document.getElementById("grid-size"));
    const sequenceLengthInput = /** @type {HTMLInputElement} */ (document.getElementById("sequence-length"));
    const symbolCountInput = /** @type {HTMLInputElement} */ (document.getElementById("symbol-count"));
    const timeLimitInput = /** @type {HTMLInputElement} */ (document.getElementById("time-limit"));
    const matrixElement = /** @type {HTMLDivElement} */ (document.getElementById("code-matrix"));
    const targetElement = /** @type {HTMLOutputElement} */ (document.getElementById("target-sequence"));
    const bufferElement = /** @type {HTMLOutputElement} */ (document.getElementById("buffer"));
    const timerElement = /** @type {HTMLOutputElement} */ (document.getElementById("timer"));
    const statusElement = /** @type {HTMLParagraphElement} */ (document.getElementById("status"));

    /** @type {GameState | null} */
    let state = null;

    /**
     * @param {number} maximum
     * @returns {number}
     */
    function randomInt(maximum) {
        return Math.floor(Math.random() * maximum);
    }

    /**
     * @template T
     * @param {T[]} values
     * @returns {T[]}
     */
    function shuffled(values) {
        const result = [...values];
        for (let index = result.length - 1; index > 0; index -= 1) {
            const swapIndex = randomInt(index + 1);
            [result[index], result[swapIndex]] = [result[swapIndex], result[index]];
        }
        return result;
    }

    /**
     * @param {number} count
     * @returns {string[]}
     */
    function makeSymbols(count) {
        return shuffled(
            Array.from({ length: 256 }, (_, index) => index.toString(16).toUpperCase().padStart(2, "0"))
        ).slice(0, count);
    }

    /**
     * @param {number} size
     * @param {number} length
     * @returns {Cell[]}
     */
    function buildPath(size, length) {
        for (let attempt = 0; attempt < 500; attempt += 1) {
            const path = [];
            const used = new Set();
            let row = 0;
            let column = randomInt(size);

            for (let step = 0; step < length; step += 1) {
                const key = `${row}:${column}`;
                path.push({ row, column });
                used.add(key);

                if (step === length - 1) {
                    return path;
                }

                const candidates = [];
                if (step % 2 === 0) {
                    for (let nextRow = 0; nextRow < size; nextRow += 1) {
                        if (!used.has(`${nextRow}:${column}`)) {
                            candidates.push({ row: nextRow, column });
                        }
                    }
                } else {
                    for (let nextColumn = 0; nextColumn < size; nextColumn += 1) {
                        if (!used.has(`${row}:${nextColumn}`)) {
                            candidates.push({ row, column: nextColumn });
                        }
                    }
                }

                if (candidates.length === 0) {
                    break;
                }
                ({ row, column } = candidates[randomInt(candidates.length)]);
            }
        }
        throw new Error("Не удалось построить маршрут для выбранных параметров.");
    }

    /**
     * @param {number} size
     * @param {number} sequenceLength
     * @param {number} symbolCount
     * @param {number} timeLimit
     * @returns {GameState}
     */
    function buildGame(size, sequenceLength, symbolCount, timeLimit) {
        const symbols = makeSymbols(symbolCount);
        const path = buildPath(size, sequenceLength);
        const distinctTargetSymbols = shuffled(symbols).slice(0, Math.min(symbolCount, sequenceLength));
        const target = [...distinctTargetSymbols];

        while (target.length < sequenceLength) {
            target.push(symbols[randomInt(symbols.length)]);
        }
        const orderedTarget = shuffled(target);
        const pathKeys = new Set(path.map(({ row, column }) => `${row}:${column}`));
        const remainingSymbols = symbols.filter((symbol) => !orderedTarget.includes(symbol));
        const spareValues = [
            ...remainingSymbols,
            ...Array.from(
                { length: (size * size) - sequenceLength - remainingSymbols.length },
                () => symbols[randomInt(symbols.length)]
            ),
        ];
        const shuffledSpareValues = shuffled(spareValues);
        const board = Array.from({ length: size }, () => Array(size));
        let spareIndex = 0;

        for (let row = 0; row < size; row += 1) {
            for (let column = 0; column < size; column += 1) {
                if (!pathKeys.has(`${row}:${column}`)) {
                    board[row][column] = shuffledSpareValues[spareIndex];
                    spareIndex += 1;
                }
            }
        }
        path.forEach(({ row, column }, index) => {
            board[row][column] = orderedTarget[index];
        });

        return {
            size,
            target: orderedTarget,
            board,
            buffer: [],
            selected: new Set(),
            nextAxis: "first-row",
            activeIndex: 0,
            timeLeft: timeLimit,
            timerId: null,
            started: false,
            finished: false,
        };
    }

    /**
     * @param {number} row
     * @param {number} column
     * @returns {boolean}
     */
    function isAllowed(row, column) {
        if (!state || state.finished || state.selected.has(`${row}:${column}`)) {
            return false;
        }
        if (state.nextAxis === "first-row") {
            return row === 0;
        }
        if (state.nextAxis === "column") {
            return column === state.activeIndex;
        }
        return row === state.activeIndex;
    }

    /** @returns {boolean} */
    function containsTarget() {
        const target = state.target;
        if (state.buffer.length < target.length) {
            return false;
        }
        return state.buffer.some((_, start) =>
            target.every((symbol, offset) => state.buffer[start + offset] === symbol)
        );
    }

    /**
     * @param {string} message
     * @returns {void}
     */
    function finish(message) {
        state.finished = true;
        if (state.timerId !== null) {
            window.clearInterval(state.timerId);
            state.timerId = null;
        }
        statusElement.textContent = message;
        renderMatrix();
    }

    /** @returns {void} */
    function updateTimer() {
        timerElement.value = `${state.timeLeft} с`;
        timerElement.textContent = `${state.timeLeft} с`;
    }

    /** @returns {void} */
    function startTimer() {
        state.started = true;
        state.timerId = window.setInterval(() => {
            state.timeLeft -= 1;
            updateTimer();
            if (state.timeLeft <= 0) {
                finish("Время вышло. Выбор ячеек заблокирован.");
            }
        }, 1000);
    }

    /**
     * @param {number} row
     * @param {number} column
     * @returns {void}
     */
    function selectCell(row, column) {
        if (!isAllowed(row, column)) {
            return;
        }
        if (!state.started) {
            startTimer();
        }

        state.selected.add(`${row}:${column}`);
        state.buffer.push(state.board[row][column]);

        if (state.nextAxis === "first-row" || state.nextAxis === "row") {
            state.nextAxis = "column";
            state.activeIndex = column;
        } else {
            state.nextAxis = "row";
            state.activeIndex = row;
        }

        bufferElement.value = state.buffer.join(" ");
        bufferElement.textContent = state.buffer.join(" ");

        if (containsTarget()) {
            finish("Последовательность загружена. Взлом выполнен.");
            return;
        }

        renderMatrix();
        if (!matrixElement.querySelector("button:not(:disabled)")) {
            finish("Доступных ходов не осталось. Сгенерируйте новое поле.");
        }
    }

    /** @returns {void} */
    function renderMatrix() {
        matrixElement.replaceChildren();
        if (!state) {
            return;
        }

        const table = document.createElement("table");
        const body = document.createElement("tbody");
        for (let row = 0; row < state.size; row += 1) {
            const tableRow = document.createElement("tr");
            for (let column = 0; column < state.size; column += 1) {
                const cell = document.createElement("td");
                const button = document.createElement("button");
                button.type = "button";
                button.textContent = state.board[row][column];
                button.disabled = !isAllowed(row, column);
                button.setAttribute("aria-label", `Строка ${row + 1}, столбец ${column + 1}: ${state.board[row][column]}`);
                if (state.selected.has(`${row}:${column}`)) {
                    button.setAttribute("aria-pressed", "true");
                }
                button.addEventListener("click", () => selectCell(row, column));
                cell.appendChild(button);
                tableRow.appendChild(cell);
            }
            body.appendChild(tableRow);
        }
        table.appendChild(body);
        matrixElement.appendChild(table);
    }

    /** @returns {void} */
    function syncSymbolMaximum() {
        const cellCount = Number(gridSizeInput.value) ** 2;
        symbolCountInput.max = String(cellCount);
        if (Number(symbolCountInput.value) > cellCount) {
            symbolCountInput.value = String(cellCount);
        }
    }

    gridSizeInput.addEventListener("input", syncSymbolMaximum);
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        syncSymbolMaximum();
        if (!form.reportValidity()) {
            return;
        }

        if (state && state.timerId !== null) {
            window.clearInterval(state.timerId);
        }
        state = buildGame(
            Number(gridSizeInput.value),
            Number(sequenceLengthInput.value),
            Number(symbolCountInput.value),
            Number(timeLimitInput.value)
        );
        targetElement.value = state.target.join(" ");
        targetElement.textContent = state.target.join(" ");
        bufferElement.value = "—";
        bufferElement.textContent = "—";
        statusElement.textContent = "Поле готово. Выберите ячейку в верхней строке.";
        updateTimer();
        renderMatrix();
    });

    syncSymbolMaximum();
}());
