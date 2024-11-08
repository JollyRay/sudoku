const roomName = JSON.parse(document.getElementById('room-code').textContent);
const selfnick = document.cookie.split("; ").find((row) => row.startsWith("nick="))?.split("=")[1];
let sudokuMode = 'digit';

const SIDE_SIZE = 9;
const CELL_QUANTITY = SIDE_SIZE * SIDE_SIZE;
const CELL_SIZE = 60;
const CELL_SIDE = 3;
const BIG_CELL_SIZE = CELL_SIZE * CELL_SIDE;
const FIELD_SIZE = BIG_CELL_SIZE * CELL_SIDE;
let isGenereate = false;
let isNoteMode = false;
let isDigitMode = false;
var timerStartTime = new Date();
var timerNode;

let selectedCellNode = undefined;
let lastDigitSelect = undefined;
let selectEnemyBoder = undefined;

var chatSocket;

if (location.protocol == 'https:'){
    chatSocket = new WebSocket(
        'wss://'
        + window.location.host
        + '/ws/sudoku/'
        + roomName
        + '/'
    );
} else {
    chatSocket = new WebSocket(
        'ws://'
        + window.location.host
        + '/ws/sudoku/'
        + roomName
        + '/'
    );
}

const IMAGE_MAP ={
    'holo': {
        1 : 'https://hololive.hololivepro.com/wp-content/uploads/2021/05/houshou_marine_thumb.png',
        2 : 'https://hololive.hololivepro.com/wp-content/uploads/2023/04/Usada-Pekora_list_thumb.png',
        3 : 'https://hololive.hololivepro.com/wp-content/uploads/2023/04/Inugami-Korone_list_thumb.png',
        4 : 'https://hololive.hololivepro.com/wp-content/uploads/2020/06/Shirakami-Fubuki_list_thumb.png',
        5 : 'https://hololive.hololivepro.com/wp-content/uploads/2021/05/tokino_sora_thumb.png',
        6 : 'https://hololive.hololivepro.com/wp-content/uploads/2021/12/shion_thumb.png',
        7 : 'https://hololive.hololivepro.com/wp-content/uploads/2023/01/Ookami-Mio_thumb.png',
        8 : 'https://hololive.hololivepro.com/wp-content/uploads/2023/04/Shiranui-Flare_list_thumb.png',
        9 : 'https://hololive.hololivepro.com/wp-content/uploads/2024/05/La-Darknesss_list_thumb.png'
    },
    'schepka': {
        1: 'https://static-cdn.jtvnw.net/emoticons/v2/emotesv2_6d971473d5a34d10ac6e31e75b351c03/default/dark/3.0',
        2: 'https://static-cdn.jtvnw.net/emoticons/v2/emotesv2_c7f2464b528b46558eb6836ad227cedc/default/dark/3.0',
        3: 'https://static-cdn.jtvnw.net/emoticons/v2/emotesv2_a0775f452a374d039478bcaad72fa456/default/dark/3.0',
        4: 'https://static-cdn.jtvnw.net/emoticons/v2/emotesv2_72157a58881d433eb2c19a22b6c85687/default/dark/3.0',
        5: 'https://static-cdn.jtvnw.net/emoticons/v2/emotesv2_9a404496158142289d9f4f78a370107a/default/dark/3.0',
        6: 'https://static-cdn.jtvnw.net/emoticons/v2/emotesv2_683c33856ae74f7c8372e1989c0438c9/default/dark/3.0',
        7: 'https://static-cdn.jtvnw.net/emoticons/v2/emotesv2_dfd4b23279534e20b4e488edc8c05cb8/default/dark/3.0',
        8: 'https://static-cdn.jtvnw.net/emoticons/v2/emotesv2_c5c36433c765458b9c10ad80edeb2a28/default/dark/3.0',
        9: 'https://static-cdn.jtvnw.net/emoticons/v2/emotesv2_35508c56d011473a9f146b1863ce56d8/default/dark/3.0'
    },
    'torry': {
        1: 'https://cdn.7tv.app/emote/66abfbf0e0109125ee25e3fd/4x.webp',
        2: 'https://cdn.7tv.app/emote/66f310d09a2a98137f488cc9/4x.webp',
        3: 'https://cdn.7tv.app/emote/6668a85eba453b48ddcb170c/4x.webp',
        4: 'https://cdn.7tv.app/emote/662f759259a94de4ca08f09c/4x.webp',
        5: 'https://cdn.7tv.app/emote/66b26be7bb3411bd939a56d1/4x.webp',
        6: 'https://cdn.7tv.app/emote/666c9be6a4cae22f82d9f318/4x.webp',
        7: 'https://static-cdn.jtvnw.net/emoticons/v2/emotesv2_756ba1d6603741f2b1e7c3f3c09ca759/default/dark/3.0',
        8: 'https://cdn.7tv.app/emote/670102cfdaf243ce8c7a0686/4x.webp',
        9: 'https://cdn.7tv.app/emote/60ae7316f7c927fad14e6ca2/4x.webp',
    }
}

chatSocket.onclose = function(e) {
    console.error('Chat socket closed unexpectedly');
};


/****************************
*                           *
*       SERVER MOMENT       *
*                           *
*****************************/

chatSocket.onmessage = function(e) {
    const data = JSON.parse(e.data);
    console.log(data);

    switch (data.kind) {
        case 'first_data':
            fillOtherBoard(data.data);
            break;
        case 'board':
            fillNamedBoard(data.to, data.board, data.bonus);
            if (data.to.toLowerCase() == selfnick.toLowerCase()){
                isGenereate = true;
                timerStartTime = new Date();
            }
            break;
        case 'new_user':
            if (selfnick != data.nick){
                createBorder(data.nick);
            }
            break;
        case 'cell_result':
            updateValueFromServer(data.to, data.cell_number, data.value, data.is_right);
            if (data.bonus_type !== null)
                bonusExecute(data.to, data.bonus_type, data.detale);
            break;
        case 'disconection':
            removeBoard(data.nick);
            break;
        case 'admin_bonus':
            bonusExecute(data.to, data.bonus_type, data.detale, data.to != '__all__');
            break;
        case 'is_add_twitch':
            if (data.ok){
                acceptTwitchChannel();
            } else {
                rejectTwitchChannel();
            }
            break;
        default:
            console.log('Server send uncorrect message');
            break;
    }
};

function removeBoard(nick){
    const board = findBoard(nick);
    if (board != null){
        board.remove();
    }
    const scoreNode = document.querySelector(`div.user-score-container[name="${nick}"]`)
    if (scoreNode != undefined){
        scoreNode.parentNode.remove();
    }
}

function updateValueFromServer(nick, cellNumber, value, isRight){

    const userOptionNode = findBoard(nick); 
    if (userOptionNode == null) return;

    if (!isEqualValue(nick, cellNumber, value)){
        recalculateProcessBar(userOptionNode);
    }

    const cellNode = userOptionNode.querySelector(`div.sudoku-cell[number="${cellNumber}"]`);

    if (isRight) {
        cellNode.classList.remove('wrong-answer');
    } else {
        cellNode.classList.add('wrong-answer');
    }
    if (nick != selfnick){
        setCellValue(cellNode, value);
    }

    if (isFinish(userOptionNode)){
        userOptionNode.classList.add('resolved-sudoku-field');
        if (userOptionNode.getAttribute('name').toLowerCase() == selfnick.toLowerCase()) isGenereate = false;
    }
}

function bonusExecute(nick, bonusType, detale, isInvert){
    nick = nick.toUpperCase();
    switch (bonusType) {
        case 'SWAP':
            getAllOptionNodes().forEach(userOptionNode => {
                if (userOptionNode.getAttribute('name').toUpperCase() != nick
                        ^ isInvert) {
                    if (detale.is_big){
                        if (detale.is_row){
                            swapBigRow(detale.first, detale.second, userOptionNode);
                        } else {
                            swapBigColumn(detale.first, detale.second, userOptionNode);
                        }
                    } else {
                        if (detale.is_row){
                            swapRow(detale.first, detale.second, userOptionNode);
                        } else {
                            swapColumn(detale.first, detale.second, userOptionNode);
                        }
                    }
                }
            });
            
            break;
        case 'SHADOW_BOX':
            getAllOptionNodes().forEach(userOptionNode => {
                if (userOptionNode.getAttribute('name').toUpperCase() != nick
                        ^ isInvert
                        && userOptionNode.querySelectorAll('.shadow-square').length < 3) {
                    shadowBox(detale.box, userOptionNode);
                }
            });
            break;
        case 'ROLL':
            getAllOptionNodes().forEach(userOptionNode => {
                if (userOptionNode.getAttribute('name').toUpperCase() != nick
                        ^ isInvert) {rotateBox(detale.box, userOptionNode);}
            });
            break;
    
        default:
            break;
    }
}

const sudokuCellReg = new RegExp('^sudoku-cell(-[0-9])?$');
function fillBoard(userOptionNode, boardValues, bonusMap){

    userOptionNode.classList.remove('resolved-sudoku-field');

    selectedCellNode = undefined;
    let fillCellQuantity = 0;
    for (let index = 0; index < CELL_QUANTITY; index++){
        const cellNode = userOptionNode.querySelector(`div.sudoku-cell[number="${index}"]`);
        Array.from(cellNode.classList).forEach(className => {
            if (!sudokuCellReg.test(className)){
                cellNode.classList.remove(className);
            }
        });
        if (boardValues[index]){
            cellNode.classList.add('static-answer');
            fillCellQuantity++;
        }
        setCellValue(cellNode, boardValues[index]);
    }

    userOptionNode.querySelectorAll('.bonus-cell').forEach(el => el.remove());

    if (bonusMap)
        for (const [cellIndex, bonusName] of Object.entries(bonusMap)){
            let bonusDiv = document.createElement('div');

            if (bonusName == 'SWAP'){
                bonusDiv.innerText = '⇄';
            } else if (bonusName == 'ROLL') {
                bonusDiv.innerText = '↻';
            } else {
                bonusDiv.innerText = '■';
            }

            bonusDiv.classList.add('bonus-cell');

            userOptionNode.querySelector(`div[number="${cellIndex}"`).appendChild(bonusDiv);
        }

    document.querySelectorAll('.numbers-button').forEach(el => el.classList.remove('number-button-ended'));

    const nick = userOptionNode.getAttribute('name');
    
    updateProcessBar(nick, fillCellQuantity);
    
}

function fillNamedBoard(nick, boardInfo, bonusMap){
    const userOptionNode = findBoard(nick);
    if (userOptionNode == null){
        return;
    }
    if (isNoteMode){
        switchNoteMode()
    }

    fillBoard(userOptionNode, boardInfo, bonusMap);
}

function createBorder(nick, isSelf){
    let container;
    if (isSelf){
        container = document.getElementById('self-sudoku');
    } else{
        container = document.querySelector('.enemy-option');

        const scoreContainerNode = document.getElementById('score-container');
        
        const scoreTemplate = document.getElementById('score-template'); 
        const scoreTemplateClone = scoreTemplate.content.cloneNode(true);
        scoreTemplateClone.querySelector('.score-owner-name').innerText = sliceNick(nick);
        const mainContainer = scoreTemplateClone.querySelector('.user-score-container')
        mainContainer.setAttribute('name', nick);
        mainContainer.addEventListener('click', selectEnemy);
        scoreTemplateClone.querySelector('.score-progress').value = 0;
        scoreContainerNode.appendChild(scoreTemplateClone);
    }
    const template = document.getElementById("user-optrion-template");

    const clone = template.content.cloneNode(true);
    const optrionHeader = clone.querySelector("h1");
    optrionHeader.textContent = sliceNick(nick);
    const userOption = clone.querySelector(".user-option");
    userOption.setAttribute('name', nick);
    if (sudokuMode != 'digit' ) { userOption.classList.add('backcground-value-mode'); }
    if (document.querySelectorAll('.enemy-option .user-option').length > 0) {
        userOption.classList.add('hidden');
    } else {
        selectEnemyBoder = userOption;
    }


    if (isSelf){
        clone.querySelectorAll('div.sudoku-cell').forEach(cell => {
            cell.addEventListener('click', selectNewCell);
        });
    }

    container.appendChild(clone);

    return container.lastElementChild;
}

function fillOtherBoard(boardsInfo){
    if (boardsInfo == null)  return;

    for (const [nick, boardInfo] of Object.entries(boardsInfo)){
        const userOptionNode = createBorder(nick);
        if (boardInfo.value){
            fillBoard(userOptionNode, boardInfo.value, boardInfo.bonus);
        }
    }
}

function requestGenerateSudoku(){
    let dataForSend = {
        "kind": "generate"
    };

    let selectDifficulty = document.getElementById('sudoku-difficulty');
    if (selectDifficulty?.value){
        dataForSend.difficulty = selectDifficulty.value;
    }

    chatSocket.send(JSON.stringify(dataForSend));
}

function requestSetValue(value, cellNumebr){
    chatSocket.send(JSON.stringify({
        "kind": "set_value",
        "cell_number": cellNumebr,
        "value": value
    }));
}

function requestAddTwitchChannel(event){
    chatSocket.send(JSON.stringify({
        "kind": "add_twitch_channel",
        "channel_name": selfnick,
    }));
}

createBorder(selfnick, true);

/****************************
*                           *
*       USER INTERFACE      *
*                           *
*****************************/

function startEventListener(){
    /* Key board event */
    document.addEventListener('keydown', (e) => {
        if (e.key >= '0' && e.key <= '9'){

            let value = Number(e.key);

            if (isDigitMode){
                let numberButton = document.evaluate(`//div[contains(@class,"numbers-button")]/p[text()=${value}]/..`, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE).singleNodeValue;
                selectDigit(numberButton);
            } else if (isGenereate && selectedCellNode != undefined && !selectedCellNode.classList.contains('static-answer')){
                setCellValueAndSend(selectedCellNode, value);
            }
            selectEqualCell(value);
        }
    });

    /* Custom number board event */
    const numberNodes = document.querySelectorAll('.numbers-button');
    numberNodes.forEach(numberNode => {numberNode.addEventListener('click', (event) => {

        if (isDigitMode){
            selectDigit(event.currentTarget);
            return;
        }

        let value = Number(event.currentTarget.innerText) || 0;

        if (isGenereate && selectedCellNode != undefined && !selectedCellNode.classList.contains('static-answer')){
            setCellValueAndSend(selectedCellNode, value);
        }

        selectEqualCell(value);
    })});

    /* Generate Sudoku */
    const generateSudokuButton = document.getElementById('generate-sudoku');
    generateSudokuButton.addEventListener('click', requestGenerateSudoku);

    /* Mode change */
    const modeSelector = document.getElementById('sudoku-mode');
    modeSelector.addEventListener('change', (e) => {
        let tempIsNoteMode = isNoteMode;
        isNoteMode = false;
        sudokuMode = e.target.value;
        rerenderSudoku();
        isNoteMode = tempIsNoteMode;
    });

    const noteButton = document.getElementById('note-mode-button');
    noteButton.addEventListener('click', switchNoteMode);

    const digitFirstButton = document.getElementById('digit-first-mode-button');
    digitFirstButton.addEventListener('click', toggleFirstDigitMode);

    const mistakeButton = document.getElementById('toggle-mistake-button');
    mistakeButton.addEventListener('click', toggleMisstakeMode);

    const addTwitchChannelButton = document.getElementById('add-twitch-channel');
    if (addTwitchChannelButton)
        addTwitchChannelButton.addEventListener('click', requestAddTwitchChannel);

    const hiddenTongue = document.getElementById('hidden-tongue');
    hiddenTongue.addEventListener('click', toggleVisibleAddOption);

    /* Timer start */
    timerNode = document.getElementById('personal-timer');
    setInterval(startTimer, 1000);

}

function switchNoteMode(event){
    let noteModeButton = document.getElementById('note-mode-button');
    isNoteMode = !isNoteMode;
    noteModeButton.classList.toggle('mode-button-active');
}

function selectEqualCell(newValue){
    document.querySelectorAll('.sudoku-cell-equal-select').forEach(cell => {
        cell.classList.remove('sudoku-cell-equal-select');
    });
    if (newValue == 0) return;
    let newEqualCells = document.evaluate(`.//div[contains(@class,"sudoku-cell")]/p[text()=${newValue}]/..`, getAllOptionNodes()[0], null, XPathResult.UNORDERED_NODE_SNAPSHOT_TYPE);

    for (let index = 0; index < newEqualCells.snapshotLength; index++){
        newEqualCells.snapshotItem(index).classList.add('sudoku-cell-equal-select');
    }
}

function selectNewCell(event){
    if (selectedCellNode != undefined){
        selectedCellNode.classList.remove('sudoku-cell-select');
    }
    selectedCellNode = event.currentTarget;
    selectedCellNode.classList.add('sudoku-cell-select');

    let cellValue = selectedCellNode.querySelector('p').innerText;
    if (isDigitMode && lastDigitSelect && !selectedCellNode.classList.contains('static-answer')){
        let value = Number(lastDigitSelect.innerText);
        if (cellValue != value){
            setCellValueAndSend(selectedCellNode, value);
        }
    }

    selectEqualCell(selectedCellNode.querySelector('p').innerText);
}

function toggleFirstDigitMode(event){
    isDigitMode = !isDigitMode;
    event.currentTarget.classList.toggle('mode-button-active');

    if (lastDigitSelect){
        lastDigitSelect.classList.remove('mode-button-active');
    }
    lastDigitSelect = undefined;
}

function toggleMisstakeMode(event){
    event.currentTarget.classList.toggle('mode-button-active');
    let gameFieldNode = document.querySelector('.game-field');
    gameFieldNode.classList.toggle('show-wrong');
}

function selectDigit(numberNode){
    if (lastDigitSelect){
        lastDigitSelect.classList.remove('mode-button-active');
    }
    lastDigitSelect = numberNode;
    lastDigitSelect.classList.add('mode-button-active');
}

function updateProcessBar(nick, value){
    const progressBar = document.querySelector(`div.user-score-container[name="${nick}"] progress`);
    if (progressBar != undefined){
        progressBar.value = value;
    }
}

function recalculateProcessBar(userOptionNode){
    let quantity = getFilledCellQuantity(userOptionNode);
    let nick = userOptionNode.getAttribute('name');

    updateProcessBar(nick, quantity);
}

function incriceProcessBar(nick){
    const progressBar = document.querySelector(`div.user-score-container[name="${nick}"] progress`);
    if (progressBar != undefined){
        progressBar.value = 1 + progressBar.value;
    }
}

function decriceProcessBar(nick){
    const progressBar = document.querySelector(`div.user-score-container[name="${nick}"] progress`);
    if (progressBar != undefined){
        progressBar.value = 1 - progressBar.value;
    }
}

function toggleVisibleAddOption(event){
    event.currentTarget.parentElement.classList.toggle('show-hidden-option');
}

startEventListener();

/****************************
*                           *
*     PAGE MODIFICATION     *
*                           *
*****************************/

function swapRow(firstIndex, secondIndex, userOptionNode){
    const addForFirst = SIDE_SIZE * (secondIndex - firstIndex);
    const addForSecond = SIDE_SIZE * (firstIndex - secondIndex);
    const firstStart = firstIndex * SIDE_SIZE;
    const firstFinish = (firstIndex + 1) * SIDE_SIZE - 1;
    const secondStart = secondIndex * SIDE_SIZE;
    const secondFinish = (secondIndex + 1) * SIDE_SIZE - 1;
    let firstNodes = document.evaluate(`.//div[@now>=${firstStart} and @now<=${firstFinish}]`, userOptionNode, null, XPathResult.UNORDERED_NODE_SNAPSHOT_TYPE);
    let secondNodes = document.evaluate(`.//div[@now>=${secondStart} and @now<=${secondFinish}]`, userOptionNode, null, XPathResult.UNORDERED_NODE_SNAPSHOT_TYPE);

    const newTopForFirst = CELL_SIZE * (secondIndex % 3) + 'px';
    const newTopForSecond = CELL_SIZE * (firstIndex % 3) + 'px';

    for (let index = 0; index < SIDE_SIZE; index++) {
        firstNodes.snapshotItem(index).style.top = newTopForFirst;
        firstNodes.snapshotItem(index).setAttribute('now', Number(firstNodes.snapshotItem(index).getAttribute('now')) + addForFirst);
    }
    for (let index = 0; index < SIDE_SIZE; index++) {
        secondNodes.snapshotItem(index).style.top = newTopForSecond;
        secondNodes.snapshotItem(index).setAttribute('now', Number(secondNodes.snapshotItem(index).getAttribute('now')) + addForSecond);
    }
}

function swapBigRow(firstIndex, secondIndex, userOptionNode){
    const addForFirst = (secondIndex - firstIndex) * CELL_SIDE;
    const addForSecond = (firstIndex - secondIndex) * CELL_SIDE;
    const firstStart = firstIndex * CELL_SIDE;
    const firstFinish = (firstIndex + 1) * CELL_SIDE - 1;
    const secondStart = secondIndex * CELL_SIDE;
    const secondFinish = (secondIndex + 1) * CELL_SIDE - 1;
    let firstNodes = document.evaluate(`.//div[@big-cell-index>=${firstStart} and @big-cell-index<=${firstFinish}]`, userOptionNode, null, XPathResult.UNORDERED_NODE_SNAPSHOT_TYPE);
    let secondNodes = document.evaluate(`.//div[@big-cell-index>=${secondStart} and @big-cell-index<=${secondFinish}]`, userOptionNode, null, XPathResult.UNORDERED_NODE_SNAPSHOT_TYPE);

    const newTopForFirst = BIG_CELL_SIZE * secondIndex + 'px';
    const newTopForSecond = BIG_CELL_SIZE * firstIndex + 'px';

    for (let index = 0; index < firstNodes.snapshotLength; index++) {
        firstNodes.snapshotItem(index).style.top = newTopForFirst;
        firstNodes.snapshotItem(index).setAttribute('big-cell-index', Number(firstNodes.snapshotItem(index).getAttribute('big-cell-index')) + addForFirst);
    }
    for (let index = 0; index < secondNodes.snapshotLength; index++) {
        secondNodes.snapshotItem(index).style.top = newTopForSecond;
        secondNodes.snapshotItem(index).setAttribute('big-cell-index', Number(secondNodes.snapshotItem(index).getAttribute('big-cell-index')) + addForSecond);
    }
}

function swapColumn(firstIndex, secondIndex, userOptionNode){
    const addForFirst = (secondIndex - firstIndex);
    const addForSecond = (firstIndex - secondIndex);

    const newLeftForFirst = CELL_SIZE * (secondIndex % 3) + 'px';
    const newLeftForSecond = CELL_SIZE * (firstIndex % 3) + 'px';

    const cellNodes = userOptionNode.querySelectorAll('.sudoku-cell');
    for (let index = 0; index < CELL_QUANTITY; index++){
        let nowNumber = Number(cellNodes[index].getAttribute('now'));
        if (nowNumber % SIDE_SIZE == firstIndex){
            cellNodes[index].setAttribute('now', nowNumber + addForFirst);
            cellNodes[index].style.left = newLeftForFirst;
        } else if (nowNumber % SIDE_SIZE == secondIndex){
            cellNodes[index].setAttribute('now', nowNumber + addForSecond);
            cellNodes[index].style.left = newLeftForSecond;
        }
    }
}

function swapBigColumn(firstIndex, secondIndex, userOptionNode){
    const addForFirst = (secondIndex - firstIndex);
    const addForSecond = (firstIndex - secondIndex);

    const newLeftForFirst = BIG_CELL_SIZE * secondIndex + 'px';
    const newLeftForSecond = BIG_CELL_SIZE * firstIndex + 'px';

    const cellNodes = userOptionNode.querySelectorAll('.sudoku-big-cell');
    for (let index = 0; index < cellNodes.length; index++){
        let nowNumber = Number(cellNodes[index].getAttribute('big-cell-index'));
        if (nowNumber % CELL_SIDE == firstIndex){
            cellNodes[index].setAttribute('big-cell-index', nowNumber + addForFirst);
            cellNodes[index].style.left = newLeftForFirst;
        } else if (nowNumber % CELL_SIDE == secondIndex){
            cellNodes[index].setAttribute('big-cell-index', nowNumber + addForSecond);
            cellNodes[index].style.left = newLeftForSecond;
        }
    }
}

function shadowBox(index, userOptionNode){
    const lockSquare = userOptionNode.querySelector(`div.sudoku-big-cell[big-cell-index="${index}"]`);
    if (lockSquare.classList.contains('shadow-square')){
        return;
    }
    lockSquare.classList.add('shadow-square');
    setTimeout(unlock.bind(null, lockSquare), 25000);
}

function unlock(lockedSquare){
    lockedSquare.classList.remove('shadow-square');
}

function rotateBox(index, userOptionNode){
    const rotateSquare = userOptionNode.querySelector(`div.sudoku-big-cell[big-cell-index="${index}"]`);
    rotateSquare.style.transform = 'rotate(1080deg)';

    setTimeout(() => {
        rotateSquare.style.transform = '';
    }, 5000);
}

function rerenderSudoku(){

    /* Change number board */

    document.querySelectorAll('.numbers-button').forEach(numberButton => {
        if (sudokuMode == 'digit'){
            numberButton.classList.remove('number-as-img');
            numberButton.style.backgroundImage = '';
        } else {
            let tempValue = numberButton.textContent.trim();
            if (tempValue > 0 && tempValue <= 9){
                numberButton.classList.add('number-as-img');
                setCellValue(numberButton, tempValue);
            }
        }
    });


    /* Change sudoku boards */
    getAllOptionNodes().forEach(nodeOption => {
        if (sudokuMode == 'digit'){
            nodeOption.classList.remove('backcground-value-mode');
        } else {
            nodeOption.classList.add('backcground-value-mode');
        }

        nodeOption.querySelectorAll('.sudoku-cell').forEach(cellNode => {
            value = cellNode.querySelector('p').innerText.trim();
            if (value == ''){
                rerenderNotes(cellNode)
            } else {
                setCellValue(cellNode, value);
            }
        });
    });
}

function rerenderNotes(cellNode){
    const noteDivs = cellNode.querySelectorAll('.cell-notes *');

    for (let index = 0; index < noteDivs.length; index++){
        let innerValue = noteDivs[index].innerText.trim();
        if (innerValue != ''){
            if (sudokuMode == 'digit'){
                noteDivs[index].innerText = index + 1;
            } else {
                noteDivs[index].innerText = '■';
            }
        }
    }
}

function setCellValue(cellNode, value){
    let fieldForValue = cellNode.querySelector('p');
    let noteCells = cellNode.querySelectorAll('div.cell-notes div');
    if (isNoteMode){
        if (cellNode.classList.contains('wrong-answer')){
            cellNode.classList.remove('wrong-answer');
        }
        fieldForValue.innerText = '';
        cellNode.style.backgroundImage = '';
        if (noteCells[value - 1].innerText){
            noteCells[value - 1].innerText = '';
        } else {
            if (sudokuMode == 'digit'){
                noteCells[value - 1].innerText = value;
            } else {
                noteCells[value - 1].innerText = '■';
            }
        }

        return 0;
        
    }

    if (value || (fieldForValue.innerText != value && value > 0 && value <= 9)){
        fieldForValue.innerText = value;
    } else {
        fieldForValue.innerText = '';
    }

    if (sudokuMode == 'digit'){
        cellNode.style.backgroundImage = '';
    } else {
        cellNode.style.backgroundImage = (value) ? `url("${IMAGE_MAP[sudokuMode][value]}")` : '';
    }

    noteCells.forEach(noteElement => {
        noteElement.innerText = '';
    });
}

function setCellValueAndSend(cellNode, value){
    if (isNoteMode || !isEqualValue(selfnick, cellNode.getAttribute('number'), value)){
        const userOptionNode = findBoard(selfnick);
        let oldValue = cellNode.querySelector('p').textContent.trim();
        let oldQuantity = document.evaluate(`.//div[contains(@class,'sudoku-cell')]/p[text() = '${oldValue}']`, userOptionNode, null, XPathResult.UNORDERED_NODE_SNAPSHOT_TYPE).snapshotLength;
        
        if (!isNoteMode){
            requestSetValue(value, Number(cellNode.getAttribute('number')));
        }
        setCellValue(cellNode, value);

        
    
        if (oldQuantity == SIDE_SIZE){
            const oldNumberNode = document.evaluate(`//div[contains(@class,'numbers-button')]/p[contains(., '${oldValue}')]/..`, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE).singleNodeValue;
            oldNumberNode.classList.remove('number-button-ended');
        }
    
        let nowQuantity = document.evaluate(`.//div[contains(@class,'sudoku-cell')]/p[text() = '${value}']`, userOptionNode, null, XPathResult.UNORDERED_NODE_SNAPSHOT_TYPE).snapshotLength;

        if (nowQuantity == SIDE_SIZE){
            const newNumberNode = document.evaluate(`//div[contains(@class,'numbers-button')]/p[contains(., '${value}')]/..`, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE).singleNodeValue;
            newNumberNode.classList.add('number-button-ended');
        }
    }
}

function selectEnemy(event){
    const mainContainer = event.currentTarget;
    const nick = mainContainer.getAttribute('name');

    if (nick == undefined){
        mainContainer.parentElement.remove();
        return;
    }

    if (selectEnemyBoder != undefined){
        selectEnemyBoder.classList.add('hidden');
    }

    const newSelectBoard = findBoard(nick);
    
    selectEnemyBoder = newSelectBoard;
    selectEnemyBoder.classList.remove('hidden');

    
}

function acceptTwitchChannel(){
    const addTwitchChannelButton = document.getElementById('add-twitch-channel');
    if (addTwitchChannelButton){
        addTwitchChannelButton.removeEventListener('click', requestAddTwitchChannel);
        addTwitchChannelButton.parentElement.classList.add('twitch-is-add');
    }
}

function rejectTwitchChannel(){
    const addTwitchChannelButton = document.getElementById('add-twitch-channel');
    if (addTwitchChannelButton){
        addTwitchChannelButton.addEventListener('click', requestAddTwitchChannel);
        addTwitchChannelButton.parentElement.classList.remove('twitch-is-add');
    }
}

function startTimer(){
    if (isGenereate){
        let timeDelta = new Date() - timerStartTime;

        let second = ~~(timeDelta  / 1000) % 60;
        if (second < 10)
            second = "0" + second;
        let minuts = ~~(timeDelta  / 60000);

        timerNode.innerText = `${minuts}:${second}`;
    }
}

/****************************
*                           *
*           UTIL            *
*                           *
*****************************/

function getAllOptionNodes(){
    return document.querySelectorAll('.user-option');
}

function findBoard(nick){
    return document.querySelector(`.user-option[name^="${nick}"]`);
}

function isEqualValue(nick, cellNumber, value){
    return findBoard(nick).querySelector(`.sudoku-cell[number="${cellNumber}"] p`).innerText == value;
}

function isFinish(userOptionNode, count = CELL_QUANTITY){
    return document.evaluate(
        `.//div[contains(@class,"sudoku-cell") and not(contains(@class,"wrong-answer"))]/p[string-length(text()) > 0]`,
        userOptionNode,
        null,
        XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
        null
    ).snapshotLength >= count;
}

function sliceNick(nick){
    return nick.length > 16 ? nick.slice(0, 16) + '...' : nick
}

function getFilledCellQuantity(userOptionNode, onlyTruth = false){
    let quantity;
    if (onlyTruth){
        quantity = document.evaluate(".//div[contains(@class, 'sudoku-cell') and not(contains(@class, 'wrong-answer'))]/p[text() != '']", userOptionNode, null, XPathResult.UNORDERED_NODE_SNAPSHOT_TYPE).snapshotLength;
    } else {
        quantity = document.evaluate(".//div[contains(@class, 'sudoku-cell')]/p[text() != '']", userOptionNode, null, XPathResult.UNORDERED_NODE_SNAPSHOT_TYPE).snapshotLength;
    }

    return quantity
}