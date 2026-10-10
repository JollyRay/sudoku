import { config } from "./config.js";
import { connectWebsocket } from "./network.js";

const board = document.querySelector(".sudoku-board");

config.setUsername(board?.dataset.boardName ?? "undefined");
connectWebsocket();

export { config } from "./config.js";
export {
    ensureBoard,
    setCellValue,
    setFixedCells,
    swapColumns,
    swapRows,
} from "./board.js";
export {
    EventQueue,
    addEvent,
    availableEvents,
    eventQueue,
} from "./event-queue.js";
export {
    connectWebsocket,
    requestBoardData,
    requestBoardGeneration,
    sendCellValue,
    sendContext,
} from "./network.js";
