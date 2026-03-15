const roomName = JSON.parse(document.getElementById('room-code').textContent);
const currentNick = document.cookie.split("; ").find((row) => row.startsWith("nick="))?.split("=")[1];

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
    // Request board data on connection
    bunkerSocket.send(JSON.stringify({
        kind: 'get_board_data'
    }));
};

bunkerSocket.onmessage = function(e) {
    const data = JSON.parse(e.data);
    console.log(data);

    switch (data.kind) {
        case 'set_board_data':
            handleSetBoardData(data);
            break;
        case 'board_init':
            handleBoardInit(data);
            break;
        case 'set_param_value':
            handleSetParamValue(data);
            break;
        case 'open_param':
            handleOpenParam(data);
            break;
        default:
            console.log('Server sent unrecognized message type ' + data.kind);
            break;
    }
};

// Fixed column order matching the HTML header
const columnNames = [
    'living_creature',
    'physique',
    'trait',
    'profession',
    'health',
    'enthusiasm',
    'fear',
    'inventory',
    'backpack',
    'additional_information'
];

function handleSetBoardData(data) {
    const { is_host, self_data, board_data, members } = data;
    const adminMenu = document.getElementById('adminMenu');
    adminMenu.style.display = is_host ? 'block' : 'none';
    updateBoardState(members, self_data, board_data);
}

function handleSetParamValue(data) {
    const { updates } = data;
    
    if (updates && Array.isArray(updates)) {
        updates.forEach(update => {
            const { member, param_name, new_value } = update;
            
            // Update game table
            updateGameTableCell(member, param_name, new_value);
            
            // Update personal table if this is the current user
            if (member === currentNick) {
                updatePersonalTableCell(param_name, new_value);
            }
        });
    }
}

function updateBoardState(members, selfData, boardData = null) {
    populatePersonalTable(selfData);
    populateMemberDropdowns(members); // Update admin dropdowns
    populateGameTable(members, boardData);
}

function populatePersonalTable(selfData) {
    const personalTable = document.getElementById('personalTable');
    
    // Remove all rows except the header
    const rows = personalTable.querySelectorAll('.grid-row');
    rows.forEach((row, index) => {
        if (index > 0) {
            row.remove();
        }
    });
    
    // Add rows for each attribute
    if (selfData && Array.isArray(selfData)) {
        selfData.forEach(item => {
            const row = document.createElement('div');
            row.classList.add('grid-row');
            const paramName = item.param_name || '';
            row.setAttribute('data-param', paramName);
            
            const paramNameCell = document.createElement('div');
            paramNameCell.classList.add('grid-cell');
            paramNameCell.textContent = paramName;
            
            const value = document.createElement('div');
            value.classList.add('grid-cell');
            value.textContent = item.value || '';
            
            const buttonCell = document.createElement('div');
            buttonCell.classList.add('grid-cell');
            const button = document.createElement('button');
            button.classList.add('btn-toggle-param');
            button.textContent = item.is_open ? 'Close' : 'Open';
            button.setAttribute('data-param', paramName);
            button.addEventListener('click', function() {
                console.log('Toggle button clicked for param:', this.getAttribute('data-param'));
                sendOpenParamRequest(this.getAttribute('data-param'));
            });
            buttonCell.appendChild(button);
            
            row.appendChild(paramNameCell);
            row.appendChild(value);
            row.appendChild(buttonCell);
            personalTable.appendChild(row);
        });
    }
}

function populateGameTable(members, boardData = null) {
    clearGameTable();
    
    if (members && Array.isArray(members)) {
        members.forEach(member => createMemberRow(member, boardData ? boardData[member] : null));
    }
}

function handleBoardInit(data) {
    const { members, self_data } = data;
    updateBoardState(members, self_data);
    console.log('Board initialized with', members.length, 'members');
}

function clearGameTable() {
    const gameTable = document.getElementById('gameTable');
    
    // Remove all rows except the header
    const rows = gameTable.querySelectorAll('.grid-row');
    rows.forEach((row, index) => {
        if (index > 0) {
            row.remove();
        }
    });
}

function getSelfParamValue(paramName) {
    const personalTable = document.getElementById('personalTable');
    const paramCell = personalTable.querySelector(`.grid-row[data-param="${paramName}"] .grid-cell:nth-child(2)`);
    return paramCell ? paramCell.textContent : null;
}

function createMemberRow(memberName, initialData = null) {
    const gameTable = document.getElementById('gameTable');
    const row = document.createElement('div');
    row.classList.add('grid-row');
    row.setAttribute('data-member', memberName);
    
    // Username column (filled)
    const usernameCell = document.createElement('div');
    usernameCell.classList.add('grid-cell');
    usernameCell.textContent = memberName;
    row.appendChild(usernameCell);
    parameterMap = {};
    if (initialData && Array.isArray(initialData)) {
        initialData.forEach(param => {
            parameterMap[param.param_name] = param.value;
        });
    }
    columnNames.forEach(param => {
        const currentCell = document.createElement('div');
        currentCell.classList.add('grid-cell');
        currentCell.setAttribute('data-param', param);
        currentCell.textContent = parameterMap[param] || '';
        row.appendChild(currentCell);
    });
    
    gameTable.appendChild(row);
}

function updateGameTableCell(member, paramName, newValue) {
    const gameTable = document.getElementById('gameTable');

    const memberCell = gameTable.querySelector(`.grid-row[data-member="${member}"] .grid-cell[data-param="${paramName}"]`);
    if (memberCell == null) {
        console.warn('Cell not found for member:', member, 'param:', paramName);
        return;
    }
    memberCell.textContent = newValue;
}

function updatePersonalTableCell(paramName, newValue) {
    const personalTable = document.getElementById('personalTable');
    const paramCell = personalTable.querySelector(`.grid-row[data-param="${paramName}"] .grid-cell:nth-child(2)`);
    if (paramCell) {
        paramCell.textContent = newValue;
        return;
    }
    console.warn('Parameter not found in personal table:', paramName);
}

function sendOpenParamRequest(paramName) {
    bunkerSocket.send(JSON.stringify({
        kind: 'open_param',
        param_name: paramName
    }));
}

function handleOpenParam(data) {
    const { param_name, is_open } = data;
    const button = document.querySelector(`#personalTable div[data-param="${param_name}"] button`);
    
    if (!button) {
        console.warn('Button not found for param:', param_name);
        return;
    }
    
    // Update button text and state
    button.textContent = is_open ? 'Close' : 'Open';
    button.setAttribute('data-is-open', is_open ? 'true' : 'false');
    
    if (is_open) {
        const paramValue = getSelfParamValue(param_name);
        updateGameTableCell(currentNick, param_name, paramValue);
    } else {
        updateGameTableCell(currentNick, param_name, '');
    }
}

function populateMemberDropdowns(members) {
    if (!Array.isArray(members)) return;

    const member1Select = document.getElementById('swapMember1');
    const member2Select = document.getElementById('swapMember2');
    const stealFromSelect = document.getElementById('stealFromMember');
    const stealToSelect = document.getElementById('stealToMember');
    const setMemberSelect = document.getElementById('setMember');    

    updateDropdown(member1Select, members);
    updateDropdown(member2Select, members);
    updateDropdown(stealFromSelect, members);
    updateDropdown(stealToSelect, members);
    updateDropdown(setMemberSelect, members);
}

function updateDropdown(dropdown, params) {
    if (!dropdown) return;

    // Clear existing options
    dropdown.innerHTML = '<option value="">Select parameter</option>';

    // Add new options
    if (params && Array.isArray(params)) {
        params.forEach(param => {
            const option = document.createElement('option');
            option.value = param;
            option.textContent = param;
            dropdown.appendChild(option);
        });
    }
}

function sendSwapParamRequest() {
    const member1 = document.getElementById('swapMember1').value;
    const member2 = document.getElementById('swapMember2').value;
    const paramName = document.getElementById('swapParam').value;
    
    if ((!member1 || !member2 || !paramName) && member1 === member2) {
        console.warn('Incomplete swap parameters');
        return;
    }
    
    bunkerSocket.send(JSON.stringify({
        kind: 'swap_param_value',
        member1: member1,
        member2: member2,
        param_name: paramName
    }));
}

function sendStealParamRequest() {
    if (!memberFrom || !memberTo || !paramName || memberFrom === memberTo) {
        return;
    }

    const memberFrom = document.getElementById('stealFromMember').value;
    const memberTo = document.getElementById('stealToMember').value;
    const paramName = document.getElementById('stealParam').value;    
    
    bunkerSocket.send(JSON.stringify({
        kind: 'steal_param_value',
        member_from: memberFrom,
        member_to: memberTo,
        param_name: paramName
    }));
    
    console.log('Steal request sent', { memberFrom, memberTo, paramName });
}

function sendSetParamRequest() {
    const member = document.getElementById('setMember').value;
    const paramName = document.getElementById('setParam').value;
    const newValue = document.getElementById('setParamValue').value;
    
    if (!member || !paramName || newValue === '') {
        return;
    }

    bunkerSocket.send(JSON.stringify({
        kind: 'set_param_value',
        member: member,
        param_name: paramName,
        new_value: newValue
    }));
    
    console.log('Set parameter request sent', { member, paramName, newValue });
}

// Event Listeners
document.addEventListener('DOMContentLoaded', function() {
    const initLobbyBtn = document.getElementById('initLobbyBtn');
    if (initLobbyBtn) {
        initLobbyBtn.addEventListener('click', function() {
            console.log('Init lobby button clicked');
            bunkerSocket.send(JSON.stringify({
                kind: 'init_board'
            }));
        });
    }
    
    const swapParamBtn = document.getElementById('swapParamBtn');
    if (swapParamBtn) {
        swapParamBtn.addEventListener('click', function() {
            console.log('Swap parameters button clicked');
            sendSwapParamRequest();
        });
    }
    
    const stealParamBtn = document.getElementById('stealParamBtn');
    if (stealParamBtn) {
        stealParamBtn.addEventListener('click', function() {
            console.log('Steal parameter button clicked');
            sendStealParamRequest();
        });
    }
    
    const setParamBtn = document.getElementById('setParamBtn');
    if (setParamBtn) {
        setParamBtn.addEventListener('click', function() {
            console.log('Set parameter button clicked');
            sendSetParamRequest();
        });
    }
});
