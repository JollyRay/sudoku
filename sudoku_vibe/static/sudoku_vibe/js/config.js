export const EMPTY_BOARD_VALUE = "";

export const DEFAULT_ALLOWED_VALUES = Object.freeze([
    EMPTY_BOARD_VALUE,
    0,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
]);

export const DEFAULT_FIELDS_TO_SEND = Object.freeze([
    "username",
    "allowedValues",
]);

const SENDABLE_FIELDS = new Set(DEFAULT_FIELDS_TO_SEND);

function copyUniqueValues(values, fieldName) {
    if (!Array.isArray(values)) {
        throw new TypeError(`${fieldName} must be an array`);
    }

    return Object.freeze([...new Set(values)]);
}

export class SudokuConfig {
    constructor({
        websocket = null,
        username = "undefined",
        allowedValues = DEFAULT_ALLOWED_VALUES,
        fieldsToSend = DEFAULT_FIELDS_TO_SEND,
    } = {}) {
        this.websocket = websocket;
        this.setUsername(username);
        this.setAllowedValues(allowedValues);
        this.setFieldsToSend(fieldsToSend);
    }

    setWebsocket(websocket) {
        this.websocket = websocket;
    }

    setUsername(username) {
        if (typeof username !== "string") {
            throw new TypeError("username must be a string");
        }

        this.username = username || "undefined";
    }

    setAllowedValues(values) {
        this.allowedValues = copyUniqueValues(values, "allowedValues");
    }

    setFieldsToSend(fields) {
        const uniqueFields = copyUniqueValues(fields, "fieldsToSend");
        const unsupportedField = uniqueFields.find(
            (field) => !SENDABLE_FIELDS.has(field),
        );

        if (unsupportedField !== undefined) {
            throw new RangeError(
                `Config field cannot be sent: ${String(unsupportedField)}`,
            );
        }

        this.fieldsToSend = uniqueFields;
    }

    toSendableContext() {
        return Object.fromEntries(
            this.fieldsToSend.map((field) => {
                const value = this[field];
                return [field, Array.isArray(value) ? [...value] : value];
            }),
        );
    }
}

export const config = new SudokuConfig();
