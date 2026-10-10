import { availableEvents } from "./events.js?v=3";


export { availableEvents } from "./events.js?v=3";

export class EventQueue {
    constructor(events = availableEvents) {
        this.events = events;
    }

    add(eventName, delayMs, cyclic = false, ...args) {
        const event = this.events.get(eventName);
        if (event === undefined) {
            throw new ReferenceError(`Unknown event: ${eventName}`);
        }

        const schedule = cyclic ? setInterval : setTimeout;
        return schedule(event, delayMs, ...args);
    }
}

export const eventQueue = new EventQueue();

export function addEvent(eventName, delayMs, cyclic = false, ...args) {
    return eventQueue.add(eventName, delayMs, cyclic, ...args);
}
