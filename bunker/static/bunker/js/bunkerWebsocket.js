const roomName = JSON.parse(document.getElementById('room-code').textContent);
var rowCounter = 0;
var bunkerSocket;

if (location.protocol == 'https:'){
    bunkerSocket = new WebSocket(
        'wss://'
        + window.location.host
        + '/ws/bunker/'
        + roomName
        + '/'
    );
} else {
    bunkerSocket = new WebSocket(
        'ws://'
        + window.location.host
        + '/ws/bunker/'
        + roomName
        + '/'
    );
}

bunkerSocket.onopen = function(e) {
    console.log('Bunker WebSocket connected');
    bunkerSocket.send(JSON.stringify({kind: 'board_init'}));
};

// ColumnType mapping from bunker/models.py
const columnTypeMap = {
    'living_creature': 1,
    'physique': 2,
    'trait': 3,
    'profession': 4,
    'health': 5,
    'enthusiasm': 6,
    'fear': 7,
    'inventory': 8,
    'backpack': 9,
    'additional_information': 10
};

function populateTableWithData(boardData) {
    console.log('Populating table with data:', boardData);
    
    // boardData is an array of {user_name: string, data: [{param_name: string, value: string}, ...]}
    if (!Array.isArray(boardData)) {
        console.error('board_data is not an array');
        return;
    }
    
    for (const userItem of boardData) {
        const userName = userItem.user_name;
        const parameterList = userItem.data;
        
        // Add a new row for this user
        addRow();
        
        // Get the last row that was just added
        const gameTable = document.getElementById('gameTable');
        const rows = gameTable.querySelectorAll('.data-row');
        const currentRow = rows[rows.length - 1];
        const cells = currentRow.querySelectorAll('.grid-cell');
        
        // Fill first cell with username
        cells[0].textContent = userName;
        
        // Fill parameter cells
        for (const param of parameterList) {
            const paramName = param.param_name;
            const value = param.value;
            const columnIndex = columnTypeMap[paramName];
            
            if (columnIndex !== undefined && cells[columnIndex]) {
                cells[columnIndex].textContent = value;
                console.log(`Filled column ${columnIndex} (${paramName}) with value: ${value}`);
            } else {
                console.warn(`Unknown parameter name: ${paramName}`);
            }
        }
    }
}

function addRow() {
    const gameTable = document.getElementById('gameTable');
    rowCounter++;
    
    const rowId = 'row-' + rowCounter;
    const rowDiv = document.createElement('div');
    rowDiv.className = 'data-row';
    rowDiv.id = rowId;
    rowDiv.dataset.rowIndex = rowCounter;
    
    // Create 11 cells (1 username + 10 parameters)
    for (let i = 0; i < 11; i++) {
        const cell = document.createElement('div');
        cell.className = 'grid-cell';
        cell.textContent = '';
        rowDiv.appendChild(cell);
    }
    
    gameTable.appendChild(rowDiv);
    console.log('Row added with ID: ' + rowId);
}

function removeRow(rowId) {
    const row = document.getElementById(rowId);
    if (row) {
        row.remove();
        console.log('Row removed with ID: ' + rowId);
    } else {
        console.log('Row not found with ID: ' + rowId);
    }
}

function initTableContainer() {
    const addRowBtn = document.getElementById('addRowBtn');
    const removeRowBtn = document.getElementById('removeRowBtn');
    const rowIdInput = document.getElementById('rowIdInput');
    
    if (addRowBtn) {
        addRowBtn.addEventListener('click', function() {
            addRow();
        });
    }
    
    if (removeRowBtn) {
        removeRowBtn.addEventListener('click', function() {
            const rowId = rowIdInput.value.trim();
            if (rowId) {
                removeRow(rowId);
                rowIdInput.value = '';
            } else {
                console.warn('No row ID provided');
            }
        });
    }
    
    // Allow removing row by pressing Enter in the input field
    if (rowIdInput) {
        rowIdInput.addEventListener('keypress', function(event) {
            if (event.key === 'Enter') {
                removeRowBtn.click();
            }
        });
    }
    
    console.log('Table container initialized');
}

// Initialize table on document ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTableContainer);
} else {
    initTableContainer();
}

bunkerSocket.onclose = function(e) {
    console.error('Chat socket closed unexpectedly');
};

bunkerSocket.onmessage = function(e) {
    const data = JSON.parse(e.data);
    console.log(data);

    switch (data.kind) {
        case 'first_data':
            console.log('Received first_data with size:', data.size);
            populateTableWithData(data.board_data);
            break;
        default:
            console.log('Server sent unrecognized message type');
            break;
    }
};
