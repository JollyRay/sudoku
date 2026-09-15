(function () {
    "use strict";

    /** @typedef {{row: number, column: number}} Cell */
    /** @typedef {"first-row" | "column" | "row"} SelectionAxis */
    /**
     * @typedef {Object} TargetSequence
     * @property {string[]} values
     * @property {boolean} matched
     */
    /**
     * @typedef {Object} GameState
     * @property {number} size
     * @property {TargetSequence[]} sequences
     * @property {string[][]} board
     * @property {string[]} buffer
     * @property {number} bufferCapacity
     * @property {Set<string>} selected
     * @property {SelectionAxis} nextAxis
     * @property {number} activeIndex
     * @property {number} timeLeft
     * @property {number} timeLimit
     * @property {number | null} timerId
     * @property {boolean} started
     * @property {boolean} finished
     */

    const form = /** @type {HTMLFormElement} */ (document.getElementById("game-settings"));
    const gridSizeInput = /** @type {HTMLInputElement} */ (document.getElementById("grid-size"));
    const sequenceCountInput = /** @type {HTMLInputElement} */ (document.getElementById("sequence-count"));
    const sequenceLengthInput = /** @type {HTMLInputElement} */ (document.getElementById("sequence-length"));
    const symbolCountInput = /** @type {HTMLInputElement} */ (document.getElementById("symbol-count"));
    const timeLimitInput = /** @type {HTMLInputElement} */ (document.getElementById("time-limit"));
    const matrixElement = /** @type {HTMLDivElement} */ (document.getElementById("code-matrix"));
    const sequencesElement = /** @type {HTMLOListElement} */ (document.getElementById("target-sequences"));
    const bufferElement = /** @type {HTMLOutputElement} */ (document.getElementById("buffer"));
    const timerElement = /** @type {HTMLOutputElement} */ (document.getElementById("timer"));
    const resetBufferButton = /** @type {HTMLButtonElement} */ (document.getElementById("reset-buffer"));
    const resetTimerButton = /** @type {HTMLButtonElement} */ (document.getElementById("reset-timer"));
    const newGameMobileButton = /** @type {HTMLButtonElement} */ (document.getElementById("new-game-mobile"));

    /** @type {GameState | null} */
    let state = null;
    /** @type {string | null} */
    let pinnedSymbol = null;
    /** @type {string | null} */
    let hoveredSymbol = null;

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
            /** @type {Cell[]} */
            const path = [];
            const used = new Set();
            let row = 0;
            let column = randomInt(size);

            for (let step = 0; step < length; step += 1) {
                path.push({ row, column });
                used.add(`${row}:${column}`);
                if (step === length - 1) {
                    return path;
                }

                /** @type {Cell[]} */
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
        throw new Error("Не удалось построить последовательность для выбранных параметров.");
    }

    /**
     * @param {number} count
     * @param {number} maximumLength
     * @returns {number[]}
     */
    function makeSequenceLengths(count, maximumLength) {
        const availableLengths = Array.from(
            { length: maximumLength - 1 },
            (_, index) => index + 2
        );
        const result = [];
        while (result.length < count) {
            result.push(...shuffled(availableLengths));
        }
        return result.slice(0, count);
    }

    /**
     * @param {number} size
     * @param {number} symbolCount
     * @returns {string[][]}
     */
    function buildBoard(size, symbolCount) {
        const symbols = makeSymbols(symbolCount);
        const values = [
            ...symbols,
            ...Array.from(
                { length: (size * size) - symbolCount },
                () => symbols[randomInt(symbols.length)]
            ),
        ];
        const shuffledValues = shuffled(values);
        return Array.from(
            { length: size },
            (_, row) => shuffledValues.slice(row * size, (row + 1) * size)
        );
    }

    /**
     * @param {number} size
     * @param {number} sequenceCount
     * @param {number} maximumSequenceLength
     * @param {number} symbolCount
     * @param {number} timeLimit
     * @returns {GameState}
     */
    function buildGame(size, sequenceCount, maximumSequenceLength, symbolCount, timeLimit) {
        const board = buildBoard(size, symbolCount);
        const sequenceLengths = makeSequenceLengths(sequenceCount, maximumSequenceLength);
        const sequences = sequenceLengths.map((length) => ({
            values: buildPath(size, length).map(({ row, column }) => board[row][column]),
            matched: false,
        }));

        return {
            size,
            sequences,
            board,
            buffer: [],
            bufferCapacity: maximumSequenceLength,
            selected: new Set(),
            nextAxis: "first-row",
            activeIndex: 0,
            timeLeft: timeLimit,
            timeLimit,
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
        if (
            !state
            || state.finished
            || state.buffer.length >= state.bufferCapacity
            || state.selected.has(`${row}:${column}`)
        ) {
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

    /**
     * @param {string[]} sequence
     * @returns {boolean}
     */
    function bufferContains(sequence) {
        if (!state || state.buffer.length < sequence.length) {
            return false;
        }
        return state.buffer.some((_, start) =>
            sequence.every((symbol, offset) => state.buffer[start + offset] === symbol)
        );
    }

    /** @returns {void} */
    function stopTimer() {
        if (state && state.timerId !== null) {
            window.clearInterval(state.timerId);
            state.timerId = null;
        }
    }

    /** @returns {void} */
    function updateTimer() {
        if (!state) {
            timerElement.value = "—";
            timerElement.textContent = "—";
            return;
        }
        timerElement.value = `${state.timeLeft} с`;
        timerElement.textContent = `${state.timeLeft} с`;
    }

    /** @returns {void} */
    function updateBuffer() {
        if (!state) {
            bufferElement.value = "—";
            bufferElement.textContent = "—";
            return;
        }
        const values = state.buffer.length > 0 ? state.buffer.join(" ") : "—";
        const rendered = `${values} (${state.buffer.length}/${state.bufferCapacity})`;
        bufferElement.value = rendered;
        bufferElement.textContent = rendered;
    }

    /** @returns {void} */
    function updateSymbolHighlights() {
        const activeSymbol = hoveredSymbol ?? pinnedSymbol;
        matrixElement.querySelectorAll("button[data-symbol]").forEach((button) => {
            const isHighlighted = activeSymbol !== null && button.getAttribute("data-symbol") === activeSymbol;
            button.classList.toggle("symbol-highlight", isHighlighted);
        });
        sequencesElement.querySelectorAll("button[data-symbol]").forEach((button) => {
            button.setAttribute(
                "aria-pressed",
                String(pinnedSymbol !== null && button.getAttribute("data-symbol") === pinnedSymbol)
            );
        });
    }

    /**
     * @param {string | null} symbol
     * @returns {void}
     */
    function setHoveredSymbol(symbol) {
        hoveredSymbol = symbol;
        updateSymbolHighlights();
    }

    /**
     * @param {string} symbol
     * @param {MouseEvent} event
     * @returns {void}
     */
    function togglePinnedSymbol(symbol, event) {
        event.stopPropagation();
        pinnedSymbol = pinnedSymbol === symbol ? null : symbol;
        updateSymbolHighlights();
    }

    /** @returns {void} */
    function renderSequences() {
        sequencesElement.replaceChildren();
        if (!state) {
            return;
        }
        state.sequences.forEach((sequence) => {
            const item = document.createElement("li");
            const container = document.createElement(sequence.matched ? "mark" : "span");
            sequence.values.forEach((symbol, index) => {
                const button = document.createElement("button");
                button.type = "button";
                button.className = "sequence-symbol";
                button.textContent = symbol;
                button.setAttribute("data-symbol", symbol);
                button.setAttribute("aria-label", `Подсветить символ ${symbol} в матрице`);
                button.setAttribute("aria-pressed", String(pinnedSymbol === symbol));
                button.addEventListener("mouseenter", () => setHoveredSymbol(symbol));
                button.addEventListener("mouseleave", () => setHoveredSymbol(null));
                button.addEventListener("focus", () => setHoveredSymbol(symbol));
                button.addEventListener("blur", () => setHoveredSymbol(null));
                button.addEventListener("click", (event) => togglePinnedSymbol(symbol, event));
                container.appendChild(button);
                if (index < sequence.values.length - 1) {
                    container.appendChild(document.createTextNode(" "));
                }
            });
            item.appendChild(container);
            sequencesElement.appendChild(item);
        });
        updateSymbolHighlights();
    }

    /** @returns {void} */
    function finishBuffer() {
        if (!state) {
            return;
        }
        state.finished = true;
        stopTimer();
        state.sequences.forEach((sequence) => {
            sequence.matched = bufferContains(sequence.values);
        });
        renderSequences();
        renderMatrix();
    }

    /** @returns {void} */
    function startTimer() {
        if (!state || state.timerId !== null || state.timeLeft <= 0) {
            return;
        }
        state.started = true;
        state.timerId = window.setInterval(() => {
            if (!state) {
                return;
            }
            state.timeLeft -= 1;
            updateTimer();
            if (state.timeLeft <= 0) {
                state.finished = true;
                stopTimer();
                renderMatrix();
            }
        }, 1000);
    }

    /**
     * @param {number} row
     * @param {number} column
     * @returns {void}
     */
    function selectCell(row, column) {
        if (!state || !isAllowed(row, column)) {
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

        updateBuffer();
        if (state.buffer.length >= state.bufferCapacity) {
            finishBuffer();
            return;
        }

        renderMatrix();
        if (!matrixElement.querySelector("button:not(:disabled)")) {
            finishBuffer();
        }
    }

    /** @returns {void} */
    function renderMatrix() {
        matrixElement.replaceChildren();
        if (!state) {
            return;
        }
        matrixElement.style.setProperty("--grid-size", String(state.size));
        const table = document.createElement("table");
        const body = document.createElement("tbody");
        for (let row = 0; row < state.size; row += 1) {
            const tableRow = document.createElement("tr");
            for (let column = 0; column < state.size; column += 1) {
                const cell = document.createElement("td");
                const button = document.createElement("button");
                button.type = "button";
                button.textContent = state.board[row][column];
                button.setAttribute("data-symbol", state.board[row][column]);
                button.disabled = !isAllowed(row, column);
                button.setAttribute(
                    "aria-label",
                    `Строка ${row + 1}, столбец ${column + 1}: ${state.board[row][column]}`
                );
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
        updateSymbolHighlights();
    }

    /** @returns {void} */
    function resetBuffer() {
        if (!state) {
            return;
        }
        state.buffer = [];
        state.selected.clear();
        state.nextAxis = "first-row";
        state.activeIndex = 0;
        state.sequences.forEach((sequence) => {
            sequence.matched = false;
        });
        state.finished = state.timeLeft <= 0;
        updateBuffer();
        renderSequences();
        renderMatrix();

        if (!state.finished && state.started) {
            startTimer();
        }
    }

    /** @returns {void} */
    function resetTimer() {
        if (!state || !timeLimitInput.reportValidity()) {
            return;
        }
        stopTimer();
        state.timeLimit = Number(timeLimitInput.value);
        state.timeLeft = state.timeLimit;
        state.started = false;
        state.finished = state.buffer.length >= state.bufferCapacity;
        updateTimer();
        renderMatrix();
    }

    /** @returns {void} */
    function syncDynamicLimits() {
        const gridSize = Number(gridSizeInput.value);
        if (!Number.isInteger(gridSize) || gridSize < 3 || gridSize > 10) {
            return;
        }

        const cellCount = gridSize ** 2;
        symbolCountInput.max = String(cellCount);
        if (Number(symbolCountInput.value) > cellCount) {
            symbolCountInput.value = String(cellCount);
        }

        const maximumSequenceLength = Math.min(8, Math.floor(cellCount / 2));
        sequenceLengthInput.max = String(maximumSequenceLength);
        if (Number(sequenceLengthInput.value) > maximumSequenceLength) {
            sequenceLengthInput.value = String(maximumSequenceLength);
        }
    }

    /** @returns {void} */
    function generateGame() {
        syncDynamicLimits();
        if (!form.reportValidity()) {
            return;
        }

        stopTimer();
        pinnedSymbol = null;
        hoveredSymbol = null;
        state = buildGame(
            Number(gridSizeInput.value),
            Number(sequenceCountInput.value),
            Number(sequenceLengthInput.value),
            Number(symbolCountInput.value),
            Number(timeLimitInput.value)
        );
        resetBufferButton.disabled = false;
        resetTimerButton.disabled = false;
        updateTimer();
        updateBuffer();
        renderSequences();
        renderMatrix();
    }

    gridSizeInput.addEventListener("input", syncDynamicLimits);
    resetBufferButton.addEventListener("click", resetBuffer);
    resetTimerButton.addEventListener("click", resetTimer);
    newGameMobileButton.addEventListener("click", generateGame);
    document.addEventListener("click", () => {
        pinnedSymbol = null;
        hoveredSymbol = null;
        updateSymbolHighlights();
    });
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        generateGame();
    });

    syncDynamicLimits();
    generateGame();
}());
