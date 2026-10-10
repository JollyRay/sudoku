import { config } from "./config.js?v=3";
import { connectWebsocket } from "./network.js?v=3";

const board = document.querySelector(".sudoku-board");

config.setUsername(board?.dataset.boardName ?? "undefined");
connectWebsocket();

export { config } from "./config.js?v=3";
export {
    ensureBoard,
    setCellValue,
    setFixedCells,
    swapColumns,
    swapRows,
} from "./board.js?v=3";
export {
    EventQueue,
    addEvent,
    availableEvents,
    eventQueue,
} from "./event-queue.js?v=3";
export {
    connectWebsocket,
    requestBoardData,
    requestBoardGeneration,
    sendCellValue,
    sendContext,
} from "./network.js?v=3";
