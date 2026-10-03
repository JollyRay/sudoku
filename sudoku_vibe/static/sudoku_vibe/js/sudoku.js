import { config } from "./config.js";

const board = document.querySelector(".sudoku-board");

config.setUsername(board?.dataset.boardName ?? "undefined");

export { config } from "./config.js";
export {
    EventQueue,
    addEvent,
    availableEvents,
    eventQueue,
} from "./event-queue.js";
