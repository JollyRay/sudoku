import {renderSymbol} from './symbols.js?v=11';

function makeTable(container, size, own) {
    container.replaceChildren();
    const table=document.createElement('table');table.className='sudoku-board';
    const body=document.createElement('tbody');
    for(let r=0;r<size;r++) {
        const row=document.createElement('tr');row.dataset.rowIndex=r;
        for(let c=0;c<size;c++) {
            const td=document.createElement('td');td.dataset.columnIndex=c;
            const cell=document.createElement(own?'button':'span');
            cell.className='cell';cell.dataset.cellIndex=r*size+c;
            if(own){cell.type='button';cell.tabIndex=-1;}
            for(const name of ['digit','cell-notes','bonus-mark']) {
                const part=document.createElement('span');part.className=name;
                if(name!=='digit')part.setAttribute('aria-hidden','true');
                cell.append(part);
            }
            td.append(cell);row.append(td);
        }
        body.append(row);
    }
    table.append(body);container.append(table);return table;
}
export function getNoteLayout(size, value) {
    const side=Math.ceil(Math.sqrt(size)),position=value-1;
    return {side,row:Math.floor(position/side)+1,column:position%side+1};
}
export function renderBoard(container, board, {config,selectedCell=null,highlightValue}) {
    const own=board.name===config.username,size=board.size??9;
    const table=container.querySelector('table')??makeTable(container,size,own);
    table.dataset.boardName=board.name;table.setAttribute('aria-label',`${own?'Моя доска':'Доска игрока'} ${board.name}`);
    const fixed=new Set(board.fixedCells??[]),wrong=new Set(board.wrongCells??[]);
    const selectedValue=highlightValue??board.values?.[selectedCell]??'';
    for(const cell of table.querySelectorAll('[data-cell-index]')) {
        const i=Number(cell.dataset.cellIndex),r=Math.floor(i/9),c=i%9,value=board.values?.[i]??'';
        const selected=own&&i===selectedCell;
        const related=own&&selectedCell!==null&&(r===Math.floor(selectedCell/9)||c===selectedCell%9||
            (Math.floor(r/3)===Math.floor(selectedCell/27)&&Math.floor(c/3)===Math.floor((selectedCell%9)/3)));
        cell.classList.toggle('is-fixed',fixed.has(i));cell.classList.toggle('is-selected',selected);
        cell.classList.toggle('is-related',related);
        cell.classList.toggle('is-matching',own&&value!==''&&value===selectedValue);
        cell.classList.toggle('is-error',config.preferences.showErrors&&wrong.has(i));
        cell.dataset.fixed=String(fixed.has(i));cell.dataset.value=String(value);
        if(own){cell.tabIndex=(i===(selectedCell??0))?0:-1;cell.setAttribute('aria-pressed',String(selected));}
        const digit=cell.querySelector('.digit');
        renderSymbol(digit,value,config.runtime.symbolSheet);
        const notes=cell.querySelector('.cell-notes');
        const candidates=own&&value===''?(config.local.notes[i]??[]).filter(n=>Number.isInteger(n)&&n>=1&&n<=size):[];
        const side=Math.ceil(Math.sqrt(size));
        const notesSignature=`${side}:${candidates.join(',')}`;
        if(notes.dataset.values!==notesSignature){
            notes.replaceChildren();
            notes.style.gridTemplateColumns=`repeat(${side},minmax(0,1fr))`;
            notes.style.gridTemplateRows=`repeat(${side},minmax(0,1fr))`;
            for(const note of candidates) {
                const {row,column}=getNoteLayout(size,note);
                const n=document.createElement('span');n.textContent=note;
                n.style.gridArea=`${row} / ${column}`;
                notes.append(n);
            }
            notes.dataset.values=notesSignature;
        }
        const bonus=board.bonuses?.[i],definition=config.runtime.bonusCatalog?.find(b=>b.id===bonus);
        const mark=cell.querySelector('.bonus-mark'),bonusSymbol=bonus?(definition?.symbol??'◇'):'';
        if(mark.textContent!==bonusSymbol)mark.textContent=bonusSymbol;
        const bonusLabel=bonus?`Бонус: ${definition?.label??bonus}`:'';
        cell.setAttribute('aria-label',`Строка ${r+1}, столбец ${c+1}: ${value===''?'пусто':value}${candidates.length?', заметки: '+candidates.join(', '):''}${fixed.has(i)?', исходная':''}${config.preferences.showErrors&&wrong.has(i)?', ошибка':''}${bonusLabel?', '+bonusLabel:''}`);
    }
    let completion=container.querySelector('.completion-overlay');
    if(!completion){
        completion=document.createElement('div');completion.className='completion-overlay';
        completion.setAttribute('role','status');
        const label=document.createElement('strong');label.textContent='Готово!';completion.append(label);
        container.append(completion);
    }
    completion.hidden=!board.completed;
    container.classList.toggle('is-completed',Boolean(board.completed));
    return table;
}
