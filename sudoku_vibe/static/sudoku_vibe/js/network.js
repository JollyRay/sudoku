import { setCellValue } from "./board.js";
import { config } from "./config.js";
import { addEvent } from "./event-queue.js";


const incomingHandlers = new Map([
    ["set_value", receiveSetValue],
    ["bonus", receiveBonus],
    ["board_data", receiveBoardData],
    ["error", receiveError],
]);

function getWebsocket() {
    const websocket = config.websocket;
    if (websocket === null || websocket.readyState !== WebSocket.OPEN) {
        throw new ReferenceError("WebSocket is not connected");
    }

    return websocket;
}

function send(kind, data = {}) {
    getWebsocket().send(JSON.stringify({ kind, data }));
}

export function requestBoardData() {
    send("get_board_data");
}

export function sendCellValue(boardName, cellIndex, value) {
    setCellValue(boardName, cellIndex, value);
    send("set_value", {
        boardName,
        cellIndex,
        value,
    });
}

export function sendContext() {
    send("set_context", config.toSendableContext());
}

export function requestBoardGeneration(difficulty, size = 9) {
    send("generate_board", { difficulty, size });
}

function receiveSetValue({ boardName, cellIndex, value }) {
    setCellValue(boardName, cellIndex, value);
}

function receiveBonus({ name, args = [], delayMs = 0, cyclic = false }) {
    addEvent(name, delayMs, cyclic, ...args);
}

function applyConfig(context) {
    if (context.username !== undefined) {
        config.setUsername(context.username);
    }
    if (context.allowedValues !== undefined) {
        config.setAllowedValues(context.allowedValues);
    }
    if (context.fieldsToSend !== undefined) {
        config.setFieldsToSend(context.fieldsToSend);
    }
}

function receiveBoardData({ board, config: receivedConfig = {} }) {
    applyConfig(receivedConfig);

    const boardName = board.name ?? config.username;
    for (const [cellIndex, value] of Object.entries(board.values ?? {})) {
        setCellValue(boardName, Number(cellIndex), value);
    }
}

function receiveError({ code, message }) {
    console.error(`WebSocket error (${String(code)}): ${String(message)}`);
}

function receiveMessage(message) {
    const envelope = JSON.parse(message.data);
    const handler = incomingHandlers.get(envelope.kind);

    if (handler === undefined) {
        console.warn(`Unknown WebSocket message: ${String(envelope.kind)}`);
        return;
    }

    handler(envelope.data ?? {});
}

function defaultWebsocketUrl() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}/ws/sudoku-vibe/`;
}

export function connectWebsocket(url = defaultWebsocketUrl()) {
    const websocket = new WebSocket(url);
    config.setWebsocket(websocket);

    websocket.addEventListener("message", receiveMessage);
    websocket.addEventListener("open", () => {
        sendContext();
        requestBoardData();
    });

    return websocket;
}
