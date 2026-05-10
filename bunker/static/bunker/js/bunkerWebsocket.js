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
        case 'toggle_status':
            handleToggleStatus(data);
            break;
        default:
            console.log('Server sent unrecognized message type ' + data.kind);
            break;
    }
};

const parameterOptions = {
    'living_creature': 'Живое существо',
    'physique': 'Самочувствие',
    'trait': 'Черта',
    'profession': 'Профессия',
    'health': 'Здоровье',
    'enthusiasm': 'Боевой дух',
    'fear': 'Страх',
    'inventory': 'Инвентарь',
    'backpack': 'Рюкзак',
    'additional_information': 'Дополнительная информация',
};

// View mode: 'card' or 'table'
let viewMode = localStorage.getItem('bunkerViewMode') || 'card';

// Cache latest board state so view mode switching doesn't need a new websocket request
let lastMembers = [];
let lastSelfData = [];
let lastBoardData = null;
let banedMembers = [];
let isAdmin = false;

function setViewMode(mode) {
    const gameTable = document.getElementById('gameTable');
    const toggleBtn = document.getElementById('toggleViewBtn');

    if (!gameTable || !toggleBtn) return;

    viewMode = mode === 'table' ? 'table' : 'card';
    localStorage.setItem('bunkerViewMode', viewMode);

    gameTable.classList.toggle('table-mode', viewMode === 'table');
    gameTable.classList.toggle('card-mode', viewMode === 'card');

    toggleBtn.textContent = viewMode === 'table' ? 'Switch to card view' : 'Switch to table view';

    renderGameTable(lastMembers, lastBoardData);
}

function renderGameTable(members, boardData) {
    if (viewMode === 'table') {
        populateGameTableTableMode(members, boardData);
    } else {
        populateGameTableCardMode(members, boardData);
    }
}

function populateParameterSelectors() {
    const selects = document.querySelectorAll('.param-select');
    selects.forEach(select => {
        // Keep the placeholder option if present
        select.querySelectorAll('option:not([value=""])').forEach(opt => opt.remove());
        Object.entries(parameterOptions).forEach(([value, label]) => {
            const option = document.createElement('option');
            option.value = value;
            option.textContent = label;
            select.appendChild(option);
        });
    });
}

function handleSetBoardData(data) {
    const { is_host, self_data, board_data, members, baned_members } = data;
    const adminMenu = document.getElementById('adminMenu');
    adminMenu.style.display = is_host ? 'block' : 'none';
    isAdmin = is_host;
    updateBoardState(members, self_data, board_data);
    for (const member of baned_members){
        updateBanStatus(member, true);
    }
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
    lastMembers = Array.isArray(members) ? members : [];
    lastSelfData = Array.isArray(selfData) ? selfData : [];
    lastBoardData = boardData;

    populatePersonalTable(selfData);
    populateMemberDropdowns(members); // Update admin dropdowns
    renderGameTable(members, boardData);
}

function populatePersonalTable(selfData) {
    const personalTable = document.getElementById('personalTable');
    if (!personalTable) return;

    // Clear existing parameter cards
    personalTable.innerHTML = '';

    const PARAM_SLOTS = Math.ceil(Object.keys(parameterOptions).length / 3) * 3;
    const params = Array.isArray(selfData) ? selfData : [];

    // Add cards for each attribute
    params.forEach(item => {
        const paramName = item.param_name || '';
        const value = item.value || '';
        const isOpen = Boolean(item.is_open);

        const card = document.createElement('div');
        card.classList.add('personal-param-card');
        card.setAttribute('data-param', paramName);

        const nameLabel = document.createElement('div');
        nameLabel.classList.add('param-name');
        nameLabel.textContent = parameterOptions[paramName] || paramName.replace(/_/g, ' ');

        const button = document.createElement('button');
        button.classList.add('btn-toggle-param');
        button.classList.add(isOpen ? 'open' : 'closed');
        button.textContent = isOpen ? 'Close' : 'Open';
        button.setAttribute('data-param', paramName);
        button.addEventListener('click', function() {
            sendOpenParamRequest(this.getAttribute('data-param'));
        });

        const headerRow = document.createElement('div');
        headerRow.classList.add('param-header');
        headerRow.appendChild(nameLabel);
        headerRow.appendChild(button);

        const valueLabel = document.createElement('div');
        valueLabel.classList.add('param-value');
        valueLabel.textContent = value;

        card.appendChild(headerRow);
        card.appendChild(valueLabel);
        personalTable.appendChild(card);
    });

    // Add blank cards to maintain a consistent 3x4 grid
    for (let i = params.length; i < PARAM_SLOTS; i++) {
        const emptyCard = document.createElement('div');
        emptyCard.classList.add('personal-param-card', 'empty');
        personalTable.appendChild(emptyCard);
    }
}

function populateGameTableCardMode(members, boardData = null) {
    clearGameTable();

    if (members && Array.isArray(members)) {
        members.forEach(member => createMemberCard(member, boardData ? boardData[member] : null));
    }
}

function populateGameTableTableMode(members, boardData = null) {
    clearGameTable();

    const gameTable = document.getElementById('gameTable');
    const headerRow = document.createElement('div');
    headerRow.classList.add('grid-row');

    for (let i = -1; i < Object.keys(parameterOptions).length; i++) {
        const headerCell = document.createElement('div');
        headerCell.classList.add('grid-header');
        headerCell.textContent = i === -1 ? 'Username' : Object.values(parameterOptions)[i];
        headerRow.appendChild(headerCell);
    }

    gameTable.appendChild(headerRow);

    if (members && Array.isArray(members)) {
        members.forEach(member => createMemberRow(member, boardData ? boardData[member] : null));
    }
}

function handleBoardInit(data) {
    const { members, self_data } = data;
    updateBoardState(members, self_data);
    lastBoardData = null;
    console.log('Board initialized with', members.length, 'members');
}

function clearGameTable() {
    const gameTable = document.getElementById('gameTable');
    gameTable.innerHTML = '';
}

function createMemberCard(memberName, initialData = null) {
    const gameTable = document.getElementById('gameTable');
    const card = document.createElement('div');
    card.classList.add('member-card');
    card.setAttribute('data-member', memberName);
    if (banedMembers.includes(memberName)){
        card.classList.add('banned');
    }

    const header = document.createElement('div');
    header.classList.add('member-card-header');
    header.textContent = memberName;

    if (isAdmin) {
        const disableBtn = document.createElement('button');
        disableBtn.classList.add('btn-disable-member');
        disableBtn.textContent = 'Disable';
        disableBtn.addEventListener('click', function() {
            sendToggleStatusRequest(memberName);
        });
        header.appendChild(disableBtn);
        header.style.display = 'flex';
        header.style.justifyContent = 'space-between';
        header.style.alignItems = 'center';
    }

    card.appendChild(header);

    const paramGrid = document.createElement('div');
    paramGrid.classList.add('param-grid');

    const parameterMap = {};
    if (initialData && Array.isArray(initialData)) {
        initialData.forEach(param => {
            parameterMap[param.param_name] = param.value;
        });
    }

    Object.keys(parameterOptions).forEach(param => {
        const cell = document.createElement('div');
        cell.classList.add('param-cell');
        cell.setAttribute('data-param', param);

        const nameLabel = document.createElement('span');
        nameLabel.classList.add('param-name');
        nameLabel.textContent = parameterOptions[param];

        const valueLabel = document.createElement('span');
        valueLabel.classList.add('param-value');
        valueLabel.textContent = parameterMap[param] || '';

        cell.appendChild(nameLabel);
        cell.appendChild(valueLabel);
        paramGrid.appendChild(cell);
    });

    card.appendChild(paramGrid);

    gameTable.appendChild(card);
}

function getSelfParamValue(paramName) {
    const personalTable = document.getElementById('personalTable');
    const valueEl = personalTable.querySelector(`.personal-param-card[data-param="${paramName}"] .param-value`);
    return valueEl ? valueEl.textContent : null;
}

function createMemberRow(memberName, initialData = null) {
    const gameTable = document.getElementById('gameTable');
    const row = document.createElement('div');
    row.classList.add('grid-row');
    row.setAttribute('data-member', memberName);
    if (banedMembers.includes(memberName)){
        row.classList.add('banned');
    }
    
    // Username column (filled)
    const usernameCell = document.createElement('div');
    usernameCell.classList.add('grid-cell');
    usernameCell.textContent = memberName;

    if (isAdmin) {
        const disableBtn = document.createElement('button');
        disableBtn.classList.add('btn-disable-member');
        disableBtn.textContent = 'Disable';
        disableBtn.addEventListener('click', function() {
            sendToggleStatusRequest(memberName);
        });
        usernameCell.appendChild(disableBtn);
        usernameCell.style.display = 'flex';
        usernameCell.style.justifyContent = 'space-between';
        usernameCell.style.alignItems = 'center';
    }

    row.appendChild(usernameCell);

    const parameterMap = {};
    if (initialData && Array.isArray(initialData)) {
        initialData.forEach(param => {
            parameterMap[param.param_name] = param.value;
        });
    }
    Object.keys(parameterOptions).forEach(param => {
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

    let valueCell;

    if (viewMode === 'table') {
        valueCell = gameTable.querySelector(`.grid-row[data-member="${member}"] .grid-cell[data-param="${paramName}"]`);
    } else {
        valueCell = gameTable.querySelector(`.member-card[data-member="${member}"] .param-cell[data-param="${paramName}"] .param-value`);
    }

    if (valueCell == null) {
        console.warn('Cell not found for member:', member, 'param:', paramName);
        return;
    }
    if (!lastBoardData){
        lastBoardData = {};
    }
    if (!lastBoardData[member]){
        lastBoardData[member] = [];
    }
    lastBoardData[member].push({'param_name': paramName, 'value': newValue});
    valueCell.textContent = newValue;
}

function updatePersonalTableCell(paramName, newValue) {
    const personalTable = document.getElementById('personalTable');
    const valueEl = personalTable.querySelector(`.personal-param-card[data-param="${paramName}"] .param-value`);
    if (valueEl) {
        valueEl.textContent = newValue;
        return;
    }
    console.warn('Parameter not found in personal table:', paramName);
}

function sendToggleStatusRequest(member) {
    bunkerSocket.send(JSON.stringify({
        kind: 'toggle_status',
        member: member
    }));
}

function handleOpenParam(data) {
    const { param_name, is_open } = data;
    const button = document.querySelector(`#personalTable .personal-param-card[data-param="${param_name}"] button`);
    
    if (!button) {
        console.warn('Button not found for param:', param_name);
        return;
    }
    
    // Update button text and state
    button.textContent = is_open ? 'Close' : 'Open';
    button.setAttribute('data-is-open', is_open ? 'true' : 'false');
    button.classList.toggle('open', is_open);
    button.classList.toggle('closed', !is_open);
    
    if (is_open) {
        const paramValue = getSelfParamValue(param_name);
        updateGameTableCell(currentNick, param_name, paramValue);
    } else {
        updateGameTableCell(currentNick, param_name, '');
    }
}

function handleToggleStatus(data) {
    const { member, is_banned } = data;
    updateBanStatus(member, is_banned);
}

function updateBanStatus(member, is_banned) {

    const card = document.querySelector(`.member-card[data-member="${member}"]`);
    if (card) {
        card.classList.toggle('banned', is_banned);
    }

    const row = document.querySelector(`.grid-row[data-member="${member}"]`);
    if (row) {
        row.classList.toggle('banned', is_banned);
    }

    if (is_banned) {
        banedMembers.push(member);
    } else {
        banedMembers = banedMembers.filter(m => m !== member);
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

function sendOpenParamRequest(paramName) {
    bunkerSocket.send(JSON.stringify({
        kind: 'open_param',
        param_name: paramName
    }));
}

function sendSwapParamRequest() {
    const member1 = document.getElementById('swapMember1').value;
    const member2 = document.getElementById('swapMember2').value;
    const paramName = document.getElementById('swapParam').value;
    
    if (!member1 || !member2 || !paramName || member1 === member2) {
        console.warn('Incomplete or invalid swap parameters');
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
    const memberFrom = document.getElementById('stealFromMember').value;
    const memberTo = document.getElementById('stealToMember').value;
    const paramName = document.getElementById('stealParam').value;

    if (!memberFrom || !memberTo || !paramName || memberFrom === memberTo) {
        console.warn('Incomplete or invalid steal parameters');
        return;
    }

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

document.addEventListener('DOMContentLoaded', function() {
    populateParameterSelectors();

    const initLobbyBtn = document.getElementById('initLobbyBtn');
    if (initLobbyBtn) {
        initLobbyBtn.addEventListener('click', function() {
            console.log('Init lobby button clicked');
            bunkerSocket.send(JSON.stringify({
                kind: 'init_board'
            }));
        });
    }

    const toggleViewBtn = document.getElementById('toggleViewBtn');
    if (toggleViewBtn) {
        toggleViewBtn.addEventListener('click', function() {
            setViewMode(viewMode === 'table' ? 'card' : 'table');
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

    // Initialize view mode UI
    setViewMode(viewMode);
});
